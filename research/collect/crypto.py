"""Spot 1-minute candles (Binance public data API) and Deribit DVOL hourly index."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .http import get_json

OUT = Path("research/data/raw/crypto")
KLINES = "https://data-api.binance.vision/api/v3/klines"
DVOL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"


def month_starts(start: str, end: str):
    return list(pd.date_range(start, end, freq="MS", tz="UTC"))


def pull_month(args):
    symbol, month = args
    target = OUT / f"{symbol}_{month:%Y-%m}.parquet"
    if target.exists():
        return target.name, -1
    lo = int(month.timestamp() * 1000)
    hi = int((month + pd.offsets.MonthBegin(1)).timestamp() * 1000)
    rows, cur = [], lo
    while cur < hi:
        page = get_json(KLINES, {"symbol": symbol, "interval": "1m", "startTime": cur, "endTime": hi - 1, "limit": 1000})
        if not isinstance(page, list) or not page:
            break
        rows.extend((r[0] // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in page)
        cur = page[-1][0] + 60_000
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume"])
    df = df.astype({"t": np.int64, "open": np.float64, "high": np.float64, "low": np.float64, "close": np.float64, "volume": np.float32})
    complete = month + pd.offsets.MonthBegin(1) <= pd.Timestamp.now(tz="UTC")
    if complete or len(df):
        df.to_parquet(target if complete else OUT / f"{symbol}_{month:%Y-%m}.partial.parquet", index=False)
    return target.name, len(df)


def pull_dvol(currency: str, start: str):
    rows, end = [], int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    lo = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    while end > lo:
        js = get_json(DVOL, {"currency": currency, "start_timestamp": lo, "end_timestamp": end, "resolution": 3600})
        res = js.get("result", {})
        data = res.get("data") or []
        if not data:
            break
        rows.extend(data)
        cont = res.get("continuation")
        if not cont:
            break
        end = cont
    df = pd.DataFrame(rows, columns=["t_ms", "open", "high", "low", "close"]).drop_duplicates("t_ms").sort_values("t_ms")
    df["t"] = df.t_ms // 1000
    df[["t", "open", "high", "low", "close"]].to_parquet(OUT / f"dvol_{currency}.parquet", index=False)
    return len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-10-01")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for cur in ("BTC", "ETH"):
        print("dvol", cur, pull_dvol(cur, "2023-06-01"), flush=True)
    jobs = [(s, m) for s in a.symbols.split(",") for m in month_starts(a.start, a.end)]
    with ThreadPoolExecutor(4) as ex:
        for name, n in ex.map(pull_month, jobs):
            print(name, "cached" if n < 0 else n, flush=True)


if __name__ == "__main__":
    main()
