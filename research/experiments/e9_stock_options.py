"""E9. Polymarket single-stock threshold contracts priced as digital options on the official close.

Same design as E4, with a trading-time variance clock (sessions carry 75% of a day's variance, the
overnight gap 25%) and trailing 20-day close-to-close volatility. Spot is the last completed hourly
bar, so the model is blind to pre-market and after-hours moves. WTI and index-level contracts are
excluded because the continuous futures and index series do not reproduce their settlements.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.experiments.e4_crypto_options import encompass
from research.lib.boot import diff_ci, ratio_ci
from research.lib.stocks import model_prob

HB = [0, 3600, 6 * 3600, 86400, 3 * 86400, 30 * 86400]
HL = ["<1h", "1-6h", "6-24h", "1-3d", ">3d"]
EXCLUDE = {"CL_F", "GSPC"}


def load(lag=0):
    c = pd.read_parquet("research/data/derived/stock_contracts.parquet")
    c = c[~c.file.isin(EXCLUDE)]
    t = pd.read_parquet("research/data/derived/tape.parquet",
                        columns=["market_id", "t", "p", "d", "cost", "size", "usd", "win", "fee"])
    t = t.merge(c[["market_id", "ticker", "file", "kind", "k", "k2", "t_end", "y"]], on="market_id")
    t = t[t.t < t.t_end - 60]
    o = model_prob(t, lag=lag)
    o["day"] = (o.t_end // 86400).astype(int)
    o["hb"] = pd.cut(o.tau, HB, labels=HL)
    return o


def main():
    o = load()
    res = {"markets": int(o.market_id.nunique()), "fills": int(len(o)), "usd": float(o.usd.sum()), "tickers": sorted(o.ticker.unique().tolist())}
    print(f"{res['markets']:,} stock contracts, {res['fills']:,} fills, ${res['usd']/1e6:.1f}M, {o.day.nunique()} expiry days")
    res["brier"] = {}
    for hb, h in o.groupby("hb", observed=True):
        if h.market_id.nunique() < 50:
            continue
        w = (1.0 / h.groupby("market_id").p.transform("size")).to_numpy()
        y = h.y.to_numpy(float)
        d = (h.pm.to_numpy() - y) ** 2 - (h.p.to_numpy() - y) ** 2
        pt, lo, hi, _ = diff_ci(d, w, h.day.to_numpy(), n_boot=600)
        res["brier"][str(hb)] = {"markets": int(h.market_id.nunique()), "brier_fill": float(np.average((h.p - y) ** 2, weights=w)),
                                 "brier_model": float(np.average((h.pm - y) ** 2, weights=w)), "model_minus_fill": pt, "ci": [lo, hi]}
        r = res["brier"][str(hb)]
        print(f"  {str(hb):6s} mkts {r['markets']:5d} Brier fill {r['brier_fill']:.4f} model {r['brier_model']:.4f} diff {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    res["encompass"] = encompass(o[o.tau > 600])
    e = res["encompass"]
    print(f"  weight on price {e['w_price']:.2f} [{e['w_price_ci'][0]:.2f}, {e['w_price_ci'][1]:.2f}], weight on model {e['w_model']:.2f} [{e['w_model_ci'][0]:.2f}, {e['w_model_ci'][1]:.2f}]")
    res["endorsed"] = {}
    for lag in (0, 3600, 4 * 3600):
        g = o if lag == 0 else load(lag)
        edge = g.d.to_numpy() * (g.pm.to_numpy() - g.p.to_numpy()) - g.fee.to_numpy()
        sh = g["size"].to_numpy(float)
        pnl, stake = sh * (g.win.to_numpy() - g.cost.to_numpy() - g.fee.to_numpy()), sh * g.cost.to_numpy()
        for th in (0.05, 0.10):
            for label, s in (("endorsed", edge > th), ("opposed", edge < -th)):
                if s.sum() < 200:
                    continue
                r = ratio_ci(pnl[s], stake[s], g.day.to_numpy()[s])
                res["endorsed"][f"lag{lag}s_{label}_{th}"] = {"fills": int(s.sum()), "markets": int(g.market_id[s].nunique()), "stake": float(stake[s].sum()), "taker_net_return": r}
                print(f"  extra spot age {lag // 3600}h {label:8s} |edge|>{th:.2f}: fills {s.sum():6d} mkts {g.market_id[s].nunique():5d} stake ${stake[s].sum()/1e6:5.2f}M taker net {100*r[0]:+6.2f}% [{100*r[1]:+6.2f}, {100*r[2]:+6.2f}]")
    json.dump(res, open("results/tables/e9_stock_options.json", "w"), indent=1)


if __name__ == "__main__":
    main()
