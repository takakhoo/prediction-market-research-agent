"""Load taker trades and express each one as a position in outcome 0 ("YES").

Each row of the public trade feed is one taker fill. A buy of outcome 1 at q is the same
economic position as a sale of outcome 0 at 1 - q, so every trade becomes:
  p    : outcome-0 price paid or received
  d    : +1 if the taker ends up long outcome 0, -1 if long outcome 1
  cost : what the taker paid per share for the side they bought (p if d=+1 else 1-p)
The maker holds the opposite position at the same price.
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

CAP = 11_000


def load_trades(pattern="research/data/raw/trades*/chunk_*.parquet") -> pd.DataFrame:
    parts = []
    for f in sorted(glob.glob(pattern)):
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        df["wallet"] = df.wallet.astype(str)
        parts.append(df)
    t = pd.concat(parts, ignore_index=True)
    t = t.drop_duplicates(["market_id", "t", "price", "size", "is_buy", "outcome_index", "wallet"])
    first = t.outcome_index == 0
    t["p"] = np.where(first, t.price, 1.0 - t.price).astype(np.float32)
    t["d"] = np.where(first == t.is_buy, 1, -1).astype(np.int8)
    t["cost"] = np.where(t.d == 1, t.p, 1.0 - t.p).astype(np.float32)
    t["usd"] = (t["size"] * t.price).astype(np.float32)
    n = t.groupby("market_id").t.transform("size")
    t["complete"] = n < CAP
    return t.sort_values(["market_id", "t"]).reset_index(drop=True)


def taker_fee(cost, fee_rate):
    """Polymarket taker fee per share: rate * p * (1 - p). Zero where the market has no fee schedule."""
    return np.nan_to_num(fee_rate, nan=0.0) * cost * (1.0 - cost)
