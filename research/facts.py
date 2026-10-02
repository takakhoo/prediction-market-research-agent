"""One source of truth for every number quoted in the README and the paper.

`facts()` reads results/tables/*.json and returns formatted strings. `python -m research.facts`
renders README.md from research/README.template.md and writes paper/numbers.tex, so prose cannot
drift from the tables.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

T = Path("results/tables")


def _load(name):
    return json.load(open(T / f"{name}.json"))


def pct(x, d=1):
    return f"{100 * x:+.{d}f}%"


def pct_ci(r, d=1):
    return f"{100 * r[0]:+.{d}f}% ({100 * r[1]:+.{d}f} to {100 * r[2]:+.{d}f})"


def pts_ci(r, d=1):
    return f"{100 * r[0]:+.{d}f} ({100 * r[1]:+.{d}f} to {100 * r[2]:+.{d}f})"


def mag_ci(r, d=1, unit=""):
    """Magnitude with interval, for sentences whose wording already carries the sign."""
    lo, hi = sorted((abs(100 * r[1]), abs(100 * r[2])))
    if r[1] * r[2] < 0:  # interval crosses zero: keep the signs
        return f"{100 * r[0]:+.{d}f}{unit} ({100 * r[1]:+.{d}f} to {100 * r[2]:+.{d}f})"
    return f"{abs(100 * r[0]):.{d}f}{unit} ({lo:.{d}f} to {hi:.{d}f})"


def facts() -> dict:
    f = {}
    # dataset totals come from the raw pulls when they are on disk, otherwise from the committed summary
    summary = T / "dataset.json"
    if Path("research/data/derived/markets.parquet").exists():
        import glob
        m = pd.read_parquet("research/data/derived/markets.parquet", columns=["market_id", "volume"])
        q_ids = set()
        for fn in glob.glob("research/data/raw/prices*/ids_*.parquet"):
            q_ids.update(pd.read_parquet(fn).market_id.tolist())
        json.dump({"markets": int(len(m)), "volume_usd": float(m.volume.sum()), "quote_markets": len(q_ids)}, open(summary, "w"), indent=1)
    d = json.load(open(summary))
    f["nMarkets"] = f"{d['markets']:,}"
    f["volumeB"] = f"{d['volume_usd'] / 1e9:.0f}"
    f["quoteMarketsK"] = f"{d['quote_markets'] / 1e3:.0f}"

    e3 = _load("e3_maker_taker")
    a = e3["all"]
    f["tapeFills"] = f"{a['fills'] / 1e6:.1f} million"
    f["tapeMarkets"] = f"{a['markets']:,}"
    f["tapeUsdB"] = f"{a['taker_usd'] / 1e9:.2f}"
    f["takerNet"] = pct_ci(a["taker_net"], 2)
    u = e3["by_category"]["crypto_updown"]
    f["updownTakerNet"] = pct_ci(u["taker_net"], 2)
    f["updownTakerLoss"] = mag_ci(u["taker_net"], 2, "%")
    f["updownFee"] = f"{100 * u['fee_rate_paid']:.2f}%"
    fe = e3["favorite_first_entry"]
    f["firstEntryMid"] = pct_ci(fe["0.7-0.85"]["gross"], 2)
    f["firstEntryMidN"] = f"{fe['0.7-0.85']['markets']:,}"
    f["firstEntryHigh"] = pct_ci(fe["0.85-0.95"]["gross"], 2)
    f["firstEntryHighN"] = f"{fe['0.85-0.95']['markets']:,}"

    e1 = _load("e1_e2_calibration")
    lt = e1["e1"]["long_tail_yes_no"]
    f["dormantShare"] = f"{100 * e1['e1']['all']['share_dormant']:.0f}%"
    f["dormantGap"] = f"{-100 * lt['dormant']['outcome_minus_price_0.4_0.6']:.0f}"
    f["activeGap"] = f"{-100 * lt['active']['outcome_minus_price_0.4_0.6']:.0f}"
    f["dormantZone"] = f"{100 * e1['e1']['all']['dormant']['share_in_0.4_0.6']:.0f}%"
    f["activeZone"] = f"{100 * e1['e1']['all']['active']['share_in_0.4_0.6']:.0f}%"
    bc = e1["e2"]["by_category"]
    for c in ("sports", "politics", "crypto", "weather", "finance", "mentions", "geopolitics"):
        r = bc[c]
        f["slope" + c.capitalize()] = f"{r['slope']:.2f} ({r['slope_ci'][0]:.2f} to {r['slope_ci'][1]:.2f})"
    lf = e1["e2"]["by_life_fraction"]
    f["slopeEarly"] = f"{lf['0-0.15']['slope']:.2f}"
    f["slopeLate"] = f"{lf['0.75-1.0']['slope']:.2f}"
    f["brierOverall"] = f"{e1['e2']['overall']['brier']:.3f}"

    b = _load("e3b_first_touch")
    f["ftMarkets"] = f"{b['markets']:,}"
    f["ftHigh"] = pts_ci(b["buckets"]["0.8-0.9"]["first_touch"])
    f["pooledHigh"] = pts_ci(b["buckets"]["0.8-0.9"]["pooled"])
    f["ftHighMag"] = mag_ci(b["buckets"]["0.8-0.9"]["first_touch"])
    f["pooledHighMag"] = mag_ci(b["buckets"]["0.8-0.9"]["pooled"])
    f["spikeGapMag"] = mag_ci(b["anatomy"]["isolated_spike"]["outcome_minus_trigger"], 0)
    f["sustainedGapMag"] = mag_ci(b["anatomy"]["sustained"]["outcome_minus_next5"])
    f["ftLow"] = pts_ci(b["buckets"]["0.02-0.1"]["first_touch"])
    f["fadeMid"] = pct_ci(b["fade"]["0.6-0.8"]["return_on_stake"])
    f["fadeMidN"] = f"{b['fade']['0.6-0.8']['markets']:,}"
    f["fadeHigh"] = pct_ci(b["fade"]["0.8-0.98"]["return_on_stake"])
    f["fadeHighN"] = f"{b['fade']['0.8-0.98']['markets']:,}"
    f["fadeWait"] = f"{b['fade']['0.6-0.8']['median_wait_min']:.0f}"
    if "from_2026_04" in b["fade"]["0.6-0.8"]:
        f["fadeMidLate"] = pct_ci(b["fade"]["0.6-0.8"]["from_2026_04"]["return_on_stake"])
        f["fadeHighLate"] = pct_ci(b["fade"]["0.8-0.98"]["from_2026_04"]["return_on_stake"])
        f["fadeMidBase"] = pct_ci(b["fade"]["0.6-0.8"]["untriggered_baseline"]["return_on_stake"])
        f["fadeHighBase"] = pct_ci(b["fade"]["0.8-0.98"]["untriggered_baseline"]["return_on_stake"])
    f["fadeFillUsd"] = f"{b['fade']['0.6-0.8']['fill_usd_median']:.0f}"
    f["fadeTotalK"] = f"{(b['fade']['0.6-0.8']['fill_usd_total'] + b['fade']['0.8-0.98']['fill_usd_total']) / 1e3:.0f}"
    f["spikeShare"] = f"{100 * b['anatomy']['isolated_spike']['share']:.0f}%"
    f["spikeGap"] = pts_ci(b["anatomy"]["isolated_spike"]["outcome_minus_trigger"], 0)
    f["sustainedGap"] = pts_ci(b["anatomy"]["sustained"]["outcome_minus_next5"])

    e4 = _load("e4_crypto_options")
    en = e4["endorsed"]
    f["encPrice"] = f"{e4['encompass_threshold']['w_price']:.2f}"
    f["encModel"] = f"{e4['encompass_threshold']['w_model']:.2f} ({e4['encompass_threshold']['w_model_ci'][0]:.2f} to {e4['encompass_threshold']['w_model_ci'][1]:.2f})"
    f["encUpdown"] = f"{e4['encompass_updown']['w_model']:.2f} ({e4['encompass_updown']['w_model_ci'][0]:.2f} to {e4['encompass_updown']['w_model_ci'][1]:.2f})"
    for lag, tag in ((60, "One"), (300, "Five"), (900, "Fifteen"), (3600, "Sixty")):
        f["backed" + tag] = pct_ci(en[f"lag{lag}s_endorsed_0.1"]["taker_net_return"])
        f["opposed" + tag] = pct_ci(en[f"lag{lag}s_opposed_0.1"]["taker_net_return"])
    f["opposedOneLoss"] = mag_ci(en["lag60s_opposed_0.1"]["taker_net_return"], 1, "%")
    f["backedMarkets"] = f"{en['lag60s_endorsed_0.1']['markets']:,}"
    f["backedStakeM"] = f"{en['lag60s_endorsed_0.1']['stake'] / 1e6:.1f}"
    f["displayedRule"] = pct_ci(e4["displayed_price_rule"]["return"], 0)
    q = e4["by_quarter"]
    last = sorted(k for k in q if "endorsed" in q[k])[-1]
    f["lastQuarter"] = last
    f["lastQuarterEndorsed"] = pct_ci(q[last]["endorsed"]["return"])
    iv = e4["implied_vol"]
    f["ivRatioLow"] = f"{min(v['implied_over_realized'] for v in iv.values()):.2f}"
    f["ivRatioHigh"] = f"{max(v['implied_over_realized'] for v in iv.values()):.2f}"
    thr_m = max(v["markets"] for v in e4["brier_threshold"].values())
    f["thrMarkets"] = f"{thr_m:,}"

    e9 = _load("e9_stock_options")
    f["stockMarkets"] = f"{e9['markets']:,}"
    f["stockEncModel"] = f"{e9['encompass']['w_model']:.2f} ({e9['encompass']['w_model_ci'][0]:.2f} to {e9['encompass']['w_model_ci'][1]:.2f})"
    f["stockOpposed"] = pct_ci(e9["endorsed"]["lag0s_opposed_0.1"]["taker_net_return"])
    f["stockOpposedLoss"] = mag_ci(e9["endorsed"]["lag0s_opposed_0.1"]["taker_net_return"], 1, "%")
    f["stockOpposedStaleLoss"] = mag_ci(e9["endorsed"]["lag14400s_opposed_0.1"]["taker_net_return"], 1, "%")
    f["stockEndorsed"] = pct_ci(e9["endorsed"]["lag0s_endorsed_0.1"]["taker_net_return"])
    f["stockOpposedStale"] = pct_ci(e9["endorsed"]["lag14400s_opposed_0.1"]["taker_net_return"])

    e6 = _load("e6_backtest")
    c = e6["crypto_lag840"]
    f["replayAll"] = pct(c["all"]["return_on_stake"])
    f["replaySharpe"] = f"{c['all']['sharpe_annual']:.2f}"
    f["replayT"] = f"{c['all']['t_stat']:.2f}"
    f["replayDSR"] = f"{c['all']['deflated_sharpe_prob']:.2f}"
    f["replayConfirm"] = pct(c["confirmation"]["return_on_stake"])
    f["replayConfirmT"] = f"{c['confirmation']['t_stat']:.2f}"
    f["replayCapitalK"] = f"{c['all']['peak_capital'] / 1e3:.0f}"
    f["replayPnlK"] = f"{c['all']['pnl'] / 1e3:.0f}"
    s = e6["stocks_lag3600"]
    f["stockReplaySharpe"] = f"{s['all']['sharpe_annual']:.2f}"
    f["stockReplayDSR"] = f"{s['all']['deflated_sharpe_prob']:.2f}"
    f["stockReplayAll"] = pct(s["all"]["return_on_stake"])
    f["stockReplayCapitalK"] = f"{s['all']['peak_capital'] / 1e3:.0f}"
    f["stockReplaySelect"] = pct(s["selection"]["return_on_stake"])
    f["stockReplayConfirm"] = pct(s["confirmation"]["return_on_stake"])

    e7 = _load("e7_wallets")
    f["wallets"] = f"{e7['wallets']:,}"
    f["firstTimers"] = pct_ci(e7["first_timers"]["net_return"], 2)
    f["seasoned"] = pct_ci(e7["seasoned"]["net_return"], 2)

    e8 = _load("e8_llm")
    f["llmN"] = str(e8["n_questions"])
    f["llmMarket"] = f"{e8['market_brier']:.3f}"
    f["llmBase"] = f"{e8['always_base_rate_brier']:.3f}"
    for k in ("fable", "sonnet", "haiku"):
        f["llmBlind" + k.capitalize()] = f"{e8['models'][k + '_A']['brier']:.3f}"
        f["llmPrice" + k.capitalize()] = f"{e8['models'][k + '_B']['brier']:.3f}"

    e5 = _load("e5_model")
    f["modelTestMarkets"] = f"{e5['all']['markets']:,}"
    f["modelMarketBrier"] = f"{e5['all']['market']['brier']:.4f}"
    for key, tag in (("platt", "Platt"), ("isotonic", "Isotonic"), ("res_flow_wallets", "ResFlow"), ("res_full", "ResFull"), ("fair_blend", "Blend"), ("quote_mid", "Mid")):
        for split, st in (("all", "All"), ("holdout", "Hold")):
            r = e5[split][key]
            f[f"skill{tag}{st}"] = f"{r['skill_pct']:+.2f}%"
            f[f"dBrier{tag}{st}"] = f"{r['d_brier']:+.5f} ({r['ci'][0]:+.5f} to {r['ci'][1]:+.5f})"
    pl = e5["price_linked_only"]
    f["plMarkets"] = f"{pl['markets']:,}"
    f["plSkillFair"] = f"{pl['fair_value']['skill_pct']:+.1f}%"
    f["plSkillBlend"] = f"{pl['fair_blend']['skill_pct']:+.1f}%"
    pm = e5["price_linked_vs_midpoint"]
    f["plMidFair"] = f"{pm['fair_value']['skill_pct']:+.1f}%"
    f["plMidBlend"] = f"{pm['fair_blend']['skill_pct']:+.1f}%"
    f["plMidBlendCI"] = f"{pm['fair_blend']['d_brier']:+.5f} ({pm['fair_blend']['ci'][0]:+.5f} to {pm['fair_blend']['ci'][1]:+.5f})"
    ph = e5["price_linked_holdout"]
    f["plHoldBlend"] = f"{ph['fair_blend']['skill_pct']:+.1f}%"
    return f


def main():
    f = facts()
    tpl = Path("research/README.template.md").read_text()
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", tpl)) - set(f))
    if missing:
        raise SystemExit(f"README template uses unknown facts: {missing}")
    Path("README.md").write_text(re.sub(r"\{\{(\w+)\}\}", lambda mt: f[mt[1]], tpl))
    tex = "".join(f"\\newcommand{{\\{k}}}{{{v.replace('%', chr(92) + '%').replace('$', chr(92) + '$')}}}\n" for k, v in sorted(f.items()))
    Path("paper/numbers.tex").write_text("% Generated by python -m research.facts. Do not edit.\n" + tex)
    print(f"rendered README.md and paper/numbers.tex from {len(f)} facts")


if __name__ == "__main__":
    main()
