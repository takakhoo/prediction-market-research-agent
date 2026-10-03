"""Single-stock and index threshold contracts as digital options on the official close."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

ROOT = Path("research/data/raw/stocks")
SESSION = 6.5 * 3600
OVERNIGHT_SHARE = 0.25  # share of daily return variance that arrives while the market is closed
ALIAS = {"SPX": "GSPC", "WTI": "CL_F", "CL": "CL_F", "NG": "NG_F", "GC": "GC_F", "SI": "SI_F"}
_NUM = r"\$?([\d,]+(?:\.\d+)?)"
_ABOVE = re.compile(rf"\(([A-Z]{{1,5}})\) (?:close[sd]? above|finish week of .+? above) {_NUM}")
_ABOVE2 = re.compile(rf"\(([A-Z]{{1,5}})\) finish week of .+ above {_NUM}")
_BETWEEN = re.compile(rf"\(([A-Z]{{1,5}})\) close at {_NUM}-\$?([\d,]+(?:\.\d+)?)")


def parse(markets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in markets.itertuples():
        q = r.question
        mt = _BETWEEN.search(q)
        if mt:
            rows.append((r.market_id, mt[1], "between", float(mt[2].replace(",", "")), float(mt[3].replace(",", ""))))
            continue
        mt = _ABOVE.search(q) or _ABOVE2.search(q)
        if mt:
            rows.append((r.market_id, mt[1], "above", float(mt[2].replace(",", "")), np.nan))
    out = pd.DataFrame(rows, columns=["market_id", "ticker", "kind", "k", "k2"])
    out["file"] = out.ticker.map(lambda x: ALIAS.get(x, x))
    out = out[out.file.map(lambda f: (ROOT / f"{f}_1d.parquet").exists())]
    return out.merge(markets[["market_id", "t_end", "t0", "t_close", "y", "volume", "fee_rate", "question", "event_id"]], on="market_id")


class Stock:
    def __init__(self, name: str):
        d = pd.read_parquet(ROOT / f"{name}_1d.parquet").sort_values("t")
        h = pd.read_parquet(ROOT / f"{name}_1h.parquet").sort_values("t")
        self.open_t = d.t.to_numpy(dtype=np.int64)          # session open, epoch seconds
        self.day_close = d.close.to_numpy()
        r = np.diff(np.log(self.day_close), prepend=np.nan)
        self.sig_d = pd.Series(r).rolling(20, min_periods=10).std().to_numpy()
        self.h_done = h.t.to_numpy(dtype=np.int64) + 3600   # when each hourly bar is complete
        self.h_close = h.close.to_numpy()

    def spot(self, t):
        i = np.searchsorted(self.h_done, t, side="right") - 1
        return np.where(i >= 0, self.h_close[np.clip(i, 0, None)], np.nan)

    def daily_vol(self, t):
        """20-day close-to-close vol using only sessions that had closed by t."""
        i = np.searchsorted(self.open_t + int(SESSION), t, side="right") - 1
        return np.where(i >= 0, self.sig_d[np.clip(i, 0, None)], np.nan)

    def _clock(self, x):
        n = np.searchsorted(self.open_t, x, side="right")
        last = self.open_t[np.clip(n - 1, 0, None)]
        sess = np.where(n > 0, SESSION * (n - 1) + np.clip(x - last, 0, SESSION), 0.0)
        return n, sess

    def variance_to(self, t, T):
        n0, s0 = self._clock(t)
        n1, s1 = self._clock(T)
        units = OVERNIGHT_SHARE * (n1 - n0) + (1 - OVERNIGHT_SHARE) * (s1 - s0) / SESSION
        return np.maximum(units, 1e-4) * self.daily_vol(t) ** 2

    def settle_close(self, T):
        """Official close of the session containing or ending at T."""
        i = np.searchsorted(self.open_t, T, side="right") - 1
        return np.where(i >= 0, self.day_close[np.clip(i, 0, None)], np.nan)


def model_prob(o: pd.DataFrame, lag: int = 0) -> pd.DataFrame:
    """Add spot `s`, variance to expiry `v`, and the digital-option probability `pm` for each row."""
    parts = []
    for f, g in o.groupby("file"):
        st = Stock(f)
        g = g.copy()
        t = g.t.to_numpy(dtype=np.int64) - lag
        T = g.t_end.to_numpy(dtype=np.int64)
        g["s"] = st.spot(t)
        g["v"] = st.variance_to(g.t.to_numpy(dtype=np.int64), T)
        sd = np.sqrt(np.where(g.v.to_numpy() > 0, g.v.to_numpy(), np.nan))
        above = lambda k: ndtr((np.log(g.s.to_numpy() / k) - 0.5 * sd ** 2) / sd)
        pa = above(g.k.to_numpy())
        g["pm"] = np.where(g.kind == "between", pa - above(g.k2.fillna(1.0).to_numpy()), pa)
        g["tau"] = T - g.t.to_numpy()
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    out = out[np.isfinite(out.pm) & np.isfinite(out.s)]
    out["pm"] = out.pm.clip(1e-3, 1 - 1e-3)
    return out
