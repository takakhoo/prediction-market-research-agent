"""Parse price-linked markets into option-like terms and replay their settlement from spot data.

kind:
  above / below : digital on the settlement print at expiry
  between       : range digital [k, k2)
  updown        : digital struck at the window-open price (>= open resolves Up)
  reach / dip   : one-touch on the high / low over the window
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ASSETS = {"bitcoin": "BTCUSDT", "btc": "BTCUSDT", "ethereum": "ETHUSDT", "eth": "ETHUSDT",
          "solana": "SOLUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT"}
_NUM = r"\$?([\d,]+(?:\.\d+)?)\s*([kKmM]?)"
_A = r"(Bitcoin|Ethereum|Solana|XRP|BTC|ETH|SOL)"

_PATTERNS = [
    ("above", re.compile(rf"^Will the price of {_A} be (?:above|greater than) {_NUM} on ", re.I)),
    ("below", re.compile(rf"^Will the price of {_A} be (?:below|less than) {_NUM} on ", re.I)),
    ("between", re.compile(rf"^Will the price of {_A} be between {_NUM} and {_NUM} on ", re.I)),
    ("above", re.compile(rf"^{_A} above {_NUM} on ", re.I)),
    ("reach", re.compile(rf"^Will {_A} reach {_NUM} ", re.I)),
    ("dip", re.compile(rf"^Will {_A} dip to {_NUM} ", re.I)),
    ("updown", re.compile(rf"^{_A} Up or Down - ", re.I)),
]
_RANGE = re.compile(r"(\d{1,2})(?::(\d{2}))?(AM|PM)-(\d{1,2})(?::(\d{2}))?(AM|PM) ET")
_HOUR = re.compile(r", (\d{1,2})(AM|PM) ET$")


_MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                            "september", "october", "november", "december"])}
_TITLE_DATE = re.compile(r"\bon (January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2})\b", re.I)
_RULE_TIME = re.compile(r"(\d{1,2}):(\d{2}) in the ET timezone")


def rule_expiry(question: str, description: str, t_end: float) -> float:
    """Settlement instant from the title's date and the rule's stated Eastern time.

    The API's end date is sometimes date-only (midnight UTC), hours before the candle the rules name.
    Falls back to `t_end` when the title or rules do not state a date and time.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    d, tm = _TITLE_DATE.search(question or ""), _RULE_TIME.search(description or "")
    if not (d and tm) or not np.isfinite(t_end):
        return t_end
    ny = ZoneInfo("America/New_York")
    year = datetime.fromtimestamp(t_end, ny).year
    best = t_end
    for y in (year - 1, year, year + 1):
        try:
            cand = datetime(y, _MONTHS[d[1].lower()], int(d[2]), int(tm[1]), int(tm[2]), tzinfo=ny).timestamp()
        except ValueError:
            continue
        if abs(cand - t_end) < 3 * 86400:
            best = cand
    return best


def _num(s, suffix):
    v = float(s.replace(",", ""))
    return v * {"k": 1e3, "m": 1e6}.get(suffix.lower(), 1.0)


def _minutes(h, mnt, ap):
    h = int(h) % 12 + (12 if ap.upper() == "PM" else 0)
    return h * 60 + int(mnt or 0)


