"""Build the snapshot panel: one row per (market, ex-ante snapshot time).

Every column is computable from information available at the snapshot time, except the
label `y` (did outcome 0 win) and columns prefixed `post_`, which exist for evaluation only.

Snapshot times are fixed by the market's scheduled life (start to scheduled end), which is
published when the market opens:
  - fractions of scheduled life: 5%, 10%, 20%, ..., 90%, 95%
  - fixed times before the scheduled end: 1h, 6h, 1d, 3d, 7d, 30d
A snapshot exists only if the market was still open and had already printed a price.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

from .categories import add_category

FRACS = np.array([0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95])
HORIZONS = np.array([3600, 6 * 3600, 86400, 3 * 86400, 7 * 86400, 30 * 86400])
LAGS = {"lag_1h": 3600, "lag_6h": 6 * 3600, "lag_1d": 86400, "lag_3d": 3 * 86400, "lag_7d": 7 * 86400}
EPS = 1e-3


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def load_prices(pattern="research/data/raw/prices*/chunk_*.parquet") -> pd.DataFrame:
    # A chunk is complete only once its ids_ sidecar exists.
    files = [f for f in sorted(glob.glob(pattern)) if Path(f.replace("chunk_", "ids_")).exists()]
    px = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    px = px.sort_values(["market_id", "t", "fid"]).drop_duplicates(["market_id", "t"], keep="first")
    return px


def _at(t, p, when):
    """Last price at or before each `when`; NaN when none exists. Returns (price, age_seconds)."""
    idx = np.searchsorted(t, when, side="right") - 1
    ok = idx >= 0
    price = np.where(ok, p[np.clip(idx, 0, None)], np.nan)
    age = np.where(ok, when - t[np.clip(idx, 0, None)], np.nan)
    return price, age


def build(markets: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    m = markets.set_index("market_id")
    out = []
    grouped = px.groupby("market_id", sort=False)
    for mid, g in grouped:
        if mid not in m.index:
            continue
        r = m.loc[mid]
        t = g.t.to_numpy()
        p = g.p.to_numpy(dtype=np.float64)
        t0, t_end, t_close = r.t0, r.t_end, r.t_close
        if not np.isfinite(t_end) or t_end <= t0 or len(t) < 2:
            continue
        life = t_end - t0
        snaps = np.concatenate([t0 + FRACS * life, t_end - HORIZONS[HORIZONS < life]])
        kind = np.concatenate([np.zeros(len(FRACS), np.int8), np.ones(int((HORIZONS < life).sum()), np.int8)])
        keep = (snaps < t_close - 60) & (snaps >= t[0])
        snaps, kind = snaps[keep], kind[keep]
        if not len(snaps):
            continue
        price, age = _at(t, p, snaps)
        idx = np.searchsorted(t, snaps, side="right")
        lp = logit(p)
        d = np.diff(lp)
        dt = np.maximum(np.diff(t), 1)
        # running stats of the path up to each snapshot
        cum_abs = np.concatenate([[0.0], np.cumsum(np.abs(d))])
        cum_sq = np.concatenate([[0.0], np.cumsum(d * d)])
        run_max = np.maximum.accumulate(p)
        run_min = np.minimum.accumulate(p)
        k = np.clip(idx - 1, 0, len(t) - 1)
        elapsed = np.maximum(snaps - t[0], 1)
        row = {
            "market_id": np.full(len(snaps), mid, np.int32),
            "t_snap": snaps.astype(np.int64),
            "kind": kind,
            "p": price,
            "age": age,
            "frac_life": (snaps - t0) / life,
            "tte": t_end - snaps,
            "life": np.full(len(snaps), life),
            "n_obs": idx,
            "path_abs": cum_abs[k],
            "path_rv": np.sqrt(cum_sq[k] / elapsed * 86400),
            "run_max": run_max[k],
            "run_min": run_min[k],
            "p_first": np.full(len(snaps), p[0]),
            "post_ttc": t_close - snaps,
        }
        for name, lag in LAGS.items():
            row[name], _ = _at(t, p, snaps - lag)
        if "usd" in g.columns:
            cum_usd = np.cumsum(g.usd.to_numpy(dtype=np.float64))
            cum_signed = np.cumsum((g.usd * g.d).to_numpy(dtype=np.float64))
            row["cum_usd"] = cum_usd[k]
            row["cum_flow"] = cum_signed[k]
            j = np.clip(np.searchsorted(t, snaps - 3600, side="right") - 1, 0, len(t) - 1)
            row["usd_1h"] = cum_usd[k] - cum_usd[j]
            row["flow_1h"] = cum_signed[k] - cum_signed[j]
            # size-weighted mean price of the last ten fills: a less noisy consensus than the last print
            sz = g["size"].to_numpy(dtype=np.float64) if "size" in g.columns else np.ones(len(t))
            c_sp, c_s = np.cumsum(sz * p), np.cumsum(sz)
            k10 = np.clip(k - 10, -1, None)
            num = c_sp[k] - np.where(k10 >= 0, c_sp[np.clip(k10, 0, None)], 0.0)
            den = c_s[k] - np.where(k10 >= 0, c_s[np.clip(k10, 0, None)], 0.0)
            row["vwap10"] = num / np.maximum(den, 1e-12)
        for col in g.columns:
            if col.startswith("c_"):
                row[col] = np.cumsum(g[col].to_numpy(dtype=np.float64))[k]
        out.append(pd.DataFrame(row))
    panel = pd.concat(out, ignore_index=True)
    panel = panel.drop_duplicates(["market_id", "t_snap"])
    cols = ["y", "category", "neg_risk", "event_id", "volume", "yes_no", "fees_enabled", "n_siblings", "t_close", "t0"]
    return panel.join(m[cols], on="market_id")


def prepare_markets(markets: pd.DataFrame) -> pd.DataFrame:
    m = add_category(markets)
    resolved = ((m.final0 == 1) & (m.final1 == 0)) | ((m.final0 == 0) & (m.final1 == 1))
    m = m[resolved & m.token0.notna()].copy()
    m["y"] = (m.final0 == 1).astype(np.int8)
    m["yes_no"] = (m.outcome0 == "Yes") & (m.outcome1 == "No")
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    sec = lambda s: (s - epoch).dt.total_seconds()
    m["t0"] = sec(m.start)
    m["t_close"] = sec(m.closed_time.fillna(m.end))
    m["t_end"] = sec(m.end)
    m = m[m.t0.notna() & m.t_close.notna()].copy()
    m["event_id"] = m.event_id.fillna("m" + m.market_id.astype(str))
    m["n_siblings"] = m.groupby("event_id").market_id.transform("size")
    return m


if __name__ == "__main__":
    markets = prepare_markets(pd.read_parquet("research/data/derived/markets.parquet"))
    px = load_prices()
    panel = build(markets, px)
    Path("research/data/derived").mkdir(parents=True, exist_ok=True)
    panel.to_parquet("research/data/derived/panel.parquet", index=False)
    print(len(panel), "snapshots from", panel.market_id.nunique(), "markets")
