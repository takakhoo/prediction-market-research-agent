"""Download taker trades for a list of markets from the public data API.

The endpoint serves the most recent 11,000 trades per market (offset cap 10,000),
so a market is complete only when it has fewer trades than that. Completeness is recorded.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .http import get_json

URL = "https://data-api.polymarket.com/trades"
CAP = 11_000


def fetch(row):
    mid, cond = row
    out, off = [], 0
    while off <= 10_000:
        page = get_json(URL, {"market": cond, "limit": 1000, "offset": off, "takerOnly": "true"})
        if not isinstance(page, list):
            return mid, None
        out.extend((mid, t["timestamp"], t["price"], t["size"], t["side"] == "BUY", t["outcomeIndex"], t["proxyWallet"]) for t in page)
        if len(page) < 1000:
            break
        off += 1000
    return mid, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="parquet with market_id, condition_id")
    ap.add_argument("--out", default="research/data/raw/trades")
    ap.add_argument("--chunk", type=int, default=500)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    m = pd.read_parquet(a.ids)
    rows = list(zip(m.market_id, m.condition_id))
    with ThreadPoolExecutor(a.workers) as ex:
        for i in range(0, len(rows), a.chunk):
            target = out / f"chunk_{i // a.chunk:04d}.parquet"
            if target.exists():
                continue
            recs, failed = [], 0
            for mid, got in ex.map(fetch, rows[i:i + a.chunk]):
                if got is None:
                    failed += 1
                else:
                    recs.extend(got)
            df = pd.DataFrame(recs, columns=["market_id", "t", "price", "size", "is_buy", "outcome_index", "wallet"]).astype(
                {"market_id": np.int32, "t": np.int64, "price": np.float32, "size": np.float32, "outcome_index": np.int8})
            df["wallet"] = df.wallet.astype("category")
            df.to_parquet(target, index=False)
            print(target.name, len(df), "trades", failed, "failed", flush=True)


if __name__ == "__main__":
    main()
