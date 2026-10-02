"""E3b. Three ways to ask "are favorites mispriced?", and why they disagree.

  pooled      : every fill, share-weighted. Weights markets by how much trades inside the band.
  first touch : one bet per market at the first fill inside the band. A stopping rule, so its
                expected profit is zero if fill prices are fair.
  fade        : after a first touch, buy the other side at the next real taker fill on that side
                at least 60 seconds later, provided the price is still within 5 cents of the band.

Run on Yes/No markets outside sports, crypto, and weather, where "Yes" is a named event happening.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.lib.boot import diff_ci, ratio_ci

LONG_TAIL = ["politics", "geopolitics", "economy", "finance", "culture", "tech", "mentions", "other"]
EDGES = [0.02, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.98]


def main():
    t = pd.read_parquet("research/data/derived/tape.parquet",
                        columns=["market_id", "event_id", "t", "p", "y", "size", "yes_no", "category", "d", "fee_rate"])
    g = t[t.yes_no & t.category.isin(LONG_TAIL)].sort_values(["market_id", "t"]).reset_index(drop=True)
    g["k"] = g.groupby("market_id").cumcount()
    prev = g.groupby("market_id").p.transform(lambda s: s.shift(1).rolling(5, min_periods=1).median())
    nxt = g[::-1].groupby("market_id").p.transform(lambda s: s.shift(1).rolling(5, min_periods=1).median())[::-1]
    g["jump"], g["after"] = g.p - prev, nxt
    res = {"markets": int(g.market_id.nunique()), "fills": int(len(g)), "buckets": {}, "fade": {}, "anatomy": {}}
    print(f"{res['markets']:,} long-tail Yes/No markets, {res['fills']:,} fills")
    print("Yes price   pooled outcome-minus-price          first-touch outcome-minus-price")
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        h = g[(g.p > lo) & (g.p <= hi)]
        sh = h["size"].to_numpy(float)
        a = ratio_ci(sh * (h.y.to_numpy() - h.p.to_numpy()), sh, h.event_id.to_numpy(), 400)
        f = h.groupby("market_id").head(1)
        b = diff_ci((f.y - f.p).to_numpy(), np.ones(len(f)), f.event_id.to_numpy(), 1000)
        res["buckets"][f"{lo}-{hi}"] = {"pooled": a, "first_touch": b[:3], "markets": int(len(f))}
        print(f"  {lo:.2f}-{hi:.2f}   {a[0]:+.3f} [{a[1]:+.3f}, {a[2]:+.3f}]            {b[0]:+.3f} [{b[1]:+.3f}, {b[2]:+.3f}]  n={len(f):,}")

    sells = g[g.d == -1][["market_id", "t", "p", "fee_rate", "size"]].rename(columns={"t": "t2", "p": "p2", "fee_rate": "fr2", "size": "size2"})
    for lo, hi in ((0.6, 0.8), (0.8, 0.98)):
        f = g[(g.p > lo) & (g.p <= hi)].groupby("market_id").head(1)
        j = pd.merge_asof(f.assign(tq=f.t + 60).sort_values("tq"), sells.sort_values("t2"), left_on="tq", right_on="t2",
                          by="market_id", direction="forward")
        j = j[j.t2.notna() & (j.p2 > lo - 0.05)]
        fee = j.fr2.fillna(0) * j.p2 * (1 - j.p2)
        profit, stake = (j.p2 - j.y - fee).to_numpy(), (1 - j.p2).to_numpy()
        r = ratio_ci(profit, stake, j.event_id.to_numpy())
        res["fade"][f"{lo}-{hi}"] = {"markets": int(len(j)), "of_first_touches": int(len(f)), "median_wait_min": float((j.t2 - j.t).median() / 60),
                                     "return_on_stake": r, "per_share": diff_ci(profit, np.ones(len(j)), j.event_id.to_numpy())[:3]}
        usd = (j.size2 * (1 - j.p2)).to_numpy()
        res["fade"][f"{lo}-{hi}"]["fill_usd_median"] = float(np.median(usd))
        res["fade"][f"{lo}-{hi}"]["fill_usd_total"] = float(usd.sum())
        cut = pd.Timestamp("2026-04-01", tz="UTC").timestamp()
        for label, sel in (("before_2026_04", (j.t2 < cut).to_numpy()), ("from_2026_04", (j.t2 >= cut).to_numpy())):
            res["fade"][f"{lo}-{hi}"][label] = {"markets": int(sel.sum()), "return_on_stake": ratio_ci(profit[sel], stake[sel], j.event_id.to_numpy()[sel])}
        res["fade"][f"{lo}-{hi}"]["by_category"] = {
            c: {"markets": int(len(h)), "return_on_stake": ratio_ci(profit[h.index_pos.to_numpy()], stake[h.index_pos.to_numpy()], h.event_id.to_numpy())}
            for c, h in j.assign(index_pos=np.arange(len(j))).groupby("category") if len(h) >= 150}
        # baseline: the same kind of fill with no trigger, first one per market
        base = g[(g.d == -1) & (g.p > lo - 0.05) & (g.p <= hi)].groupby("market_id").head(1)
        bfee = base.fee_rate.fillna(0) * base.p * (1 - base.p)
        res["fade"][f"{lo}-{hi}"]["untriggered_baseline"] = {"markets": int(len(base)), "return_on_stake": ratio_ci(
            (base.p - base.y - bfee).to_numpy(), (1 - base.p).to_numpy(), base.event_id.to_numpy())}
        b_ = res["fade"][f"{lo}-{hi}"]
        print(f"   before 2026-04: {100*b_['before_2026_04']['return_on_stake'][0]:+.1f}% (n={b_['before_2026_04']['markets']:,}); from 2026-04: {100*b_['from_2026_04']['return_on_stake'][0]:+.1f}% "
              f"[{100*b_['from_2026_04']['return_on_stake'][1]:+.1f}, {100*b_['from_2026_04']['return_on_stake'][2]:+.1f}] (n={b_['from_2026_04']['markets']:,}); "
              f"untriggered baseline {100*b_['untriggered_baseline']['return_on_stake'][0]:+.1f}% [{100*b_['untriggered_baseline']['return_on_stake'][1]:+.1f}, {100*b_['untriggered_baseline']['return_on_stake'][2]:+.1f}]")
        print(f"   size of the fills copied: median ${np.median(usd):.0f}, total ${usd.sum()/1e3:.0f}k")
        print("   by category: " + "  ".join(f"{c} {100*v['return_on_stake'][0]:+.0f}%" for c, v in b_["by_category"].items()))
        print(f"fade first touch of ({lo}, {hi}]: {len(j):,} of {len(f):,} markets filled, median wait {res['fade'][f'{lo}-{hi}']['median_wait_min']:.0f} min, "
              f"net return on stake {100*r[0]:+.1f}% [{100*r[1]:+.1f}, {100*r[2]:+.1f}]")

    f = g[(g.p > 0.6) & (g.p <= 0.9)].groupby("market_id").head(1)
    f = f[f.k >= 20]
    for name, s in (("isolated_spike", (f.after - f.p) < -0.15), ("sustained", (f.after - f.p).abs() <= 0.05),
                    ("small_jump", f.jump < 0.05), ("big_jump", f.jump > 0.2)):
        x = f[s]
        b = diff_ci((x.y - x.p).to_numpy(), np.ones(len(x)), x.event_id.to_numpy(), 600)
        c = diff_ci((x.y - x.after).to_numpy(), np.ones(len(x)), x.event_id.to_numpy(), 600)
        res["anatomy"][name] = {"markets": int(len(x)), "share": float(len(x) / len(f)), "outcome_minus_trigger": b[:3], "outcome_minus_next5": c[:3]}
        print(f"  {name:15s} {100*len(x)/len(f):4.0f}% of first touches: outcome minus trigger price {b[0]:+.3f} [{b[1]:+.3f}, {b[2]:+.3f}], minus the next five fills {c[0]:+.3f} [{c[1]:+.3f}, {c[2]:+.3f}]")
    json.dump(res, open("results/tables/e3b_first_touch.json", "w"), indent=1)


if __name__ == "__main__":
    main()
