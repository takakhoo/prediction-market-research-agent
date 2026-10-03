"""Volatility estimators and digital-option probabilities for the price-linked contracts."""
from __future__ import annotations

import numpy as np
from scipy.special import ndtr

YEAR = 365.25 * 86400


class MinuteVol:
    """Trailing realized variance on a 1-minute close grid, queryable at any time without look-ahead."""

    def __init__(self, t0: int, close: np.ndarray):
        self.t0 = t0
        lc = np.log(close)
        r = np.diff(lc, prepend=lc[0])
        r[~np.isfinite(r)] = 0.0
        self.cum = np.cumsum(r * r)
        self.n = len(close)

    def rv(self, t, window_s):
        """Annualized realized vol over the `window_s` seconds ending at the last completed minute before t."""
        i = np.clip(((np.asarray(t, dtype=np.int64) - self.t0) // 60 - 1).astype(int), 0, self.n - 1)
        j = np.clip(i - int(window_s // 60), 0, self.n - 1)
        var_per_min = (self.cum[i] - self.cum[j]) / np.maximum(i - j, 1)
        return np.sqrt(var_per_min * YEAR / 60)


def digital_above(s, k, sigma, tau_s):
    """P(S_T > K) for driftless lognormal S with annualized vol sigma and tau in seconds."""
    tau = np.maximum(np.asarray(tau_s, float), 1.0) / YEAR
    v = np.maximum(sigma, 1e-6) * np.sqrt(tau)
    return ndtr((np.log(np.asarray(s, float) / k) - 0.5 * v * v) / v)


def touch_up(s, k, sigma, tau_s, running_max=None):
    """P(max S >= K before T) by the reflection principle (driftless lognormal, continuous monitoring)."""
    tau = np.maximum(np.asarray(tau_s, float), 1.0) / YEAR
    v = np.maximum(sigma, 1e-6) * np.sqrt(tau)
    b = np.log(k / np.asarray(s, float))
    p = np.where(b <= 0, 1.0, ndtr((-b - 0.5 * v * v) / v) + np.exp(-b) * ndtr((-b + 0.5 * v * v) / v))
    if running_max is not None:
        p = np.where(running_max >= k, 1.0, p)
    return np.clip(p, 0.0, 1.0)


def implied_vol(p, s, k, tau_s, lo=0.01, hi=10.0, iters=60):
    """Vol that makes digital_above equal p. NaN where p is on the wrong side of the no-vol limit."""
    p, s, k = (np.asarray(x, float) for x in (p, s, k))
    lo_a, hi_a = np.full(p.shape, lo), np.full(p.shape, hi)
    otm = s < k  # for OTM digitals, price rises with vol; for ITM it falls
    for _ in range(iters):
        mid = 0.5 * (lo_a + hi_a)
        f = digital_above(s, k, mid, tau_s)
        up = np.where(otm, f < p, f > p)
        lo_a, hi_a = np.where(up, mid, lo_a), np.where(up, hi_a, mid)
    out = 0.5 * (lo_a + hi_a)
    bad = (out < lo * 1.01) | (out > hi * 0.99) | (p <= 0.005) | (p >= 0.995)
    return np.where(bad, np.nan, out)


def contract_prob(o, sigma):
    """Model probability that outcome 0 wins for each row of a contract table, given annualized vol `sigma`."""
    k = np.where(o.kind == "updown", o.s_open, o.k)
    above = digital_above(o.s, k, sigma, o.tau)
    p = np.where(o.kind == "below", 1.0 - above, above)
    p = np.where(o.kind == "between", above - digital_above(o.s, o.k2.fillna(1.0), sigma, o.tau), p)
    p = np.where(o.kind == "reach", touch_up(o.s, o.k, sigma, o.tau, o.run_hi), p)
    p = np.where(o.kind == "dip", touch_up(1.0 / o.s, 1.0 / o.k, sigma, o.tau, 1.0 / o.run_lo), p)
    return np.clip(p, 1e-3, 1 - 1e-3)
