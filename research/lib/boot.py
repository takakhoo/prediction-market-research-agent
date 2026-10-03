"""Fast cluster bootstrap for ratio statistics: aggregate per cluster once, then reweight clusters."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ratio_ci(num: np.ndarray, den: np.ndarray, cluster: np.ndarray, n_boot: int = 1000, seed: int = 0):
    """Point estimate and 95% CI of sum(num)/sum(den), resampling clusters with replacement."""
    codes, _ = pd.factorize(cluster)
    k = codes.max() + 1
    a = np.bincount(codes, weights=num, minlength=k)
    b = np.bincount(codes, weights=den, minlength=k)
    rng = np.random.default_rng(seed)
    w = rng.poisson(1.0, size=(n_boot, k)).astype(np.float64)
    draws = (w @ a) / np.maximum(w @ b, 1e-12)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(a.sum() / b.sum()), float(lo), float(hi)


def diff_ci(x: np.ndarray, w: np.ndarray, cluster: np.ndarray, n_boot: int = 1000, seed: int = 0):
    """Weighted mean of x with a cluster-bootstrap CI and the share of draws above zero."""
    codes, _ = pd.factorize(cluster)
    k = codes.max() + 1
    a = np.bincount(codes, weights=x * w, minlength=k)
    b = np.bincount(codes, weights=w, minlength=k)
    rng = np.random.default_rng(seed)
    wt = rng.poisson(1.0, size=(n_boot, k)).astype(np.float64)
    draws = (wt @ a) / np.maximum(wt @ b, 1e-12)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(a.sum() / b.sum()), float(lo), float(hi), float((draws > 0).mean())
