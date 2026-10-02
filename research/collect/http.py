"""Shared polite HTTP client for the public, credential-free endpoints."""
from __future__ import annotations

import random
import time

import httpx

_client = httpx.Client(
    timeout=httpx.Timeout(40.0, connect=15.0),
    headers={"User-Agent": "prediction-market-research-agent/2.0 (research; read-only)"},
    limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
    http2=False,
)


def get_json(url: str, params: dict | None = None, retries: int = 12):
    delay = 1.0
    for attempt in range(retries):
        try:
            r = _client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 404, 422):
                return {"_error": r.status_code, "_body": r.text[:300]}
            if r.status_code == 429:
                time.sleep(0.5 + random.random())
                delay = min(delay * 1.3, 8.0)
                continue
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(delay + random.random())
        delay = min(delay * 2, 60.0)
    return {"_error": "retries_exhausted"}
