"""Flatten the raw Gamma pulls into one typed market table."""
from __future__ import annotations

import glob
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("research/data/raw/markets")
OUT = Path("research/data/derived/markets.parquet")


def _ts(s):
    return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")


def load() -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(str(RAW / "markets_*.jsonl.gz"))):
        if not Path(f.replace(".jsonl.gz", ".done")).exists():
            continue
        with gzip.open(f, "rt") as fh:
            for line in fh:
                m = json.loads(line)
                try:
                    outcomes = json.loads(m.get("outcomes") or "[]")
                    prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                    tokens = json.loads(m.get("clobTokenIds") or "[]")
                except (ValueError, TypeError):
                    continue
                ev = (m.get("events") or [{}])[0]
                rows.append({
                    "market_id": int(m["id"]),
                    "condition_id": m.get("conditionId"),
                    "question": (m.get("question") or "").strip(),
                    "slug": m.get("slug"),
                    "description": (m.get("description") or "")[:3000],
                    "resolution_source": m.get("resolutionSource"),
                    "outcome0": outcomes[0] if len(outcomes) == 2 else None,
                    "outcome1": outcomes[1] if len(outcomes) == 2 else None,
                    "n_outcomes": len(outcomes),
                    "final0": prices[0] if len(prices) == 2 else np.nan,
                    "final1": prices[1] if len(prices) == 2 else np.nan,
                    "token0": tokens[0] if len(tokens) == 2 else None,
                    "token1": tokens[1] if len(tokens) == 2 else None,
                    "volume": float(m.get("volumeNum") or 0),
                    "start": m.get("startDate") or m.get("createdAt"),
                    "created": m.get("createdAt"),
                    "end": m.get("endDate"),
                    "closed_time": m.get("closedTime"),
                    "uma_status": m.get("umaResolutionStatus"),
                    "neg_risk": bool(m.get("negRisk")),
                    "neg_risk_id": m.get("negRiskMarketID"),
                    "order_book": bool(m.get("enableOrderBook")),
                    "fees_enabled": bool(m.get("feesEnabled")),
                    "fee_type": m.get("feeType"),
                    "fee_rate": (m.get("feeSchedule") or {}).get("rate"),
                    "fee_exponent": (m.get("feeSchedule") or {}).get("exponent"),
                    "taker_fee_bps": m.get("takerBaseFee"),
                    "maker_fee_bps": m.get("makerBaseFee"),
                    "tick": m.get("orderPriceMinTickSize"),
                    "sports_type": m.get("sportsMarketType"),
                    "game_start": m.get("gameStartTime"),
                    "group_item": m.get("groupItemTitle"),
                    "event_id": ev.get("id"),
                    "event_slug": ev.get("slug"),
                    "event_title": ev.get("title"),
                    "event_volume": ev.get("volume"),
                    "tags": "|".join(m.get("tags") or []),
                })
    df = pd.DataFrame(rows).drop_duplicates("market_id")
    for c in ("start", "created", "end", "closed_time", "game_start"):
        df[c] = _ts(df[c])
    return df.sort_values("market_id").reset_index(drop=True)


if __name__ == "__main__":
    df = load()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(len(df), "markets ->", OUT)
