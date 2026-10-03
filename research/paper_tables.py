"""Write the paper's tables (paper/tables/*.tex) from results/tables/*.json and the market table."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

T, OUT = Path("results/tables"), Path("paper/tables")
CATS = ["sports", "crypto_updown", "crypto", "weather", "finance", "politics", "mentions", "culture", "economy", "geopolitics", "tech", "other"]
NAMES = {"crypto_updown": "crypto up/down", "crypto": "crypto thresholds and other crypto", "tech": "technology"}


def load(n):
    return json.load(open(T / f"{n}.json"))


def ci(r, scale=100, d=1, unit=""):
    return f"{scale * r[0]:+.{d}f}{unit} & ({scale * r[1]:+.{d}f}, {scale * r[2]:+.{d}f})"


def ci2(pt, lo_hi, scale=1, d=4):
    return f"{scale * pt:+.{d}f} & ({scale * lo_hi[0]:+.{d}f}, {scale * lo_hi[1]:+.{d}f})"


def tab(name, caption, label, header, rows, notes, align):
    body = " \\\\\n".join(rows)
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.tex").write_text(
        f"\\begin{{table}}[t]\n\\caption{{{caption}}}\n\\label{{{label}}}\n\\centering\\footnotesize\\setlength{{\\tabcolsep}}{{4pt}}\n\\resizebox{{\\linewidth}}{{!}}{{\\begin{{tabular}}{{{align}}}\n\\toprule\n{header} \\\\\n\\midrule\n{body} \\\\\n\\bottomrule\n\\end{{tabular}}}}\n\n\\smallskip\n\\begin{{minipage}}{{0.96\\linewidth}}\\footnotesize {notes}\\end{{minipage}}\n\\end{{table}}\n")


def summary():
    from research.lib.panel import prepare_markets
    m = prepare_markets(pd.read_parquet("research/data/derived/markets.parquet"))
    e3 = load("e3_maker_taker")["by_category"]
    tot_v = m.volume.sum()
    rows = []
    for c in CATS:
        g = m[m.category == c]
        f = e3.get(c, {"markets": 0, "fills": 0, "taker_usd": 0})
        rows.append(f"{NAMES.get(c, c)} & {len(g):,} & {100 * g.volume.sum() / tot_v:.1f} & {100 * g.y.mean():.1f} & {f['markets']:,} & {f['fills'] / 1e6:.2f} & {f['taker_usd'] / 1e6:.0f}")
    a = load("e3_maker_taker")["all"]
    rows.append(f"\\midrule all & {len(m):,} & 100 & {100 * m.y.mean():.1f} & {a['markets']:,} & {a['fills'] / 1e6:.2f} & {a['taker_usd'] / 1e6:.0f}")
    tab("summary", "The universe and the fill sample by category.", "tab:summary",
        "Category & Markets & Volume share (\\%) & Outcome 0 wins (\\%) & Markets with fills & Fills (M) & Taker stake (\\$M)", rows,
        "Resolved binary markets with at least \\$1,000 of volume, 2020 to October 2026. Outcome 0 is Yes in Yes/No markets. The fill sample is stratified: all crypto threshold contracts after 2025 were queued first, then finance, then other non-sports categories, then a uniform draw of everything, interleaved; the download stopped at the cutoff with the sample as shown.", "lrrrrrr")


def calibration():
    e = load("e1_e2_calibration")["e2"]
    rows = []
    for c, r in e["by_category"].items():
        rows.append(f"{NAMES.get(c, c)} & {r['markets']:,} & {r['brier']:.3f} & {r['mean_p']:.3f} & {r['mean_y']:.3f} & {r['slope']:.2f} & ({r['slope_ci'][0]:.2f}, {r['slope_ci'][1]:.2f}) & {r['intercept']:+.2f} & ({r['intercept_ci'][0]:+.2f}, {r['intercept_ci'][1]:+.2f})")
    for k, r in e["by_life_fraction"].items():
        rows.append(f"life fraction {k} & {r['markets']:,} & {r['brier']:.3f} & {r['mean_p']:.3f} & {r['mean_y']:.3f} & {r['slope']:.2f} & ({r['slope_ci'][0]:.2f}, {r['slope_ci'][1]:.2f}) & {r['intercept']:+.2f} & ({r['intercept_ci'][0]:+.2f}, {r['intercept_ci'][1]:+.2f})")
    tab("calibration", "Calibration of the last traded price at scheduled snapshots.", "tab:calibration",
        "Sample & Markets & Brier & Mean price & Mean outcome & Slope $b$ & 95\\% CI & Intercept $a$ & 95\\% CI", rows,
        "Logistic recalibration $\\Pr(y=1)=\\sigma(a+b\\,\\mathrm{logit}\\,p)$ fitted with one weight per market. $b<1$ means prices are too extreme. Snapshots with a trade in the prior six hours or 10\\% of the market's life. Intervals from 300 bootstrap draws that resample events.", "lrrrrrrrr")


def takers():
    e = load("e3_maker_taker")
    rows = [f"{NAMES.get(c, c)} & {r['markets']:,} & {r['taker_usd'] / 1e6:.0f} & {ci(r['taker_gross'], 100, 2)} & {ci(r['taker_net'], 100, 2)} & {100 * r['fee_rate_paid']:.2f}"
            for c, r in e["by_category"].items() if r["markets"] >= 100]
    a = e["all"]
    rows.append(f"\\midrule all & {a['markets']:,} & {a['taker_usd'] / 1e6:.0f} & {ci(a['taker_gross'], 100, 2)} & {ci(a['taker_net'], 100, 2)} & {100 * a['fee_rate_paid']:.2f}")
    tab("takers", "Taker returns on dollars staked, by category.", "tab:takers",
        "Category & Markets & Stake (\\$M) & Gross (\\%) & 95\\% CI & Net of fees (\\%) & 95\\% CI & Fees (\\% of stake)", rows,
        "Return is dollars won over dollars staked across every fill in the sample; the maker's gross return is the negative of the taker's. Intervals from 1,000 bootstrap draws that resample events.", "lrrrrrrr")


def options():
    e = load("e4_crypto_options")
    rows = [f"{h} & {r['markets']:,} & {r['fills']:,} & {r['brier_fill']:.4f} & {r['brier_model']:.4f} & {ci2(r['model_minus_fill'], r['ci'])}" for h, r in e["brier_threshold"].items()]
    rows.append("\\midrule \\multicolumn{7}{l}{\\emph{Up/down contracts}}")
    rows += [f"{h} & {r['markets']:,} & {r['fills']:,} & {r['brier_fill']:.4f} & {r['brier_model']:.4f} & {ci2(r['model_minus_fill'], r['ci'])}" for h, r in e["brier_updown"].items()]
    tab("options", "Fill price against the option model, scored at the same fills.", "tab:options",
        "Time to expiry & Markets & Fills & Brier, fill & Brier, model & Difference & 95\\% CI", rows,
        "Threshold contracts in the top block. One weight per market; intervals from 600 bootstrap draws that resample expiry dates. Negative differences favor the model.", "lrrrrrr")


def endorsed():
    e = load("e4_crypto_options")["endorsed"]
    rows = []
    for lag, lab in ((60, "1 min"), (300, "5 min"), (900, "15 min"), (3600, "60 min")):
        for th in (0.05, 0.10):
            a, b = e[f"lag{lag}s_endorsed_{th}"], e[f"lag{lag}s_opposed_{th}"]
            rows.append(f"{lab} & {th:.2f} & {a['markets']:,} & {a['stake'] / 1e6:.1f} & {ci(a['taker_net_return'])} & {b['stake'] / 1e6:.1f} & {ci(b['taker_net_return'])}")
    tab("endorsed", "Taker return after fees on crypto threshold fills the option model endorses or opposes.", "tab:endorsed",
        "Spot age & Bar & Markets & Endorsed stake (\\$M) & Return (\\%) & 95\\% CI & Opposed stake (\\$M) & Return (\\%) & 95\\% CI", rows,
        "A fill is endorsed when the model values the side bought at least the bar above its price plus the fee, and opposed in the mirror case. Spot age is how old the model's last candle is. Intervals resample expiry dates.", "lrrrrrrrr")


def models():
    e = load("e5_model")
    names = [("quote_mid", "Quote midpoint"), ("vwap10", "Ten-fill average price"), ("platt", "Platt recalibration"), ("platt_by_category", "Platt by category"),
             ("isotonic", "Isotonic recalibration"), ("res_flow_wallets", "Residual trees: path, flow, wallets"), ("res_full", "Residual trees plus option value"), ("fair_blend", "Price and option value blend")]
    rows = []
    for k, lab in names:
        cells = [f"{e[s][k]['skill_pct']:+.2f} & ({-100 * e[s][k]['ci'][1] / e[s]['market']['brier']:+.2f}, {-100 * e[s][k]['ci'][0] / e[s]['market']['brier']:+.2f})" for s in ("all", "holdout", "price_linked_only")]
        rows.append(f"{lab} & " + " & ".join(cells))
    pl = e["price_linked_only"]["fair_value"]
    rows.append(f"Option value alone & & & & & {pl['skill_pct']:+.2f} & ({-100 * pl['ci'][1] / e['price_linked_only']['market']['brier']:+.2f}, {-100 * pl['ci'][0] / e['price_linked_only']['market']['brier']:+.2f})")
    tab("models", "Brier skill of each challenger relative to the last traded price, walk-forward.", "tab:models",
        "Challenger & All months & 95\\% CI & May to Sep 2026 & 95\\% CI & Price-linked & 95\\% CI", rows,
        f"Skill is the percentage reduction in Brier score relative to the price; positive beats the price. All months: {e['all']['markets']:,} test markets, price Brier {e['all']['market']['brier']:.4f}. Last five months: {e['holdout']['markets']:,} markets. Price-linked: {e['price_linked_only']['markets']:,} crypto and single-stock threshold markets. Two-month test blocks; a model tested in a block trains only on markets that resolved before it. Intervals resample events.", "lrrrrrr")


def llm():
    e = load("e8_llm")
    rows = []
    for k, lab in (("haiku", "Claude Haiku 4.5"), ("sonnet", "Claude Sonnet"), ("fable", "Claude Fable 5.1")):
        for cond, cl in (("A", "question only"), ("B", "question and price")):
            r = e["models"][f"{k}_{cond}"]
            rows.append(f"{lab} & {cl} & {r['brier']:.3f} & {r['brier_minus_market']:+.4f} & ({r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}) & {r['corr_with_market']:.2f} & {r['weight_on_llm_given_market']:+.2f} & ({r['weight_ci'][0]:+.2f}, {r['weight_ci'][1]:+.2f})")
    tab("llm", f"Language-model forecasts on {e['n_questions']} questions opened after the models' training cutoffs.", "tab:llm",
        "Model & Sees & Brier & vs market & 95\\% CI & Corr. with price & Weight given price & 95\\% CI", rows,
        f"Market Brier {e['market_brier']:.3f}; a constant forecast at the base rate scores {e['always_base_rate_brier']:.3f}. The weight is the coefficient on the model's log-odds in a logistic regression of the outcome on the log-odds of the price and of the model. Intervals resample questions, one per event.", "llrrrrrr")


def replay():
    e = load("e6_backtest")
    rows = []
    for key, lab in (("crypto_lag0", "Crypto, 1-min spot"), ("crypto_lag840", "Crypto, 15-min spot"), ("stocks_lag0", "Stocks, current bar"), ("stocks_lag3600", "Stocks, hour-old bar")):
        for per, pl in (("all", "all"), ("selection", "before Apr 2026"), ("confirmation", "Apr to Sep 2026")):
            r = e[key][per]
            rows.append(f"{lab} & {pl} & {r['markets']:,} & {r['stake'] / 1e3:.0f} & {r['pnl'] / 1e3:+.0f} & {100 * r['return_on_stake']:+.1f} & {r['peak_capital'] / 1e3:.0f} & {r['sharpe_annual']:.2f} & {r['t_stat']:.2f} & {r['deflated_sharpe_prob']:.2f}")
    tab("replay", "Capital-constrained replay of the option-model rule, \\$200 cap per fill.", "tab:replay",
        "Rule & Period & Markets & Stake (\\$k) & Profit (\\$k) & Return (\\%) & Peak capital (\\$k) & Sharpe & $t$ & DSR", rows,
        "Profit is booked on the expiry day; daily return is profit over the largest stake outstanding on any day; Sharpe is annualized. $t$ is the daily-series $t$-statistic. DSR is the deflated Sharpe probability against the best of 24 skill-free variants. The ten-cent bar was fixed on contracts expiring before April 2026.", "llrrrrrrrr")


def first_touch():
    e = load("e3b_first_touch")
    rows = [f"{k} & {r['markets']:,} & {ci(r['pooled'])} & {ci(r['first_touch'])}" for k, r in e["buckets"].items()]
    tab("firsttouch", "Outcome minus Yes price at fills in long-tail Yes/No markets, two sampling rules.", "tab:firsttouch",
        "Yes price band & Markets & Pooled (pts) & 95\\% CI & First touch (pts) & 95\\% CI", rows,
        f"{e['markets']:,} Yes/No markets outside sports, crypto, and weather. Pooled: every fill, share-weighted. First touch: the first fill of each market inside the band. Both rules use only the past, so both average zero when fill prices are fair. Intervals resample events.", "lrrrrr")


if __name__ == "__main__":
    for fn in (summary, calibration, takers, options, endorsed, models, llm, replay, first_touch):
        fn()
    print("wrote", sorted(p.name for p in OUT.glob("*.tex")))
