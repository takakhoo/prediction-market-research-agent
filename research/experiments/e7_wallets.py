"""E7. Do wallets with good records keep winning?

For every taker fill, the wallet's record is its realized profit over stake on markets that had
resolved before that fill (research/experiments/build_tape.py). We bucket fills by that prior
record and measure the realized net return of the fills themselves. Caveat: records come from the
sampled markets only, so each wallet's history is partial.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.lib.boot import ratio_ci

BINS = [-10, -0.2, -0.1, -0.05, -0.02, 0, 0.02, 0.05, 0.1, 0.2, 10]


def main():
    t = pd.read_parquet("research/data/derived/tape.parquet",
                        columns=["market_id", "event_id", "cost", "win", "fee", "size", "w_pnl", "w_stake", "w_n", "wallet"])
    sh = t["size"].to_numpy(float)
    t["stake"], t["pnl"] = sh * t.cost, sh * (t.win - t.cost - t.fee)
    roi = t.w_pnl / (t.w_stake + 1000)
    seasoned = (t.w_n >= 50) & (t.w_stake >= 5000)
    res = {"wallets": int(t.wallet.nunique()), "fills": int(len(t)), "seasoned_stake_share": float(t.stake[seasoned].sum() / t.stake.sum()), "buckets": {}}

    def row(g):
        r = ratio_ci(g.pnl.to_numpy(), g.stake.to_numpy(), g.event_id.to_numpy(), 500)
        return {"fills": int(len(g)), "wallets": int(g.wallet.nunique()), "stake": float(g.stake.sum()), "net_return": r}

    res["first_timers"] = row(t[t.w_n == 0])
    res["seasoned"] = row(t[seasoned])
    print(f"{res['wallets']:,} wallets. First-time wallets: {100*res['first_timers']['net_return'][0]:+.2f}% [{100*res['first_timers']['net_return'][1]:+.2f}, {100*res['first_timers']['net_return'][2]:+.2f}]"
          f"; seasoned wallets: {100*res['seasoned']['net_return'][0]:+.2f}% [{100*res['seasoned']['net_return'][1]:+.2f}, {100*res['seasoned']['net_return'][2]:+.2f}]")
    t["rb"] = pd.cut(roi.where(seasoned), BINS)
    for k, g in t.groupby("rb", observed=True):
        res["buckets"][str(k)] = row(g)
        r = res["buckets"][str(k)]
        print(f"  prior record {str(k):15s} wallets {r['wallets']:5d} stake ${r['stake']/1e6:6.1f}M later net return {100*r['net_return'][0]:+.2f}% [{100*r['net_return'][1]:+.2f}, {100*r['net_return'][2]:+.2f}]")
    json.dump(res, open("results/tables/e7_wallets.json", "w"), indent=1)


if __name__ == "__main__":
    main()
