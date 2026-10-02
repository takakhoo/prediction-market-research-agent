"""E4. Polymarket crypto contracts priced as digital options.

Each threshold contract ("Bitcoin above K at noon") is a cash-or-nothing digital. With spot S, time to
expiry tau, and volatility sigma, a driftless lognormal model gives P(S_T > K) = N(d2). We ask, at
every real fill:
  a. which forecasts the outcome better, the fill price or the model?
  b. does the model carry information the fill price lacks (encompassing regression)?
  c. are fills the model endorses profitable for the taker after fees, and does that survive when the
     model's spot input is 1, 5, 15, or 60 minutes old?
  d. what volatility do Polymarket prices imply, and how does it compare with realized and Deribit DVOL?
Clusters for inference are expiry dates, since contracts expiring the same day share one price path.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import optimize

from research.experiments.crypto_obs import CONTRACT_COLS, attach_spot, restrict
from research.lib.boot import diff_ci, ratio_ci
from research.lib.stats import logit
from research.lib.vol import YEAR, contract_prob, implied_vol

HB = [0, 300, 900, 3600, 6 * 3600, 86400, 3 * 86400, 30 * 86400]
HL = ["<5m", "5-15m", "15m-1h", "1-6h", "6-24h", "1-3d", ">3d"]
RV_GRID = np.array([900, 3600, 6 * 3600, 86400, 7 * 86400, 30 * 86400])
RV_COLS = ["rv_15m", "rv_1h", "rv_6h", "rv_1d", "rv_7d", "rv_30d"]


def matched_vol(o: pd.DataFrame) -> np.ndarray:
    """Trailing realized vol over a window about four times the remaining horizon, floored at one hour."""
    target = np.clip(4 * o.tau.to_numpy(), 3600, 30 * 86400)
    idx = np.abs(np.log(target[:, None] / RV_GRID[None, :])).argmin(axis=1)
    return o[RV_COLS].to_numpy()[np.arange(len(o)), idx]


def load(lag=0):
    c = pd.read_parquet("research/data/derived/crypto_contracts.parquet")
    t = pd.read_parquet("research/data/derived/tape.parquet",
                        columns=["market_id", "t", "p", "d", "cost", "size", "usd", "win", "fee", "event_id", "wallet"])
    t = t.merge(c[CONTRACT_COLS].drop(columns=["fee_rate"]), on="market_id")
    o = attach_spot(restrict(t), lag=lag)
    o["sigma"] = matched_vol(o)
    o["pm"] = contract_prob(o, o.sigma)
    o["day"] = (o.t_end // 86400).astype(int)
    o["hb"] = pd.cut(o.tau, HB, labels=HL)
    return o


def encompass(o, n_boot=300):
    X = np.column_stack([np.ones(len(o)), logit(o.p.to_numpy()), logit(o.pm.to_numpy())])
    y = o.y.to_numpy(float)
    w = (1.0 / o.groupby("market_id").p.transform("size")).to_numpy()
    codes, _ = pd.factorize(o.day.to_numpy())

    def fit(ww):
        nll = lambda th: np.sum(ww * (np.logaddexp(0, X @ th) - y * (X @ th)))
        jac = lambda th: X.T @ (ww * (1 / (1 + np.exp(-(X @ th))) - y))
        return optimize.minimize(nll, np.array([0.0, 0.5, 0.5]), jac=jac, method="BFGS").x

    th = fit(w)
    rng = np.random.default_rng(0)
    draws = np.array([fit(w * rng.poisson(1.0, codes.max() + 1)[codes]) for _ in range(n_boot)])
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    return {"w_price": float(th[1]), "w_model": float(th[2]), "w_price_ci": [float(lo[1]), float(hi[1])], "w_model_ci": [float(lo[2]), float(hi[2])]}


def main():
    o = load()
    res = {}
    thr = o[o.kind.isin(["above", "below", "between"])]
    upd = o[o.kind == "updown"]
    print(f"threshold contracts: {thr.market_id.nunique():,} markets, {len(thr):,} fills, ${thr.usd.sum()/1e6:.1f}M; "
          f"up/down: {upd.market_id.nunique():,} markets, {len(upd):,} fills, ${upd.usd.sum()/1e6:.1f}M")
    for name, g in (("threshold", thr), ("updown", upd)):
        rows = {}
        for hb, h in g.groupby("hb", observed=True):
            if h.market_id.nunique() < 50:
                continue
            w = (1.0 / h.groupby("market_id").p.transform("size")).to_numpy()
            y = h.y.to_numpy(float)
            d = (h.pm.to_numpy() - y) ** 2 - (h.p.to_numpy() - y) ** 2
            pt, lo, hi, _ = diff_ci(d, w, h.day.to_numpy(), n_boot=600)
            rows[str(hb)] = {"markets": int(h.market_id.nunique()), "fills": int(len(h)), "days": int(h.day.nunique()),
                             "brier_fill": float(np.average((h.p - y) ** 2, weights=w)), "brier_model": float(np.average((h.pm - y) ** 2, weights=w)),
                             "model_minus_fill": pt, "ci": [lo, hi]}
            print(f"  {name:9s} {str(hb):7s} mkts {rows[str(hb)]['markets']:6d} Brier fill {rows[str(hb)]['brier_fill']:.4f} model {rows[str(hb)]['brier_model']:.4f}  diff {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]")
        res[f"brier_{name}"] = rows
        res[f"encompass_{name}"] = encompass(g[(g.tau > 300)])
        e = res[f"encompass_{name}"]
        print(f"  {name}: weight on price {e['w_price']:.2f} [{e['w_price_ci'][0]:.2f}, {e['w_price_ci'][1]:.2f}], weight on model {e['w_model']:.2f} [{e['w_model_ci'][0]:.2f}, {e['w_model_ci'][1]:.2f}]")

    print("taker fills the model endorses (threshold contracts), by staleness of the model's spot input")
    res["endorsed"] = {}
    for lag in (0, 240, 840, 3540):
        g = thr if lag == 0 else load(lag)[lambda x: x.kind.isin(["above", "below", "between"])]
        edge = g.d.to_numpy() * (g.pm.to_numpy() - g.p.to_numpy()) - g.fee.to_numpy()
        sh = g["size"].to_numpy(float)
        pnl = sh * (g.win.to_numpy() - g.cost.to_numpy() - g.fee.to_numpy())
        stake = sh * g.cost.to_numpy()
        for th in (0.02, 0.05, 0.10):
            for label, s in (("endorsed", edge > th), ("opposed", edge < -th)):
                if s.sum() < 200:
                    continue
                r = ratio_ci(pnl[s], stake[s], g.day.to_numpy()[s])
                res["endorsed"][f"lag{lag + 60}s_{label}_{th}"] = {"fills": int(s.sum()), "markets": int(g.market_id[s].nunique()), "days": int(g.day[s].nunique()),
                                                                 "stake": float(stake[s].sum()), "taker_net_return": r}
                print(f"  spot age {(lag + 60) // 60:3d}m {label:8s} |edge|>{th:.2f}: fills {s.sum():7d} mkts {g.market_id[s].nunique():5d} stake ${stake[s].sum()/1e6:6.2f}M taker net {100*r[0]:+6.2f}% [{100*r[1]:+6.2f}, {100*r[2]:+6.2f}]")

    # the same rule scored at displayed quote midpoints instead of fills: what a naive backtest would report
    q = pd.read_parquet("research/data/derived/crypto_obs.parquet")
    q = q[q.kind.isin(["above", "below", "between"])].copy()
    q["pm"] = contract_prob(q, matched_vol(q))
    gap = q.pm.to_numpy() - q.p.to_numpy()
    side = np.sign(gap)
    cost = np.where(side > 0, q.p.to_numpy(), 1 - q.p.to_numpy())
    win = np.where(side > 0, q.y.to_numpy(), 1 - q.y.to_numpy())
    s_ = np.abs(gap) > 0.10
    wq = (1.0 / q.groupby("market_id").p.transform("size")).to_numpy()
    r = ratio_ci((wq * (win - cost))[s_], (wq * cost)[s_], (q.t_end.to_numpy() // 86400).astype(int)[s_])
    res["displayed_price_rule"] = {"observations": int(s_.sum()), "markets": int(q.market_id[s_].nunique()), "return": r,
                                   "share_of_observations": float(s_.mean())}
    print(f"same rule at displayed midpoints: {s_.sum():,} observations in {q.market_id[s_].nunique():,} markets, return {100*r[0]:+.1f}% [{100*r[1]:+.1f}, {100*r[2]:+.1f}]")

    # by settlement quarter: does the edge persist?
    res["by_quarter"] = {}
    tq = thr.assign(q=pd.to_datetime(thr.t_end, unit="s").dt.to_period("Q").astype(str))
    tq["edge"] = tq.d * (tq.pm - tq.p) - tq.fee
    tq["pnl"] = tq["size"].astype(float) * (tq.win - tq.cost - tq.fee)
    tq["stake"] = tq["size"].astype(float) * tq.cost
    for qn, h in tq.groupby("q"):
        if h.market_id.nunique() < 80:
            continue
        row = {"markets": int(h.market_id.nunique()), "fills": int(len(h)), "fee_share": float((h.fee > 0).mean()),
               "encompass": encompass(h[h.tau > 300], n_boot=150)}
        for label, sel in (("endorsed", h.edge > 0.10), ("opposed", h.edge < -0.10)):
            if sel.sum() > 200:
                row[label] = {"stake": float(h.stake[sel].sum()), "return": ratio_ci(h.pnl[sel].to_numpy(), h.stake[sel].to_numpy(), h.day[sel].to_numpy(), 400)}
        res["by_quarter"][qn] = row
        e_ = row.get("endorsed", {"stake": 0, "return": (np.nan,) * 3})
        print(f"  {qn} mkts {row['markets']:5d} fee share {row['fee_share']:.2f} endorsed ${e_['stake']/1e3:6.0f}k {100*e_['return'][0]:+6.1f}% [{100*e_['return'][1]:+6.1f}, {100*e_['return'][2]:+6.1f}] model weight {row['encompass']['w_model']:.2f}")

    # d. implied volatility of 'above' fills against what was realized afterwards
    a = thr[(thr.kind == "above") & (thr.p > 0.1) & (thr.p < 0.9) & (thr.tau > 3600)].copy()
    a["iv"] = implied_vol(a.p.to_numpy(), a.s.to_numpy(), a.k.to_numpy(), a.tau.to_numpy())
    a = a[np.isfinite(a.iv)]
    from research.lib.contracts import Spot, load_spot
    fut = np.full(len(a), np.nan)
    for sym, idx in a.groupby("symbol").indices.items():
        sp = Spot(load_spot(sym))
        lc = np.log(pd.Series(sp.close).ffill().to_numpy())
        r2 = np.concatenate([[0.0], np.cumsum(np.diff(lc) ** 2)])
        i0 = np.clip(sp._i(a.t.to_numpy()[idx]), 0, sp.n - 1)
        i1 = np.clip(sp._i(a.t_end.to_numpy()[idx]), 0, sp.n - 1)
        fut[idx] = np.sqrt((r2[i1] - r2[i0]) / np.maximum(i1 - i0, 1) * YEAR / 60)
    a["rv_fwd"] = fut
    res["implied_vol"] = {}
    print("Polymarket-implied vol vs trailing, Deribit DVOL, and realized-to-expiry (median across markets)")
    for hb, h in a.groupby("hb", observed=True):
        mk = h.groupby("market_id")[["iv", "sigma", "rv_fwd", "dvol"]].median()
        if len(mk) < 50:
            continue
        r = {"markets": int(len(mk)), "implied": float(mk.iv.median()), "trailing": float(mk.sigma.median()), "realized_after": float(mk.rv_fwd.median()),
             "dvol": float(mk.dvol.median()), "implied_over_realized": float((mk.iv / mk.rv_fwd).median())}
        res["implied_vol"][str(hb)] = r
        print(f"  {str(hb):7s} mkts {r['markets']:5d} implied {r['implied']:.3f} trailing {r['trailing']:.3f} realized-after {r['realized_after']:.3f} DVOL {r['dvol']:.3f} implied/realized {r['implied_over_realized']:.2f}")
    json.dump(res, open("results/tables/e4_crypto_options.json", "w"), indent=1)


if __name__ == "__main__":
    main()
