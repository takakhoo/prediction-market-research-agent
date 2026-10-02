"""Expanding-window walk-forward evaluation with label purging.

For a test block starting at time B, the training set holds only snapshots from markets that had
already resolved before B, so every training label was public when the test forecasts are made.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from .stats import fit_logistic, logit
from scipy.special import expit


def blocks(panel: pd.DataFrame, start: str, freq: str = "2MS"):
    edges = pd.date_range(start, pd.Timestamp(panel.t_snap.max(), unit="s") + pd.offsets.MonthBegin(2), freq=freq)
    for a, b in zip(edges[:-1], edges[1:]):
        yield a, a.timestamp(), b.timestamp()


def market_weights(df: pd.DataFrame) -> np.ndarray:
    return (1.0 / df.groupby("market_id").p.transform("size")).to_numpy()


class Platt:
    name = "platt"

    def fit(self, tr):
        self.a, self.b = fit_logistic(logit(tr.p), tr.y, market_weights(tr))
        return self

    def predict(self, te):
        return expit(self.a + self.b * logit(te.p))


class PlattByCategory:
    name = "platt_by_category"

    def fit(self, tr):
        self.glob = fit_logistic(logit(tr.p), tr.y, market_weights(tr))
        self.by = {c: fit_logistic(logit(g.p), g.y, market_weights(g)) for c, g in tr.groupby("category") if g.market_id.nunique() >= 300}
        return self

    def predict(self, te):
        out = np.empty(len(te))
        lp = logit(te.p)
        for c in te.category.unique():
            a, b = self.by.get(c, self.glob)
            s = (te.category == c).to_numpy()
            out[s] = expit(a + b * lp[s])
        return out


class Isotonic:
    name = "isotonic"

    def fit(self, tr):
        self.m = IsotonicRegression(y_min=0.001, y_max=0.999, out_of_bounds="clip").fit(tr.p, tr.y, sample_weight=market_weights(tr))
        return self

    def predict(self, te):
        return self.m.predict(te.p)


class GBM:
    def __init__(self, feats, name="gbm", **kw):
        self.feats, self.name = feats, name
        self.kw = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200, l2_regularization=1.0,
                       early_stopping=False, random_state=0)
        self.kw.update(kw)

    def fit(self, tr):
        cat_idx = [i for i, f in enumerate(self.feats) if f == "cat_code"]
        self.m = HistGradientBoostingClassifier(categorical_features=cat_idx or None, **self.kw)
        self.m.fit(tr[self.feats].to_numpy(), tr.y.to_numpy(), sample_weight=market_weights(tr))
        return self

    def predict(self, te):
        return np.clip(self.m.predict_proba(te[self.feats].to_numpy())[:, 1], 0.001, 0.999)


class ResidualGBM:
    """Boosted trees on the residual y - p. The forecast is the market price plus a learned correction,
    so with no signal the model returns the price itself."""

    def __init__(self, feats, name="residual_gbm", shrink=1.0, **kw):
        from sklearn.ensemble import HistGradientBoostingRegressor
        self.feats, self.name, self.shrink = feats, name, shrink
        self.kw = dict(max_iter=100, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=400, l2_regularization=5.0,
                       early_stopping=False, random_state=0)
        self.kw.update(kw)
        self.cls = HistGradientBoostingRegressor

    def fit(self, tr):
        cat_idx = [i for i, f in enumerate(self.feats) if f == "cat_code"]
        self.m = self.cls(categorical_features=cat_idx or None, **self.kw)
        self.m.fit(tr[self.feats].to_numpy(), (tr.y - tr.p).to_numpy(), sample_weight=market_weights(tr))
        return self

    def predict(self, te):
        return np.clip(te.p.to_numpy() + self.shrink * self.m.predict(te[self.feats].to_numpy()), 0.001, 0.999)


class FairBlend:
    """Two-parameter blend of the traded price and the option-model value, in log-odds:
    logit(p_hat) = a + b logit(price) + c logit(fair). Contracts without a fair value keep the price."""

    name = "fair_blend"

    def fit(self, tr):
        from scipy import optimize
        g = tr[tr.fair.notna()]
        self.theta = None
        if g.market_id.nunique() < 300:
            return self
        X = np.column_stack([np.ones(len(g)), logit(g.p), g.fair_lp])
        y, w = g.y.to_numpy(float), market_weights(g)
        nll = lambda th: np.sum(w * (np.logaddexp(0, X @ th) - y * (X @ th)))
        jac = lambda th: X.T @ (w * (expit(X @ th) - y))
        self.theta = optimize.minimize(nll, np.array([0.0, 0.5, 0.5]), jac=jac, method="BFGS").x
        return self

    def predict(self, te):
        out = te.p.to_numpy(float).copy()
        s = te.fair.notna().to_numpy()
        if self.theta is not None and s.any():
            X = np.column_stack([np.ones(s.sum()), logit(te.p[s]), te.fair_lp[s]])
            out[s] = expit(X @ self.theta)
        return np.clip(out, 0.001, 0.999)


class Column:
    """Use an existing column as the forecast (for example a smoothed price or an option-model value)."""

    def __init__(self, col, name=None):
        self.col, self.name = col, name or col

    def fit(self, tr):
        return self

    def predict(self, te):
        return np.clip(te[self.col].to_numpy(), 0.001, 0.999)


def run(panel: pd.DataFrame, models, start="2025-07-01", min_train_markets=2000, verbose=True) -> pd.DataFrame:
    """Returns the test rows with one prediction column per model."""
    out = []
    for label, a, b in blocks(panel, start):
        tr = panel[panel.t_close < a]
        te = panel[(panel.t_snap >= a) & (panel.t_snap < b)]
        if tr.market_id.nunique() < min_train_markets or te.empty:
            continue
        te = te.copy()
        for mdl in models:
            te[mdl.name] = mdl.fit(tr).predict(te)
        te["block"] = label.strftime("%Y-%m")
        out.append(te)
        if verbose:
            print(label.strftime("%Y-%m"), "train mkts", tr.market_id.nunique(), "test mkts", te.market_id.nunique(), flush=True)
    return pd.concat(out, ignore_index=True)
