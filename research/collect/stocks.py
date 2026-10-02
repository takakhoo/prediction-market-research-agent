"""Daily and hourly bars for the tickers behind Polymarket's stock-linked contracts (Yahoo chart API)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .http import _client

OUT = Path("research/data/raw/stocks")
TICKERS = ["NVDA", "GOOGL", "TSLA", "AAPL", "META", "AMZN", "MSFT", "PLTR", "NFLX", "OPEN", "ABNB", "HOOD", "COIN",
           "RKLB", "MU", "SPY", "QQQ", "EWY", "^GSPC", "^VIX", "CL=F", "NG=F", "GC=F", "SI=F"]
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"


def pull(ticker: str, interval: str, rng: str) -> pd.DataFrame:
    r = _client.get(URL.format(ticker), params={"interval": interval, "range": rng, "includePrePost": "false"},
                    headers={"User-Agent": "Mozilla/5.0"})
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"t": res["timestamp"], "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]})
    return df.dropna(subset=["close"]).reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for tk in TICKERS:
        name = tk.replace("^", "").replace("=F", "_F")
        for interval, rng in (("1d", "5y"), ("1h", "730d")):
            try:
                df = pull(tk, interval, rng)
                df.to_parquet(OUT / f"{name}_{interval}.parquet", index=False)
                print(name, interval, len(df), flush=True)
            except Exception as e:  # one bad ticker should not stop the rest
                print(name, interval, "FAILED", repr(e)[:80], flush=True)


if __name__ == "__main__":
    main()
