"""E5. Can anything beat the price? Walk-forward comparison of forecasters at ex-ante snapshots.

Baseline: the last traded price. Challengers: smoothed price, Platt and isotonic recalibration,
category-wise recalibration, and residual boosted trees with growing feature sets (path and flow,
smoothed-price gap, wallet-record flow). Training labels are purged: a model tested in month M
has seen only markets that resolved before M began. One weight per market, CIs resample events.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from research.lib.boot import diff_ci
from research.lib.features import BASE, FAIR, SMOOTH, WALLET, add_fair, add_features
from research.lib.stats import brier, logloss
from research.lib.walkforward import Column, FairBlend, Isotonic, Platt, PlattByCategory, ResidualGBM, market_weights, run


def score(R: pd.DataFrame, names) -> dict:
    w = market_weights(R)
    y, p = R.y.to_numpy(float), R.p.to_numpy(float)
    ev = R.event_id.to_numpy()
    out = {"snapshots": int(len(R)), "markets": int(R.market_id.nunique()), "events": int(R.event_id.nunique()),
           "market": {"brier": brier(p, y, w), "logloss": logloss(p, y, w)}}
    for n in names:
        q = R[n].to_numpy(float)
        d = (q - y) ** 2 - (p - y) ** 2
        pt, lo, hi, share = diff_ci(d, w, ev)
        out[n] = {"brier": brier(q, y, w), "logloss": logloss(q, y, w), "d_brier": pt, "ci": [lo, hi],
                  "skill_pct": -100 * pt / out["market"]["brier"], "p_better": 1 - share}
    return out


HOLDOUT_START = "2026-05"


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "2025-09-01"
    P = add_features(pd.read_parquet("research/data/derived/panel.parquet"))
    P = add_fair(P[(P.p > 0.005) & (P.p < 0.995)].reset_index(drop=True))
    mid = pd.read_parquet("research/data/derived/quote_panel.parquet").drop_duplicates(["market_id", "t_snap"])
    P = P.merge(mid, on=["market_id", "t_snap"], how="left")
    P["quote_mid"] = P.p_mid.fillna(P.p)  # where no quote history exists, fall back to the last trade
    P.to_parquet("research/data/derived/panel_features.parquet", index=False)
    models = [Column("quote_mid"), Column("vwap10"), Platt(), PlattByCategory(), Isotonic(),
              ResidualGBM(BASE + SMOOTH + WALLET, "res_flow_wallets"),
              ResidualGBM(BASE + SMOOTH + WALLET + FAIR, "res_full"),
              FairBlend()]
    R = run(P, models, start=start, min_train_markets=1500)
    names = [m.name for m in models]
    R.to_parquet("research/data/derived/e5_predictions.parquet", index=False)
    res = {"all": score(R, names), "by_category": {c: score(g, names) for c, g in R.groupby("category") if g.market_id.nunique() >= 150}}
    live = R[R.age < np.maximum(6 * 3600, 0.1 * R.life)]
    res["live_only"] = score(live, names)
    # the last five months were not looked at while features and settings were chosen
    res["development"] = score(R[R.block < HOLDOUT_START], names)
    res["holdout"] = score(R[R.block >= HOLDOUT_START], names)
    priced = R[R.fair.notna()]
    res["price_linked_only"] = score(priced.assign(fair_value=priced.fair), names + ["fair_value"])
    res["price_linked_holdout"] = score(priced[priced.block >= HOLDOUT_START].assign(fair_value=lambda d: d.fair), names + ["fair_value"])
    # the same contracts scored against the quote midpoint instead of the last trade
    pq = priced[priced.p_mid.notna()].copy()
    pq["last_trade"], pq["fair_value"] = pq.p, pq.fair
    res["price_linked_vs_midpoint"] = score(pq.assign(p=pq.p_mid), ["last_trade", "fair_value", "fair_blend"])
    json.dump(res, open("results/tables/e5_model.json", "w"), indent=1)
    for label in ("all", "live_only", "development", "holdout", "price_linked_only", "price_linked_holdout", "price_linked_vs_midpoint"):
        a = res[label]
        print(f"[{label}] {a['markets']:,} test markets, {a['snapshots']:,} snapshots. Market Brier {a['market']['brier']:.5f}, log loss {a['market']['logloss']:.5f}")
        for n in [k for k in a if isinstance(a[k], dict) and "d_brier" in a[k]]:
            r = a[n]
            print(f"  {n:18s} Brier {r['brier']:.5f}  delta {r['d_brier']:+.5f} [{r['ci'][0]:+.5f}, {r['ci'][1]:+.5f}]  skill {r['skill_pct']:+.2f}%  logloss {r['logloss']:.5f}")
    best = "res_full"
    print(f"by category ({best}):")
    for c, r in res["by_category"].items():
        print(f"  {c:14s} mkts {r['markets']:6d} market {r['market']['brier']:.4f}  delta {r[best]['d_brier']:+.5f} [{r[best]['ci'][0]:+.5f}, {r[best]['ci'][1]:+.5f}]")


if __name__ == "__main__":
    main()
