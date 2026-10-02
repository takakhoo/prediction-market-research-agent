"""Explanatory diagrams and the committed walkthrough sample for the README.

Schematics (pipeline, fill anatomy, option geometry, walk-forward) are drawn from constants.
The two case studies read the fill tape and pick their subject by a fixed rule.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from scipy.special import ndtr

from research.figures import AQUA, BASE, BLUE, GRID, INK, INK2, MUTED, ORANGE, SURFACE, YELLOW, save

LIGHT = {"blue": "#cde2fb", "orange": "#fbdccd", "aqua": "#c9eede", "yellow": "#fbe9bf", "grey": "#efeeea"}


def _box(ax, x, y, w, h, title, body="", color="grey"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02", fc=LIGHT[color], ec=BASE, lw=1))
    ax.text(x + w / 2, y + h - 0.035, title, ha="center", va="top", fontsize=9.5, fontweight="bold", color=INK)
    if body:
        ax.text(x + w / 2, y + h - 0.095, body, ha="center", va="top", fontsize=7.6, color=INK2, linespacing=1.35)


def _arrow(ax, a, b):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=11, lw=1.2, color=MUTED, shrinkA=2, shrinkB=2))


def fig_pipeline():
    d = json.load(open("results/tables/dataset.json"))
    e3 = json.load(open("results/tables/e3_maker_taker.json"))["all"]
    fig, ax = plt.subplots(figsize=(9.6, 4.3))
    ax.set_xlim(-0.015, 1.015), ax.set_ylim(0, 1), ax.axis("off")
    _box(ax, 0.01, 0.56, 0.17, 0.38, "1. Collect", "public endpoints,\nno credentials\n\nmarkets, quotes,\nfills with wallets,\nspot, DVOL, equities", "blue")
    _box(ax, 0.215, 0.56, 0.17, 0.38, "2. Rebuild", f"{d['markets'] / 1e6:.2f}M markets\n{e3['fills'] / 1e6:.1f}M fills\n\nevery fill becomes a\nYes price, a side,\na cost, and a fee", "blue")
    _box(ax, 0.42, 0.56, 0.17, 0.38, "3. Price", "contracts on BTC, ETH,\nSOL, XRP, and stocks\nare digital options\n\nvalue from spot and\ntrailing volatility", "orange")
    _box(ax, 0.625, 0.56, 0.17, 0.38, "4. Sample", "snapshot times fixed\nby each market's\npublished schedule\n\nmodels train only on\nresolved markets", "aqua")
    _box(ax, 0.83, 0.56, 0.16, 0.38, "5. Audit", "every claimed edge\nwalks the ladder\n\ntables, figures,\nREADME and paper\nfrom one source", "yellow")
    for x in (0.18, 0.385, 0.59, 0.795):
        _arrow(ax, (x + 0.002, 0.75), (x + 0.033, 0.75))
    ax.text(0.01, 0.44, "The ladder each edge has to climb down", fontsize=9.5, fontweight="bold", color=INK)
    rungs = ["displayed\nquotes", "prices that\ntraded", "estimators fair\nunder the null", "older\ninformation", "capital limit\nand fees", "confirmation\nperiod"]
    w = 0.145
    for i, r in enumerate(rungs):
        x = 0.01 + i * (w + 0.021)
        ax.add_patch(FancyBboxPatch((x, 0.12 + 0.0), w, 0.22, boxstyle="round,pad=0.01,rounding_size=0.02", fc=LIGHT["grey"], ec=BASE, lw=1))
        ax.text(x + w / 2, 0.23, r, ha="center", va="center", fontsize=8.2, color=INK)
        if i:
            _arrow(ax, (x - 0.021, 0.23), (x - 0.001, 0.23))
    ax.text(0.01, 0.045, "An edge that is still there at the right-hand end is reported as an edge. Everything else is reported as what removed it.", fontsize=8, color=INK2)
    save(fig, "pipeline")


def fig_fill_anatomy():
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.3), gridspec_kw={"width_ratios": [1.45, 1]})
    ax = axes[0]
    ax.axis("off"), ax.set_xlim(0, 1), ax.set_ylim(0, 1)
    ax.set_title("One fill in the feed becomes one position in Yes")
    cols = [0.0, 0.34, 0.52, 0.70, 0.86]
    for x, h in zip(cols, ["what the taker did", "Yes price p", "taker holds", "taker paid", "maker paid"]):
        ax.text(x, 0.86, h, fontsize=8.2, fontweight="bold", color=INK2)
    rows = [("buys Yes at 0.70", "0.70", "Yes", "0.70", "0.30"), ("sells Yes at 0.70", "0.70", "No", "0.30", "0.70"),
            ("buys No at 0.30", "0.70", "No", "0.30", "0.70"), ("sells No at 0.30", "0.70", "Yes", "0.70", "0.30")]
    for i, r in enumerate(rows):
        y = 0.70 - i * 0.16
        ax.add_patch(FancyBboxPatch((-0.01, y - 0.055), 1.0, 0.12, boxstyle="round,pad=0.004,rounding_size=0.015",
                                    fc=LIGHT["blue"] if r[2] == "Yes" else LIGHT["orange"], ec="none"))
        for x, v in zip(cols, r):
            ax.text(x, y, v, fontsize=8.6, color=INK, va="center")
    ax.text(0.0, 0.03, "The side that paid c wins 1 if it is right. Both sides of every fill bought something.", fontsize=7.8, color=INK2)
    ax = axes[1]
    p = np.linspace(0, 1, 201)
    for rate, c, lab in ((0.07, ORANGE, "crypto, rate 0.07"), (0.05, BLUE, "sports, weather, rate 0.05"), (0.04, AQUA, "politics, finance, rate 0.04")):
        ax.plot(p, 100 * rate * p * (1 - p), color=c, lw=2, label=lab)
    ax.set_xlabel("price paid"), ax.set_ylabel("taker fee (cents per share)")
    ax.set_title("Fee = rate x p x (1 - p)")
    ax.legend(fontsize=7.5, loc="lower center")
    save(fig, "fill_anatomy")


def fig_option_geometry():
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.4))
    ax = axes[0]
    s0, k, sig, tau = 100.0, 103.0, 0.5, 2 / 365.25
    v = sig * np.sqrt(tau)
    x = np.linspace(88, 114, 400)
    pdf = np.exp(-((np.log(x / s0) + 0.5 * v * v) ** 2) / (2 * v * v)) / (x * v * np.sqrt(2 * np.pi))
    ax.plot(x, pdf, color=INK2, lw=1.5)
    ax.fill_between(x, 0, pdf, where=x >= k, color=BLUE, alpha=0.35, lw=0)
    ax.axvline(k, color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.axvline(s0, color=MUTED, lw=1)
    prob = ndtr((np.log(s0 / k) - 0.5 * v * v) / v)
    ax.text(k + 0.4, pdf.max() * 0.93, "strike K", fontsize=8, color=MUTED)
    ax.text(s0 - 0.4, pdf.max() * 0.93, "spot S", fontsize=8, color=MUTED, ha="right")
    ax.text(107.2, pdf.max() * 0.30, f"pays $1\nprobability {prob:.2f}", fontsize=8.5, color=INK)
    ax.set_xlabel("price at expiry"), ax.set_yticks([])
    ax.set_title("The contract pays on the shaded area")
    ax.grid(visible=False)
    ax = axes[1]
    s = np.linspace(94, 112, 300)
    for hrs, c in ((48, BLUE), (6, AQUA), (0.5, ORANGE)):
        vv = sig * np.sqrt(hrs / 24 / 365.25)
        ax.plot(s, ndtr((np.log(s / k) - 0.5 * vv * vv) / vv), color=c, lw=2, label=f"{hrs:g} hours left")
    ax.axvline(k, color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.set_xlabel("spot now"), ax.set_ylabel("value of Yes")
    ax.set_title("The same contract as expiry approaches")
    ax.legend(fontsize=8, loc="upper left")
    save(fig, "option_geometry")


def fig_walkforward():
    fig, ax = plt.subplots(figsize=(8.6, 2.9))
    blocks = ["Sep-Oct 25", "Nov-Dec 25", "Jan-Feb 26", "Mar-Apr 26", "May-Jun 26", "Jul-Aug 26", "Sep 26"]
    for i, b in enumerate(blocks):
        y = len(blocks) - 1 - i
        ax.barh(y, i + 2, left=0, color=LIGHT["blue"], height=0.62, edgecolor=SURFACE)
        ax.barh(y, 1, left=i + 2, color=ORANGE if i >= 4 else BLUE, height=0.62, edgecolor=SURFACE)
        ax.text(-0.15, y, b, ha="right", va="center", fontsize=8, color=INK2)
    ax.text(0.15, 0, "train: only markets that had already resolved", va="center", fontsize=8, color=INK2)
    ax.text(len(blocks) + 1.5, 0, "test", va="center", ha="center", fontsize=8, color="white", fontweight="bold")
    ax.text(8.2, 2.6, "last five months:\nno setting was\nchosen on these", fontsize=8, color=INK2, va="center")
    ax.set_xlim(-1.9, 10.6), ax.set_yticks([]), ax.set_xticks([])
    ax.set_title("Walk-forward with purged labels: a model never trains on a market that had not resolved")
    ax.grid(visible=False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    save(fig, "walkforward")


def case_contract():
    """The demo contract: sample for the walkthrough and an annotated still."""
    from research.experiments import e4_crypto_options as e4
    from research.lib.contracts import load_spot
    from research.render_demo import pick

    o = e4.load()
    mid = pick(o)
    g = o[(o.market_id == mid) & (o.tau < 36 * 3600)].sort_values("t")
    c = pd.read_parquet("research/data/derived/crypto_contracts.parquet").set_index("market_id").loc[mid]
    spot = load_spot(c.symbol)
    spot = spot[(spot.t >= c.t_end - 9 * 86400) & (spot.t <= c.t_end)]
    sample = {
        "market_id": int(mid), "question": c.question, "symbol": c.symbol, "strike": float(c.k), "expiry": int(c.t_end),
        "outcome_yes": int(c.y), "fee_rate": None if pd.isna(c.fee_rate) else float(c.fee_rate),
        "spot": {"t0": int(spot.t.iloc[0]), "close": [round(float(x), 2) for x in pd.Series(spot.close.to_numpy(), index=((spot.t - spot.t.iloc[0]) // 60)).reindex(range(int((spot.t.iloc[-1] - spot.t.iloc[0]) // 60) + 1)).ffill()]},
        "fills": [{"t": int(r.t), "p": round(float(r.p), 4), "d": int(r.d), "size": round(float(r.size), 2), "pm": round(float(r.pm), 4)} for r in g.itertuples()],
    }
    Path("results/demo").mkdir(parents=True, exist_ok=True)
    json.dump(sample, open("results/demo/contract.json", "w"))
    print("contract sample:", c.question, len(g), "fills,", len(sample["spot"]["close"]), "spot minutes")
    fig_case_contract()


def fig_case_contract():
    """Annotated still of the walkthrough contract, drawn from the committed sample."""
    from research import walkthrough as w

    c, t0, close, mv = w.load()
    rows = [(w.price(c, t0, close, mv, f["t"]), f) for f in c["fills"]]
    res = [w.verdict(c, f, m) for m, f in rows]
    hours = np.array([-m["tau"] / 3600 for m, _ in rows])
    value = np.array([m["value"] for m, _ in rows])
    p = np.array([f["p"] for _, f in rows])
    e = np.array([r["edge"] > w.THETA for r in res])
    fig, ax = plt.subplots(figsize=(8.2, 3.6))
    ax.plot(hours, value, color=ORANGE, lw=1.8, label="option model value", zorder=3)
    ax.scatter(hours, p, s=7, color=BLUE, alpha=0.35, lw=0, label="fills")
    ax.scatter(hours[e], p[e], s=16, color=INK, lw=0, zorder=4, label="fills the rule would take")
    ax.set_xlabel("hours to expiry"), ax.set_ylabel("price of Yes"), ax.set_ylim(-0.03, 1.03)
    ax.set_title(c["question"])
    ax.legend(fontsize=8, loc="upper left")
    stake = sum(r["stake"] for r, k in zip(res, e) if k)
    pnl = sum(r["pnl"] for r, k in zip(res, e) if k)
    ax.text(0.99, 0.05, f"{int(e.sum())} of {len(rows):,} fills taken, \\${stake:,.0f} staked, {'-' if pnl < 0 else '+'}\\${abs(pnl):,.0f} at settlement (resolved {'Yes' if c['outcome_yes'] else 'No'})",
            transform=ax.transAxes, ha="right", fontsize=8, color=INK2)
    save(fig, "case_contract")


def case_first_touch():
    """One real market where the first print in a band was a spike. Rule: among long-tail Yes/No markets with
    300 to 3,000 fills whose first touch of 0.6-0.9 came after 20 fills and was undone by the next five,
    take the one with the most fills."""
    t = pd.read_parquet("research/data/derived/tape.parquet", columns=["market_id", "t", "p", "y", "size", "yes_no", "category"])
    t = t[t.yes_no & t.category.isin(["politics", "geopolitics", "economy", "finance", "culture", "tech", "mentions", "other"])]
    n = t.groupby("market_id").size()
    t = t[t.market_id.isin(n[(n >= 300) & (n <= 3000)].index)].sort_values(["market_id", "t"]).reset_index(drop=True)
    t["k"] = t.groupby("market_id").cumcount()
    nxt = t[::-1].groupby("market_id").p.transform(lambda s: s.shift(1).rolling(5, min_periods=1).median())[::-1]
    first = t[(t.p > 0.6) & (t.p <= 0.9)].groupby("market_id").head(1)
    first = first[(first.k >= 20) & ((nxt[first.index] - first.p) < -0.15)]
    mid = n.loc[first.market_id].idxmax()
    g = t[t.market_id == mid]
    q = pd.read_parquet("research/data/derived/markets.parquet", columns=["market_id", "question"]).set_index("market_id").question[mid]
    k0 = int(first[first.market_id == mid].k.iloc[0])
    band = g[(g.p > 0.6) & (g.p <= 0.9)]
    fig, ax = plt.subplots(figsize=(8.2, 3.5))
    ax.axhspan(0.6, 0.9, color=LIGHT["grey"], lw=0)
    ax.plot(g.k, g.p, color=BLUE, lw=0.8, alpha=0.6)
    ax.scatter(g.k, g.p, s=5, color=BLUE, lw=0)
    ax.scatter([k0], [g.p.iloc[k0]], s=70, color=ORANGE, zorder=5, lw=0)
    ax.annotate("first touch of the band", xy=(k0, g.p.iloc[k0]), xytext=(k0 + len(g) * 0.06, min(0.98, g.p.iloc[k0] + 0.12)), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    y = int(g.y.iloc[0])
    pooled = float(np.average(y - band.p, weights=band["size"]))
    share = band["size"].sum() / g["size"].sum()
    ax.text(0.99, 0.95, f"Resolved {'Yes' if y else 'No'}. First touch counts this market once, at {g.p.iloc[k0]:.2f}: outcome minus price {y - g.p.iloc[k0]:+.2f}.\n"
            f"Pooling sees {len(band)} of {len(g):,} fills in the band, {100 * share:.2f}% of the shares traded.",
            transform=ax.transAxes, ha="right", va="top", fontsize=8, color=INK2, linespacing=1.4)
    ax.set_xlabel("fill number"), ax.set_ylabel("Yes price"), ax.set_ylim(-0.03, 1.03)
    ax.set_title(q.strip()[:90])
    save(fig, "case_first_touch")
    print("first-touch case:", q)


def main():
    for fn in (fig_pipeline, fig_fill_anatomy, fig_option_geometry, fig_walkforward, fig_case_contract, case_first_touch, case_contract):
        try:
            fn()
        except Exception as e:  # the case studies need the fill tape; schematics do not
            print("skipped", fn.__name__, repr(e)[:160])


if __name__ == "__main__":
    main()
