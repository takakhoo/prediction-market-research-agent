"""Scoring, calibration, and cluster-robust inference helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize, special

EPS = 1e-3


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def brier(p, y, w=None):
    return float(np.average((np.asarray(p) - np.asarray(y)) ** 2, weights=w))


def logloss(p, y, w=None):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y)
    return float(np.average(-(y * np.log(p) + (1 - y) * np.log(1 - p)), weights=w))


def murphy(p, y, bins=20):
    """Murphy (1973) decomposition: Brier = reliability - resolution + uncertainty (binned)."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    b = np.minimum((p * bins).astype(int), bins - 1)
    base = y.mean()
    rel = res = 0.0
    for k in np.unique(b):
        s = b == k
        rel += s.sum() * (p[s].mean() - y[s].mean()) ** 2
        res += s.sum() * (y[s].mean() - base) ** 2
    n = len(p)
    return {"reliability": rel / n, "resolution": res / n, "uncertainty": base * (1 - base), "brier": brier(p, y)}


def fit_logistic(x, y, w=None):
    """y ~ sigmoid(a + b x). Returns (a, b). b > 1 means prices are not extreme enough."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    w = np.ones_like(x) if w is None else np.asarray(w, float)

    def nll(theta):
        z = theta[0] + theta[1] * x
        return np.sum(w * (np.logaddexp(0, z) - y * z))

    def grad(theta):
        r = w * (special.expit(theta[0] + theta[1] * x) - y)
        return np.array([r.sum(), (r * x).sum()])

    return optimize.minimize(nll, np.array([0.0, 1.0]), jac=grad, method="BFGS").x


def cluster_boot(df: pd.DataFrame, stat, cluster="event_id", n=400, seed=0):
    """Percentile bootstrap that resamples whole clusters. `stat` maps a frame and a per-row weight to a scalar or array."""
    codes, _ = pd.factorize(df[cluster].to_numpy())
    k = codes.max() + 1
    rng = np.random.default_rng(seed)
    point = np.asarray(stat(df, np.ones(len(df))), float)
    draws = np.empty((n,) + point.shape)
    for i in range(n):
        draws[i] = stat(df, rng.poisson(1.0, k)[codes].astype(float))
    lo, hi = np.nanpercentile(draws, [2.5, 97.5], axis=0)
    return point, lo, hi, draws


def calibration_table(df: pd.DataFrame, edges, p="p", y="y", w=None):
    b = np.clip(np.digitize(df[p].to_numpy(), edges) - 1, 0, len(edges) - 2)
    w = np.ones(len(df)) if w is None else w
    g = pd.DataFrame({"b": b, "p": df[p].to_numpy(), "y": df[y].to_numpy(), "w": w})
    g["wp"], g["wy"] = g.p * g.w, g.y * g.w
    s = g.groupby("b")[["w", "wp", "wy"]].sum().reindex(range(len(edges) - 1))
    return pd.DataFrame({"lo": edges[:-1], "hi": edges[1:], "n": s.w.to_numpy(),
                         "mean_p": (s.wp / s.w).to_numpy(), "mean_y": (s.wy / s.w).to_numpy()})
