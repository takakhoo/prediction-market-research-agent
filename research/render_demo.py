"""Animate one real contract: Polymarket fills against the option model's value, with spot and strike.

The contract is chosen by a fixed rule, not by hand: among crypto threshold contracts with at least
300 fills in their final 36 hours and a spot path that crossed the strike in that window, take the
one where the option-model rule staked the most.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter

from research.experiments import e4_crypto_options as e4
from research.figures import BASE, BLUE, GRID, INK2, MUTED, ORANGE, SURFACE


def pick(o: pd.DataFrame) -> int:
    o = o[o.kind == "above"]
    edge = o.d * (o.pm - o.p) - o.fee
    stake = (o["size"] * o.cost).where(edge > 0.10, 0.0)
    w = o[o.tau < 36 * 3600].groupby("market_id").agg(n=("p", "size"), lo=("s", "min"), hi=("s", "max"), k=("k", "first"))
    w = w[(w.n >= 300) & (w.lo < w.k) & (w.hi > w.k)]
    cand = stake.groupby(o.market_id).sum().loc[w.index]
    return int(cand.idxmax())


def main():
    o = e4.load()
    mid = pick(o)
    g = o[(o.market_id == mid) & (o.tau < 36 * 3600)].sort_values("t")
    c = pd.read_parquet("research/data/derived/crypto_contracts.parquet").set_index("market_id").loc[mid]
    hours = -(g.tau.to_numpy()) / 3600
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 5.0), sharex=True, gridspec_kw={"height_ratios": [1, 1.6]})
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle(c.question, x=0.02, ha="left", fontsize=11, fontweight="bold")
    ax1.axhline(c.k, color=MUTED, lw=1, ls=(0, (4, 3)))
    ax1.text(hours.min(), c.k, " strike", va="bottom", fontsize=8, color=MUTED)
    (spot_line,) = ax1.plot([], [], color=INK2, lw=1.5)
    ax1.set_ylabel("spot")
    ax1.set_ylim(min(g.s.min(), c.k) * 0.997, max(g.s.max(), c.k) * 1.003)
    (model_line,) = ax2.plot([], [], color=ORANGE, lw=2, label="option model value")
    fills = ax2.scatter([], [], s=9, color=BLUE, alpha=0.55, label="Polymarket fills", linewidths=0)
    ax2.set_ylim(-0.03, 1.03), ax2.set_xlim(hours.min(), 0.3)
    ax2.set_ylabel("price of Yes"), ax2.set_xlabel("hours to expiry")
    ax2.legend(loc="upper left", fontsize=8, frameon=False)
    verdict = ax2.text(0.99, 0.06, "", transform=ax2.transAxes, ha="right", fontsize=9, color=INK2)
    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE), ax.grid(color=GRID, lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(BASE)
    n_frames = 70

    def draw(i):
        k = max(2, int(len(g) * min(1.0, (i + 1) / (n_frames - 10))))
        spot_line.set_data(hours[:k], g.s.to_numpy()[:k])
        model_line.set_data(hours[:k], g.pm.to_numpy()[:k])
        fills.set_offsets(np.column_stack([hours[:k], g.p.to_numpy()[:k]]))
        verdict.set_text(f"resolved {'Yes' if c.y == 1 else 'No'}" if k >= len(g) else "")
        return spot_line, model_line, fills, verdict

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    FuncAnimation(fig, draw, frames=n_frames, blit=False).save("results/figures/demo.gif", writer=PillowWriter(fps=12), dpi=110)
    print("wrote demo.gif for market", mid, c.question)


if __name__ == "__main__":
    main()
