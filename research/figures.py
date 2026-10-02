"""Render every figure in results/figures from results/tables/*.json. No experiment logic lives here."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

T = Path("results/tables")
F = Path("results/figures")
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "font.size": 10,
    "font.family": "DejaVu Sans", "axes.edgecolor": BASE, "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "legend.frameon": False, "figure.dpi": 200,
})


def load(name):
    return json.load(open(T / f"{name}.json"))


def save(fig, name):
    F.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(F / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def whisk(ax, x, pt, lo, hi, color, horizontal=False, **kw):
    pt, lo, hi = map(np.asarray, (pt, lo, hi))
    if horizontal:
        ax.errorbar(pt, x, xerr=[pt - lo, hi - pt], fmt="o", color=color, ms=5, lw=1.4, capsize=0, **kw)
    else:
        ax.errorbar(x, pt, yerr=[pt - lo, hi - pt], fmt="o", color=color, ms=5, lw=1.4, capsize=0, **kw)


def fig_dataset():
    from research.lib.panel import prepare_markets
    m = prepare_markets(pd.read_parquet("research/data/derived/markets.parquet"))
    m["q"] = pd.to_datetime(m.t_close, unit="s").dt.to_period("Q").astype(str)
    grp = np.select([m.category == "sports", m.category == "crypto_updown", m.category == "weather"],
                    ["Sports", "Crypto up/down", "Weather"], "Everything else")
    tab = m.assign(g=grp).groupby(["q", "g"]).size().unstack(fill_value=0)
    tab = tab[tab.index >= "2024Q1"][["Sports", "Crypto up/down", "Weather", "Everything else"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    bottom = np.zeros(len(tab))
    for col, c in zip(tab.columns, (BLUE, ORANGE, AQUA, YELLOW)):
        ax.bar(tab.index, tab[col] / 1e3, bottom=bottom, color=c, width=0.72, label=col, edgecolor=SURFACE, linewidth=1.2)
        bottom += tab[col].to_numpy() / 1e3
    ax.set_ylabel("resolved markets per quarter (thousands)")
    ax.set_title(f"{len(m):,} resolved markets, ${m.volume.sum()/1e9:.0f}B traded")
    ax.legend(ncol=4, loc="upper left", fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="x", visible=False)
    save(fig, "dataset")


def fig_midpoint():
    r = load("e1_e2_calibration")["e1"]["long_tail_yes_no"]
    fig, ax = plt.subplots(figsize=(4.8, 4.4))
    ax.plot([0, 1], [0, 1], color=BASE, lw=1, zorder=1)
    for key, c, lab in (("active", BLUE, "traded in the last 24 h"), ("dormant", ORANGE, "no trade in the last 24 h")):
        t = pd.DataFrame(r[key]["table"]).dropna()
        ax.plot(t.mean_p, t.mean_y, "-o", color=c, lw=2, ms=5, label=lab, zorder=3)
    ax.set_xlabel("displayed price (quote midpoint)")
    ax.set_ylabel("share that resolved Yes")
    ax.set_title("Dormant quotes fake a Yes bias")
    ax.annotate(f"{100*r['share_dormant']:.0f}% of snapshots are dormant;\nnear 0.5 they resolve Yes\n{-100*r['dormant']['outcome_minus_price_0.4_0.6']:.0f} points less often than priced",
                xy=(0.5, 0.5 + r["dormant"]["outcome_minus_price_0.4_0.6"]), xytext=(0.52, 0.12), fontsize=8, color=INK2,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlim(0, 1), ax.set_ylim(0, 1)
    save(fig, "midpoint_artifact")


def fig_estimators():
    r = load("e3b_first_touch")["buckets"]
    keys = list(r)
    x = np.arange(len(keys))
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.axhline(0, color=BASE, lw=1)
    for off, key, c, lab in ((-0.14, "pooled", BLUE, "every fill, share-weighted"), (0.14, "first_touch", ORANGE, "first fill in the band, one per market")):
        v = np.array([r[k][key] for k in keys]) * 100
        whisk(ax, x + off, v[:, 0], v[:, 1], v[:, 2], c, label=lab)
    ax.set_xticks(x, [k.replace("-", "–") for k in keys], fontsize=8)
    ax.set_xlabel("Yes price at the fill")
    ax.set_ylabel("outcome minus price (points)")
    ax.set_title("Same fills, opposite conclusions about favorites")
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(axis="x", visible=False)
    save(fig, "estimators")


def fig_maker_taker():
    r = load("e3_maker_taker")["by_category"]
    rows = sorted(((c, *v["taker_net"], v["fee_rate_paid"]) for c, v in r.items() if v["markets"] >= 150), key=lambda z: z[1])
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.axvline(0, color=BASE, lw=1)
    y = np.arange(len(rows))
    v = np.array([z[1:4] for z in rows]) * 100
    whisk(ax, y, v[:, 0], v[:, 1], v[:, 2], BLUE, horizontal=True)
    for yi, z in zip(y, rows):
        ax.text(v[yi, 2] + 0.25, yi, f"fees {100*z[4]:.1f}%", va="center", fontsize=7, color=MUTED)
    ax.set_yticks(y, [z[0].replace("_", " ") for z in rows])
    ax.set_xlabel("taker return on dollars staked, after fees (%)")
    ax.set_title("Takers break even almost everywhere; fees sink crypto up/down")
    ax.grid(axis="y", visible=False)
    save(fig, "maker_taker")


def fig_options_brier():
    r = load("e4_crypto_options")
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4), sharey=False)
    for ax, key, title in ((axes[0], "brier_threshold", "Threshold contracts: a tie"), (axes[1], "brier_updown", "Up/down contracts: the market wins")):
        d = r[key]
        x = np.arange(len(d))
        ax.plot(x, [v["brier_fill"] for v in d.values()], "-o", color=BLUE, lw=2, ms=5, label="fill price")
        ax.plot(x, [v["brier_model"] for v in d.values()], "-o", color=ORANGE, lw=2, ms=5, label="option model")
        ax.set_xticks(x, list(d), fontsize=8)
        ax.set_xlabel("time to expiry at the fill")
        ax.set_title(title)
        ax.set_ylim(0)
    axes[0].set_ylabel("Brier score (lower is better)")
    axes[0].legend(fontsize=8, loc="upper left")
    save(fig, "options_brier")


def fig_edge_decay():
    r = load("e4_crypto_options")
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.5))
    ax = axes[0]
    ax.axhline(0, color=BASE, lw=1)
    ages = [60, 300, 900, 3600]
    for off, label, c in ((-0.08, "endorsed", BLUE), (0.08, "opposed", ORANGE)):
        v = np.array([r["endorsed"][f"lag{a}s_{label}_0.1"]["taker_net_return"] for a in ages]) * 100
        whisk(ax, np.arange(4) + off, v[:, 0], v[:, 1], v[:, 2], c, label=f"fills the model {'endorses' if label == 'endorsed' else 'opposes'}")
    ax.set_xticks(range(4), ["1 min", "5 min", "15 min", "60 min"])
    ax.set_xlabel("age of the spot price the model sees")
    ax.set_ylabel("taker return after fees (%)")
    ax.set_title("The edge fades as the model's data ages")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(axis="x", visible=False)
    ax = axes[1]
    ax.axhline(0, color=BASE, lw=1)
    q = {k: v for k, v in r["by_quarter"].items() if "endorsed" in v}
    v = np.array([q[k]["endorsed"]["return"] for k in q]) * 100
    whisk(ax, np.arange(len(q)), v[:, 0], v[:, 1], v[:, 2], BLUE)
    for i, k in enumerate(q):
        ax.text(i, v[i, 2] + 2, f"${q[k]['endorsed']['stake']/1e3:.0f}k", ha="center", fontsize=7, color=MUTED)
    ax.set_xticks(range(len(q)), list(q), fontsize=8)
    ax.set_xlabel("settlement quarter (label: endorsed stake)")
    ax.set_title("...and as the market matures")
    ax.grid(axis="x", visible=False)
    save(fig, "edge_decay")


def fig_ladder():
    e4, e6 = load("e4_crypto_options"), load("e6_backtest")
    rows = [("Displayed quote midpoints\n(what a naive backtest reports)", e4["displayed_price_rule"]["return"]),
            ("Real fills, model sees 1-minute-old spot", e4["endorsed"]["lag60s_endorsed_0.1"]["taker_net_return"]),
            ("Real fills, 15-minute-old spot", e4["endorsed"]["lag900s_endorsed_0.1"]["taker_net_return"]),
            ("...capped at $200 per fill, whole sample", [e6["crypto_lag840"]["all"]["return_on_stake"]] * 3),
            ("...confirmation period only (Apr–Sep 2026)", [e6["crypto_lag840"]["confirmation"]["return_on_stake"]] * 3)]
    fig, ax = plt.subplots(figsize=(7.6, 3.3))
    y = np.arange(len(rows))[::-1]
    v = np.array([r[1] for r in rows]) * 100
    ax.barh(y, v[:, 0], color=BLUE, height=0.55)
    has_ci = v[:, 1] != v[:, 2]
    ax.errorbar(v[has_ci, 0], y[has_ci], xerr=[v[has_ci, 0] - v[has_ci, 1], v[has_ci, 2] - v[has_ci, 0]], fmt="none", ecolor=INK2, lw=1.2)
    for yi, val, hi in zip(y, v[:, 0], v[:, 2]):
        ax.text(max(val, hi) + 1.5, yi, f"{val:+.0f}%", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=8.5)
    ax.set_xlabel("return on stake from following the option model's 10-point disagreements (%)")
    ax.set_title("The same rule under each successive control")
    ax.grid(axis="y", visible=False)
    ax.axvline(0, color=BASE, lw=1)
    save(fig, "ladder")


def fig_models():
    r = load("e5_model")
    names = ["quote_mid", "vwap10", "platt", "platt_by_category", "isotonic", "res_flow_wallets", "res_full", "fair_blend"]
    labels = ["quote midpoint", "10-fill average price", "Platt recalibration", "Platt per category", "isotonic recalibration",
              "boosted residual: path, flow, wallets", "boosted residual + option value", "price + option value blend"]
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    ax.axvline(0, color=BASE, lw=1)
    y = np.arange(len(names))[::-1]
    for off, key, c, lab in ((0.14, "all", BLUE, "all test months"), (-0.14, "holdout", ORANGE, "last five months (May\u2013Sep 2026)")):
        v = np.array([[r[key][n]["d_brier"], *r[key][n]["ci"]] for n in names]) / r[key]["market"]["brier"] * 100
        whisk(ax, y + off, v[:, 0], v[:, 1], v[:, 2], c, horizontal=True, label=lab)
    ax.set_yticks(y, labels, fontsize=8.5)
    ax.set_xlabel("Brier score relative to the last traded price (%; left of zero beats the price)")
    ax.set_title("Out-of-time challengers to the price")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="y", visible=False)
    save(fig, "models")


def fig_llm():
    r = load("e8_llm")
    order = [("haiku_A", "Haiku 4.5\nblind"), ("sonnet_A", "Sonnet\nblind"), ("fable_A", "Fable 5.1\nblind"), ("market", "Market\nprice"),
             ("haiku_B", "Haiku 4.5\nsees price"), ("sonnet_B", "Sonnet\nsees price"), ("fable_B", "Fable 5.1\nsees price")]
    vals = [r["market_brier"] if k == "market" else r["models"][k]["brier"] for k, _ in order]
    cols = [ORANGE if k == "market" else BLUE for k, _ in order]
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    ax.bar(range(len(order)), vals, color=cols, width=0.6)
    ax.axhline(r["always_base_rate_brier"], color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(len(order) - 0.55, r["always_base_rate_brier"] + 0.004, "always guess the base rate", fontsize=7.5, color=MUTED, ha="right")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.004, f"{v:.3f}", ha="center", fontsize=8)
    ax.set_xticks(range(len(order)), [l for _, l in order], fontsize=8)
    ax.set_ylabel("Brier score (lower is better)")
    ax.set_title(f"{r['n_questions']} questions opened after every model's training cutoff")
    ax.grid(axis="x", visible=False)
    save(fig, "llm")


def fig_equity():
    r = load("e6_backtest")
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    for key, c, lab in (("crypto_lag840", BLUE, "crypto thresholds, 15-minute-old spot"), ("stocks_lag3600", ORANGE, "single stocks, hour-old bars")):
        cv = r[key]["all"]["curve"]
        ax.plot(pd.to_datetime(np.array(cv["day"]) * 86400, unit="s"), np.array(cv["cum_pnl"]) / 1e3, color=c, lw=2, label=lab)
    ax.axvspan(pd.Timestamp("2026-04-01"), pd.Timestamp("2026-10-01"), color=GRID, alpha=0.6, lw=0)
    ax.text(pd.Timestamp("2026-04-08"), ax.get_ylim()[1] * 0.92, "confirmation period", fontsize=8, color=INK2)
    ax.set_ylabel("cumulative profit ($ thousands, $200 cap per fill)")
    ax.set_title("Replay of the option-model rule on real fills")
    ax.legend(fontsize=8, loc="upper left")
    save(fig, "equity")


def fig_implied_vol():
    r = load("e4_crypto_options")["implied_vol"]
    x = np.arange(len(r))
    fig, ax = plt.subplots(figsize=(5.6, 3.3))
    for key, c, lab in (("implied", BLUE, "implied by Polymarket fills"), ("realized_after", ORANGE, "realized afterwards"), ("dvol", AQUA, "Deribit DVOL")):
        ax.plot(x, [100 * v[key] for v in r.values()], "-o", color=c, lw=2, ms=5, label=lab)
    ax.set_xticks(x, list(r))
    ax.set_xlabel("time to expiry")
    ax.set_ylabel("annualized volatility (%)")
    ax.set_title("No volatility premium in Polymarket crypto strikes")
    ax.legend(fontsize=8)
    save(fig, "implied_vol")


def main():
    for fn in (fig_dataset, fig_midpoint, fig_estimators, fig_maker_taker, fig_options_brier, fig_edge_decay, fig_ladder,
               fig_models, fig_llm, fig_equity, fig_implied_vol):
        try:
            fn()
        except Exception as e:  # a missing table should not block the other figures
            print("skipped", fn.__name__, repr(e)[:120])


if __name__ == "__main__":
    main()
