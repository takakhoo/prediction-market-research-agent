"""Price one real contract by hand, fill by fill. Needs no data beyond results/demo/contract.json.

    python -m research.walkthrough            # the story of one contract
    python -m research.walkthrough --fill 0   # every number behind one fill
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np

from research.lib.vol import YEAR, MinuteVol, digital_above

WINDOWS = np.array([900, 3600, 6 * 3600, 86400, 7 * 86400])
THETA = 0.10


def load(path="results/demo/contract.json"):
    c = json.load(open(path))
    close = np.array(c["spot"]["close"], dtype=float)
    return c, c["spot"]["t0"], close, MinuteVol(c["spot"]["t0"], close)


def price(c, t0, close, mv, t):
    """Everything the model knew at time t: the last closed minute, time left, and trailing volatility."""
    i = int((t - t0) // 60) - 1                      # last candle that had closed before the fill
    s = close[i]
    tau = c["expiry"] - t
    window = WINDOWS[np.abs(np.log(np.clip(4 * tau, 3600, 30 * 86400) / WINDOWS)).argmin()]
    sigma = float(mv.rv(np.array([t]), window)[0])
    v = sigma * np.sqrt(tau / YEAR)
    d2 = (np.log(s / c["strike"]) - 0.5 * v * v) / v
    return {"s": s, "tau": tau, "window": int(window), "sigma": sigma, "d2": d2,
            "value": float(np.clip(digital_above(s, c["strike"], sigma, tau), 1e-3, 1 - 1e-3))}


def verdict(c, f, m):
    cost = f["p"] if f["d"] == 1 else 1 - f["p"]
    fee = (c["fee_rate"] or 0.0) * cost * (1 - cost)
    worth = m["value"] if f["d"] == 1 else 1 - m["value"]
    won = c["outcome_yes"] if f["d"] == 1 else 1 - c["outcome_yes"]
    return {"cost": cost, "fee": fee, "edge": worth - cost - fee, "pnl": f["size"] * (won - cost - fee), "stake": f["size"] * cost}


def one_fill(c, t0, close, mv, k):
    f = c["fills"][k]
    m = price(c, t0, close, mv, f["t"])
    r = verdict(c, f, m)
    side = "Yes" if f["d"] == 1 else "No"
    print(f"Fill {k} at {datetime.fromtimestamp(f['t'], timezone.utc):%Y-%m-%d %H:%M:%S} UTC")
    print(f"  the taker bought {f['size']:,.0f} shares of {side} and paid {r['cost']:.3f} each (Yes price {f['p']:.3f})")
    print(f"  spot, last closed minute        S = {m['s']:,.2f}")
    print(f"  strike                          K = {c['strike']:,.0f}")
    print(f"  time left                     tau = {m['tau'] / 3600:.2f} hours")
    print(f"  trailing vol ({m['window'] / 3600:g}h window)  sigma = {100 * m['sigma']:.1f}% a year")
    print(f"  d2 = (ln(S/K) - sigma^2 tau / 2) / (sigma sqrt(tau)) = {m['d2']:+.3f}")
    print(f"  model value of Yes        N(d2) = {m['value']:.3f}")
    print(f"  model value of what was bought  = {m['value'] if f['d'] == 1 else 1 - m['value']:.3f}")
    print(f"  fee                             = {r['fee']:.4f}")
    print(f"  edge = value - cost - fee       = {r['edge']:+.3f}   ({'take it' if r['edge'] > THETA else 'pass'}, bar is {THETA:+.2f})")
    print(f"  at settlement this fill made    = {'-' if r['pnl'] < 0 else '+'}${abs(r['pnl']):,.2f} on ${r['stake']:,.2f}")


def story(c, t0, close, mv):
    print(f"=== {c['question']} ===")
    print(f"strike {c['strike']:,.0f}, settles {datetime.fromtimestamp(c['expiry'], timezone.utc):%Y-%m-%d %H:%M} UTC on the Binance 1-minute close\n")
    print("  hours left      spot   sigma   model   fill   side   edge   rule")
    taken_stake = taken_pnl = 0.0
    worst, lines, taken = 0.0, {}, []
    for k, f in enumerate(c["fills"]):
        m = price(c, t0, close, mv, f["t"])
        r = verdict(c, f, m)
        worst = max(worst, abs(m["value"] - f["pm"]))
        if r["edge"] > THETA:
            taken.append(k)
            taken_stake, taken_pnl = taken_stake + r["stake"], taken_pnl + r["pnl"]
        lines[k] = f"  {m['tau'] / 3600:10.2f} {m['s']:9,.0f}  {100 * m['sigma']:5.1f}%  {m['value']:6.3f} {f['p']:6.3f}   {'Yes' if f['d'] == 1 else 'No ':3s} {r['edge']:+6.3f}   {'take' if r['edge'] > THETA else '.'}"
    n_taken = len(taken)
    # print an even sample of all fills plus an even sample of the ones the rule takes
    show = set(range(0, len(c["fills"]), max(1, len(c["fills"]) // 12)))
    show.update(taken[:: max(1, len(taken) // 6)])
    rows = [lines[k] for k in sorted(show)]
    print("\n".join(rows))
    print(f"\nResolved {'Yes' if c['outcome_yes'] else 'No'}.")
    print(f"  {len(c['fills']):,} fills in the last 36 hours; the rule would have taken {n_taken:,} of them")
    if n_taken:
        print(f"  ${taken_stake:,.0f} staked, {'-' if taken_pnl < 0 else '+'}${abs(taken_pnl):,.0f} at settlement ({100 * taken_pnl / taken_stake:+.1f}%)")
    print(f"  largest gap between this recomputation and the pipeline's stored value: {worst:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", type=int, default=None, help="explain one fill in full")
    ap.add_argument("--sample", default="results/demo/contract.json")
    a = ap.parse_args()
    c, t0, close, mv = load(a.sample)
    if a.fill is None:
        story(c, t0, close, mv)
    else:
        one_fill(c, t0, close, mv, a.fill)


if __name__ == "__main__":
    main()
