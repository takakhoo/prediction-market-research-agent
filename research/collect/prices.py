"""Download outcome-0 price paths for every market in the universe from the public CLOB API.

Per market, depending on lifetime (start to close):
  <= 36 h : one call at 1-minute fidelity
  <= 6 d  : one call at 10-minute fidelity
  <= 14 d : one call at hourly fidelity
  longer  : full life at 12-hour fidelity, plus the final 14 days hourly
Output: research/data/raw/prices/chunk_XXXX.parquet with (market_id, t, p, fid).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .http import get_json

URL = "https://clob.polymarket.com/prices-history"
H, D = 3600, 86400


def plan(t0: int, t1: int):
    life = t1 - t0
    if life <= 36 * H:
        return [({"startTs": t0 - 600, "endTs": t1 + 600, "fidelity": 1}, 1)]
    if life <= 6 * D:
        return [({"startTs": t0 - H, "endTs": t1 + H, "fidelity": 10}, 10)]
    if life <= 14 * D:
        return [({"startTs": t0 - H, "endTs": t1 + H, "fidelity": 60}, 60)]
    return [
        ({"interval": "max", "fidelity": 720}, 720),
        ({"startTs": t1 - 14 * D, "endTs": t1 + H, "fidelity": 60}, 60),
    ]


def fetch(row):
    mid, token, t0, t1 = row
    out = []
    for params, fid in plan(t0, t1):
        js = get_json(URL, {"market": token, **params})
        hist = js.get("history") if isinstance(js, dict) else None
        if hist is None:
            return mid, None
        out.extend((mid, h["t"], h["p"], fid) for h in hist)
    return mid, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", default="research/data/derived/markets.parquet")
    ap.add_argument("--out", default="research/data/raw/prices")
    ap.add_argument("--chunk", type=int, default=4000)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--min-volume", type=float, default=0)
    ap.add_argument("--ids", default=None, help="optional parquet of market_id to restrict to")
    ap.add_argument("--also-done", default=None, help="another output dir whose fetched ids count as done")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    m = pd.read_parquet(a.markets, columns=["market_id", "token0", "start", "closed_time", "end", "volume", "order_book"])
    m = m[m.token0.notna() & m.order_book & (m.volume >= a.min_volume)].copy()
    if a.ids:
        m = m[m.market_id.isin(pd.read_parquet(a.ids).market_id)].copy()
    t1 = m.closed_time.fillna(m.end)
    m = m[t1.notna() & m.start.notna()]
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    m["t0"] = (m.start - epoch).dt.total_seconds().astype("int64")
    m["t1"] = (t1[m.index] - epoch).dt.total_seconds().astype("int64")
    m = m[m.t1 > m.t0]
    # Fixed shuffle so any prefix of chunks is a random sample of the universe.
    m = m.sample(frac=1.0, random_state=20261002)
    rows = [(int(a), b, int(c), int(d)) for a, b, c, d in zip(m.market_id, m.token0, m.t0, m.t1)]
    print(len(rows), "markets to fetch", flush=True)
    done = set()
    for d in [out] + ([Path(a.also_done)] if a.also_done else []):
        for f in d.glob("ids_*.parquet"):
            done.update(pd.read_parquet(f).market_id.tolist())
    rows = [r for r in rows if r[0] not in done]
    seq = len(list(out.glob("chunk_*.parquet")))
    print(len(done), "already fetched,", len(rows), "to go", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for i in range(0, len(rows), a.chunk):
            batch = rows[i:i + a.chunk]
            recs, ok_ids, failed = [], [], 0
            for mid, got in ex.map(fetch, batch):
                if got is None:
                    failed += 1
                else:
                    ok_ids.append(mid)
                    recs.extend(got)
            df = pd.DataFrame(recs, columns=["market_id", "t", "p", "fid"]).astype(
                {"market_id": np.int32, "t": np.int64, "p": np.float32, "fid": np.int16})
            df.to_parquet(out / f"chunk_{seq:05d}.parquet", index=False)
            pd.DataFrame({"market_id": np.array(ok_ids, np.int32)}).to_parquet(out / f"ids_{seq:05d}.parquet", index=False)
            print(f"chunk_{seq:05d}", len(df), "rows", failed, "failed", flush=True)
            seq += 1


if __name__ == "__main__":
    main()