def parse(markets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in markets.itertuples():
        q = r.question
        for kind, pat in _PATTERNS:
            mt = pat.match(q)
            if not mt:
                continue
            g = mt.groups()
            sym = ASSETS[g[0].lower()]
            k = k2 = np.nan
            window = np.nan
            if kind in ("above", "below", "reach", "dip"):
                k = _num(g[1], g[2])
            elif kind == "between":
                k, k2 = _num(g[1], g[2]), _num(g[3], g[4])
            if kind == "updown":
                rg = _RANGE.search(q)
                if rg:
                    a = _minutes(rg[1], rg[2], rg[3])
                    b = _minutes(rg[4], rg[5], rg[6])
                    window = ((b - a) % 1440) * 60
                elif _HOUR.search(q):
                    window = 3600
                else:
                    window = 86400  # daily contracts: noon ET to noon ET
            if kind in ("reach", "dip"):
                window = 86400
            desc = r.description or ""
            if "chain.link" in desc.lower() or "chainlink" in desc.lower():
                src = "chainlink"
            elif "1 hour candle" in desc or '"1h"' in desc or "1H" in desc:
                src = "binance_1h"
            else:
                src = "binance_1m"
            rows.append((r.market_id, sym, kind, k, k2, window, src))
            break
    out = pd.DataFrame(rows, columns=["market_id", "symbol", "kind", "k", "k2", "window", "source"])
    out = out.merge(markets[["market_id", "t_end", "t0", "t_close", "y", "volume", "fee_rate", "question", "description"]], on="market_id")
    out["t_end_api"] = out.t_end
    fix = out.kind.isin(["above", "below", "between"]) & (out.source == "binance_1m")
    out.loc[fix, "t_end"] = [rule_expiry(q, d, t) for q, d, t in zip(out.question[fix], out.description[fix], out.t_end[fix])]
    return out.drop(columns=["description"])


def load_spot(symbol: str, root="research/data/raw/crypto") -> pd.DataFrame:
    files = sorted(Path(root).glob(f"{symbol}_*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return df.drop_duplicates("t").sort_values("t").reset_index(drop=True)


class Spot:
    """Minute-indexed spot with O(1) lookups. `t` is the candle open time in epoch seconds."""

    def __init__(self, df: pd.DataFrame):
        self.t0 = int(df.t.iloc[0])
        n = int((df.t.iloc[-1] - self.t0) // 60) + 1
        idx = ((df.t.to_numpy() - self.t0) // 60).astype(int)
        self.open, self.close, self.high, self.low = (np.full(n, np.nan) for _ in range(4))
        self.open[idx], self.close[idx] = df.open.to_numpy(), df.close.to_numpy()
        self.high[idx], self.low[idx] = df.high.to_numpy(), df.low.to_numpy()
        self.n = n

    def _i(self, t):
        return ((np.asarray(t, dtype=np.int64) - self.t0) // 60).astype(int)

    def at(self, field, t):
        i = self._i(t)
        ok = (i >= 0) & (i < self.n)
        return np.where(ok, getattr(self, field)[np.clip(i, 0, self.n - 1)], np.nan)

    def last_close(self, t):
        """Close of the last completed minute candle before time t (what a trader sees at t)."""
        return self.at("close", np.asarray(t, dtype=np.int64) - 60)


def settle(c: pd.DataFrame, spots: dict[str, Spot]) -> pd.Series:
    """Replay each contract's settlement from spot data. NaN where data is missing."""
    out = np.full(len(c), np.nan)
    for i, r in enumerate(c.itertuples()):
        sp = spots.get(r.symbol)
        if sp is None or not np.isfinite(r.t_end):
            continue
        T = int(r.t_end)
        if r.kind in ("above", "below", "between"):
            px = sp.at("close", T if r.source == "binance_1m" else T - 60)
            if not np.isfinite(px):
                continue
            out[i] = {"above": px > r.k, "below": px < r.k, "between": r.k <= px < r.k2}[r.kind]
        elif r.kind == "updown":
            o, cl = sp.at("open", T - int(r.window)), sp.at("close", T - 60)
            if np.isfinite(o) and np.isfinite(cl):
                out[i] = cl >= o
        else:
            a, b = sp._i(T - int(r.window)), sp._i(T)
            if a < 0 or b > sp.n:
                continue
            out[i] = (np.nanmax(sp.high[a:b]) >= r.k) if r.kind == "reach" else (np.nanmin(sp.low[a:b]) <= r.k)
    return pd.Series(out, index=c.index)
