"""Map Polymarket tags, outcome labels, and question text to one coarse category per market."""
from __future__ import annotations

import re

import pandas as pd

_CRYPTO = {"crypto", "crypto prices", "bitcoin", "ethereum", "solana", "xrp", "ripple", "dogecoin", "up or down", "hype", "bnb"}
_SPORTS = {"sports", "games", "nba", "nfl", "mlb", "nhl", "soccer", "epl", "tennis", "golf", "cbb", "cfb", "ufc", "esports",
           "formula 1", "f1", "cricket", "boxing", "mma", "premier league", "champions league", "basketball", "football",
           "baseball", "hockey", "wnba", "nfl (all)", "cfb (all)", "pga tour", "la liga", "serie a", "bundesliga", "chess"}
_POLITICS = {"politics", "elections", "us election", "deprec usa election", "global elections", "trump", "trump presidency",
             "u.s. politics", "congress", "kamala", "biden", "primaries", "world elections", "courts", "supreme court", "midterms"}
_GEO = {"geopolitics", "world", "middle east", "ukraine", "israel", "iran", "russia", "china", "war", "foreign policy", "gaza", "venezuela"}
_ECON = {"economy", "fed", "fed rates", "inflation", "economic policy", "jobs report", "gdp", "macro indicators", "tariffs", "trade war", "recession"}
_FIN = {"finance", "stocks", "earnings", "equities", "business", "ipos", "ipo", "commodities", "indices", "stock prices", "big tech", "companies"}
_WEATHER = {"weather", "climate", "temperature", "daily temperature", "hurricanes", "climate & weather"}
_MENTIONS = {"mentions", "tweet markets", "twitter", "elon tweets"}
_CULTURE = {"culture", "movies", "music", "awards", "pop culture", "celebrities", "tv", "oscars", "grammys", "box office", "youtube", "mrbeast"}
_TECH = {"tech", "ai", "openai", "science", "space", "spacex"}

_ORDER = [("weather", _WEATHER), ("mentions", _MENTIONS), ("crypto", _CRYPTO), ("sports", _SPORTS), ("economy", _ECON),
          ("finance", _FIN), ("politics", _POLITICS), ("geopolitics", _GEO), ("tech", _TECH), ("culture", _CULTURE)]

_UPDOWN_Q = re.compile(r"\bup or down\b", re.I)
_CRYPTO_Q = re.compile(r"\b(bitcoin|btc|ethereum|eth|solana|sol|xrp|dogecoin|doge)\b", re.I)


def categorize(tags: str, outcome0: str | None, question: str, sports_type: str | None) -> str:
    tagset = {t.strip().lower() for t in (tags or "").split("|") if t.strip()}
    if isinstance(sports_type, str) and sports_type:
        return "sports"
    if (outcome0 == "Up" or _UPDOWN_Q.search(question or "")) and (tagset & _CRYPTO or _CRYPTO_Q.search(question or "")):
        return "crypto_updown"
    for name, keys in _ORDER:
        if tagset & keys:
            return name
    return "other"


def add_category(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["category"] = [categorize(t, o, q, s) for t, o, q, s in zip(df.tags, df.outcome0, df.question, df.sports_type)]
    return df
