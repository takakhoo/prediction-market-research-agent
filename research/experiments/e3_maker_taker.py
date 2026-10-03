"""E3. Who wins at real fills: taker and maker returns by price paid, category, and time to close.

Every row of the tape is a fill that happened. The taker paid `cost` per share for the side they
bought and wins 1 if that side resolves true; the maker holds the other side at 1 - cost.
Returns are on dollars staked, fees included for takers, CIs resample whole events.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.lib.boot import ratio_ci

EDGES = [0, .02, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .95, .98, 1.0]
TTC = [0, 300, 3600, 6 * 3600, 86400, 7 * 86400, 1e12]
TTC_LABELS = ["<5m", "5m-1h", "1-6h", "6-24h", "1-7d", ">7d"]


def summarize(t: pd.DataFrame) -> dict:
    sh = t["size"].to_numpy(dtype=np.float64)
    stake_t = sh * t.cost.to_numpy()
    stake_m = sh * (1 - t.cost.to_numpy())
    gross_t = sh * (t.win.to_numpy() - t.cost.to_numpy())
    fee = sh * t.fee.to_numpy()
    ev = t.event_id.to_numpy()
    out = {"fills": int(len(t)), "markets": int(t.market_id.nunique()), "events": int(t.event_id.nunique()),
           "taker_usd": float(stake_t.sum())}
    out["taker_gross"] = ratio_ci(gross_t, stake_t, ev)
    out["taker_net"] = ratio_ci(gross_t - fee, stake_t, ev)
    out["maker_gross"] = ratio_ci(-gross_t, stake_m, ev)
    out["fee_rate_paid"] = float(fee.sum() / stake_t.sum())
    return out


def first_entry(t: pd.DataFrame, bands=((0.55, 0.70), (0.70, 0.85), (0.85, 0.95))) -> dict:
    """One bet per market: buy the favorite at the first fill whose favorite-side price lands in the band.

    Pooling every fill weights markets by how long the price lingers in the band, and averaging
    per-market return ratios is biased upward because a market where the early favorite loses also
    collects winning fills once the other side becomes the favorite. Taking only the first qualifying
    fill is a stopping rule, so under efficient prices its expected profit is exactly zero.
    """
    fav_cost = np.maximum(t.p.to_numpy(), 1 - t.p.to_numpy())
    fav_win = np.where(t.p.to_numpy() >= 0.5, t.y.to_numpy(), 1 - t.y.to_numpy())
    out = {}
    for lo, hi in bands:
        s = (fav_cost > lo) & (fav_cost <= hi)
        g = t[s].assign(fav_cost=fav_cost[s], fav_win=fav_win[s]).sort_values(["market_id", "t"]).groupby("market_id").head(1)
        fee = np.nan_to_num(g.fee_rate.to_numpy(), nan=0.0) * g.fav_cost.to_numpy() * (1 - g.fav_cost.to_numpy())
        gross = g.fav_win.to_numpy() - g.fav_cost.to_numpy()
        r = {"markets": int(len(g)), "mean_cost": float(g.fav_cost.mean()), "win_rate": float(g.fav_win.mean()),
             "gross": ratio_ci(gross, g.fav_cost.to_numpy(), g.event_id.to_numpy()),
             "net_of_taker_fee": ratio_ci(gross - fee, g.fav_cost.to_numpy(), g.event_id.to_numpy()), "by_category": {}}
        for c, h in g.groupby("category"):
            if len(h) >= 200:
                r["by_category"][c] = {"markets": int(len(h)), "gross": ratio_ci((h.fav_win - h.fav_cost).to_numpy(), h.fav_cost.to_numpy(), h.event_id.to_numpy())}
        out[f"{lo}-{hi}"] = r
    return out


def main():
    t = pd.read_parquet("research/data/derived/tape.parquet")
    res = {"all": summarize(t)}
    res["by_category"] = {c: summarize(g) for c, g in t.groupby("category")}
    t["cb"] = pd.cut(t.cost, EDGES, right=True)
    res["taker_by_cost"] = {str(k): {**summarize(g), "mean_cost": float(np.average(g.cost, weights=g["size"])),
                                      "win_rate": float(np.average(g.win, weights=g["size"]))}
                            for k, g in t.groupby("cb", observed=True)}
    t["tb"] = pd.cut(t.ttc, TTC, labels=TTC_LABELS)
    res["by_time_to_close"] = {str(k): summarize(g) for k, g in t.groupby("tb", observed=True)}
    # both sides of every fill bought something: pool them to ask whether a price of c wins c of the time
    both = pd.DataFrame({
        "cost": np.concatenate([t.cost.to_numpy(), 1 - t.cost.to_numpy()]),
        "win": np.concatenate([t.win.to_numpy(), 1 - t.win.to_numpy()]),
        "size": np.concatenate([t["size"].to_numpy()] * 2),
        "role": np.repeat(["taker", "maker"], len(t)),
        "event_id": np.concatenate([t.event_id.to_numpy()] * 2),
    })
    both["cb"] = pd.cut(both.cost, EDGES, right=True)
    rows = {}
    for (cb, role), g in both.groupby(["cb", "role"], observed=True):
        sh = g["size"].to_numpy(dtype=np.float64)
        rows.setdefault(str(cb), {})[role] = {
            "mean_cost": float(np.average(g.cost, weights=sh)),
            "win_rate": ratio_ci(sh * g.win.to_numpy(), sh, g.event_id.to_numpy(), n_boot=400),
            "ret": ratio_ci(sh * (g.win.to_numpy() - g.cost.to_numpy()), sh * g.cost.to_numpy(), g.event_id.to_numpy(), n_boot=400),
        }
    res["price_paid_by_role"] = rows
    res["favorite_first_entry"] = first_entry(t)
    json.dump(res, open("results/tables/e3_maker_taker.json", "w"), indent=1)
    a = res["all"]
    print(f"{a['fills']:,} fills, {a['markets']:,} markets, ${a['taker_usd']/1e6:.0f}M taker stake")
    print("taker gross %+.2f%% [%+.2f, %+.2f]  net %+.2f%% [%+.2f, %+.2f]" % tuple(100 * x for x in a["taker_gross"] + a["taker_net"]))
    for c, r in res["by_category"].items():
        print(f"  {c:14s} mkts {r['markets']:6d} usd {r['taker_usd']/1e6:8.1f}M  taker net %+.2f%% [%+.2f, %+.2f]  fee %.2f%%" % (*[100 * x for x in r["taker_net"]], 100 * r["fee_rate_paid"]))
    print("price paid -> win rate (taker | maker)")
    for cb, r in rows.items():
        print(f"  {cb:14s} taker cost {r['taker']['mean_cost']:.3f} win {r['taker']['win_rate'][0]:.3f} ret %+.1f%% | maker cost {r['maker']['mean_cost']:.3f} win {r['maker']['win_rate'][0]:.3f} ret %+.1f%%" % (100 * r['taker']['ret'][0], 100 * r['maker']['ret'][0]))
    print("first entry on the favorite, one bet per market (unbiased under efficient prices):")
    for band, r in res["favorite_first_entry"].items():
        print(f"  band {band}: {r['markets']:,} markets, cost {r['mean_cost']:.3f}, win {r['win_rate']:.3f}, gross %+.2f%% [%+.2f, %+.2f], net of fee %+.2f%% [%+.2f, %+.2f]" % tuple(100 * x for x in r["gross"] + r["net_of_taker_fee"]))
        print("     " + "  ".join(f"{c} %+.1f%% [%+.1f,%+.1f]" % tuple(100 * x for x in v["gross"]) for c, v in r["by_category"].items()))
    print("pooled both sides, price paid -> win rate with event-clustered CI:")
    for cb, r in rows.items():
        t_, m_ = r["taker"], r["maker"]
        print(f"  {cb:14s} taker win {t_['win_rate'][0]:.3f} [{t_['win_rate'][1]:.3f},{t_['win_rate'][2]:.3f}] at {t_['mean_cost']:.3f} | maker win {m_['win_rate'][0]:.3f} [{m_['win_rate'][1]:.3f},{m_['win_rate'][2]:.3f}] at {m_['mean_cost']:.3f}")
    print("by time to close:")
    for k, r in res["by_time_to_close"].items():
        print(f"  {k:6s} usd {r['taker_usd']/1e6:8.1f}M taker net %+.2f%% [%+.2f, %+.2f]" % tuple(100 * x for x in r["taker_net"]))


if __name__ == "__main__":
    main()
