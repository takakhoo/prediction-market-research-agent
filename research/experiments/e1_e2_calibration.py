"""E1 and E2. Calibration of Polymarket prices, measured two ways on the same markets.

E1 (the midpoint artifact): the public price-history endpoint returns a quote midpoint even when the
book is empty, so dormant markets sit near 0.5 without anyone being able to trade there. We compare
calibration of those midpoints with calibration of the last traded price at the same snapshot times.

E2 (the atlas): calibration slope, intercept, and Brier decomposition of last-trade prices by category
and horizon. Slope b comes from y ~ sigmoid(a + b logit p); b > 1 means prices are not extreme enough
(favorite-longshot bias), b < 1 means they are too extreme. One weight per market, CIs resample events.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.lib.panel import build, load_prices, prepare_markets
from research.lib.stats import brier, calibration_table, fit_logistic, logit, murphy

EDGES = np.array([0, .02, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, .95, .98, 1.0001])
LONG_TAIL = ["politics", "geopolitics", "economy", "finance", "culture", "tech", "mentions", "other"]


def mweights(df):
    return (1.0 / df.groupby("market_id").p.transform("size")).to_numpy()


def slope_ci(df, n_boot=300, seed=0):
    w = mweights(df)
    x, y = logit(df.p.to_numpy()), df.y.to_numpy(float)
    a, b = fit_logistic(x, y, w)
    codes, _ = pd.factorize(df.event_id.to_numpy())
    rng = np.random.default_rng(seed)
    draws = np.array([fit_logistic(x, y, w * rng.poisson(1.0, codes.max() + 1)[codes]) for _ in range(n_boot)])
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    return {"intercept": float(a), "slope": float(b), "slope_ci": [float(lo[1]), float(hi[1])],
            "intercept_ci": [float(lo[0]), float(hi[0])], "markets": int(df.market_id.nunique()),
            "events": int(df.event_id.nunique()), "brier": brier(df.p, df.y, w),
            "mean_p": float(np.average(df.p, weights=w)), "mean_y": float(np.average(df.y, weights=w))}


def table(df):
    t = calibration_table(df, EDGES, w=mweights(df))
    t["gap"] = t.mean_y - t.mean_p
    return t.round(5).to_dict(orient="records")


def main():
    trade = pd.read_parquet("research/data/derived/panel.parquet")
    trade = trade[trade.kind == 0]
    m = prepare_markets(pd.read_parquet("research/data/derived/markets.parquet"))
    px = load_prices()
    px = px[px.market_id.isin(trade.market_id.unique())]
    quote = build(m, px)
    quote[["market_id", "t_snap", "p"]].rename(columns={"p": "p_mid"}).to_parquet("research/data/derived/quote_panel.parquet", index=False)
    quote = quote[quote.kind == 0]
    # every midpoint snapshot, tagged by whether anyone had traded in the day before it
    key = ["market_id", "t_snap"]
    q = quote.merge(trade[key + ["age", "p"]].rename(columns={"p": "p_trade", "age": "age_trade"}), on=key, how="left")
    q["dormant"] = q.age_trade.isna() | (q.age_trade > 86400)
    res = {"e1": {}, "e2": {}}
    groups = {"all": q, "long_tail_yes_no": q[q.yes_no & q.category.isin(LONG_TAIL)], "sports": q[q.category == "sports"]}
    print("E1: quote midpoints, snapshots with a trade in the prior 24h vs dormant snapshots")
    for name, g in groups.items():
        r = {"share_dormant": float(g.dormant.mean())}
        for label, h in (("active", g[~g.dormant]), ("dormant", g[g.dormant])):
            if h.market_id.nunique() < 100:
                continue
            zone = h[(h.p > 0.4) & (h.p < 0.6)]
            r[label] = {**slope_ci(h, n_boot=150), "table": table(h), "share_in_0.4_0.6": float(len(zone) / len(h)),
                        "outcome_minus_price_0.4_0.6": float(np.average(zone.y - zone.p, weights=mweights(zone))) if len(zone) else None}
        both = g[~g.dormant & g.p_trade.notna()]
        r["active_last_trade"] = {**slope_ci(both.assign(p=both.p_trade), n_boot=150), "table": table(both.assign(p=both.p_trade))}
        res["e1"][name] = r
        a_, d_ = r.get("active"), r.get("dormant")
        if a_ and d_:
            print(f"  {name:18s} dormant share {100*r['share_dormant']:.0f}% | active: Brier {a_['brier']:.4f} slope {a_['slope']:.2f} gap@0.4-0.6 {a_['outcome_minus_price_0.4_0.6']:+.3f} "
                  f"| dormant: Brier {d_['brier']:.4f} slope {d_['slope']:.2f} gap@0.4-0.6 {d_['outcome_minus_price_0.4_0.6']:+.3f} ({100*d_['share_in_0.4_0.6']:.0f}% of dormant snapshots sit in 0.4-0.6 vs {100*a_['share_in_0.4_0.6']:.0f}%)")
    print("E2: last-trade calibration by category")
    live = trade[trade.age < np.maximum(6 * 3600, 0.1 * trade.life)]
    res["e2"]["overall"] = slope_ci(live)
    res["e2"]["overall"]["murphy"] = murphy(live.p.to_numpy(), live.y.to_numpy())
    res["e2"]["by_category"] = {}
    for c, g in live.groupby("category"):
        if g.market_id.nunique() < 100:
            continue
        r = slope_ci(g)
        r["table"] = table(g)
        res["e2"]["by_category"][c] = r
        print(f"  {c:14s} mkts {r['markets']:6d} Brier {r['brier']:.4f} mean p {r['mean_p']:.3f} mean y {r['mean_y']:.3f} slope {r['slope']:.3f} [{r['slope_ci'][0]:.3f}, {r['slope_ci'][1]:.3f}] intercept {r['intercept']:+.3f} [{r['intercept_ci'][0]:+.3f}, {r['intercept_ci'][1]:+.3f}]")
    res["e2"]["by_life_fraction"] = {}
    for lo, hi in [(0, .15), (.15, .45), (.45, .75), (.75, 1.0)]:
        g = live[(live.frac_life >= lo) & (live.frac_life < hi)]
        res["e2"]["by_life_fraction"][f"{lo}-{hi}"] = slope_ci(g)
        r = res["e2"]["by_life_fraction"][f"{lo}-{hi}"]
        print(f"  life {lo:.2f}-{hi:.2f} mkts {r['markets']:6d} Brier {r['brier']:.4f} slope {r['slope']:.3f} [{r['slope_ci'][0]:.3f}, {r['slope_ci'][1]:.3f}]")
    res["e2"]["table_all"] = table(live)
    json.dump(res, open("results/tables/e1_e2_calibration.json", "w"), indent=1)


if __name__ == "__main__":
    main()
