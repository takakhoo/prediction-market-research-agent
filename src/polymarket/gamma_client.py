from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import PolymarketConfig
from .http import HttpJsonClient


@dataclass(frozen=True)
class MarketSummary:
    market_id: str
    condition_id: str
    slug: str
    question: str
    active: bool
    closed: bool
    end_date_iso: str | None
    volume: float | None
    liquidity: float | None


class GammaMarketsClient:
    """Read-only Polymarket Gamma API client for market discovery."""

    def __init__(self, config: PolymarketConfig, http_client: HttpJsonClient | None = None):
        self.config = config
        self.http = http_client or HttpJsonClient(timeout_seconds=config.timeout_seconds)

    def list_markets(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        active: bool | None = None,
        closed: bool | None = None,
        archived: bool | None = None,
        search: str | None = None,
        tag_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params = {
            "limit": max(1, min(limit, 500)),
            "offset": max(0, offset),
            "active": active,
            "closed": closed,
            "archived": archived,
            "search": search,
            "tag_id": tag_id,
        }
        payload = self.http.get_json(self.config.gamma_base_url, "/markets", params=params)
        if isinstance(payload, list):
            return payload
        raise RuntimeError("Unexpected Gamma /markets response format")

    def get_market_by_id(self, market_id: str) -> dict[str, Any] | None:
        payload = self.http.get_json(self.config.gamma_base_url, f"/markets/{market_id}", params=None)
        if isinstance(payload, dict):
            return payload
        return None

    def get_market_by_slug(self, slug: str) -> dict[str, Any] | None:
        payload = self.http.get_json(self.config.gamma_base_url, f"/markets/slug/{slug}", params=None)
        if isinstance(payload, dict):
            return payload
        return None

    def get_event_by_slug(self, slug: str) -> dict[str, Any] | None:
        payload = self.http.get_json(self.config.gamma_base_url, "/events", params={"slug": slug})
        if isinstance(payload, list) and payload:
            first = payload[0]
            return first if isinstance(first, dict) else None
        if isinstance(payload, dict):
            return payload
        return None

    def summarize(self, markets: Iterable[dict[str, Any]]) -> list[MarketSummary]:
        summaries: list[MarketSummary] = []
        for market in markets:
            summaries.append(
                MarketSummary(
                    market_id=str(market.get("id") or ""),
                    condition_id=str(market.get("conditionId") or ""),
                    slug=str(market.get("slug") or ""),
                    question=str(market.get("question") or ""),
                    active=bool(market.get("active", False)),
                    closed=bool(market.get("closed", False)),
                    end_date_iso=_normalize_iso(market.get("endDate")),
                    volume=_safe_float(market.get("volume") or market.get("volumeNum")),
                    liquidity=_safe_float(market.get("liquidity") or market.get("liquidityNum")),
                )
            )
        return summaries

    @staticmethod
    def parse_outcomes(market: dict[str, Any]) -> tuple[list[str], list[float]]:
        outcomes = _parse_json_list(market.get("outcomes"))
        prices_raw = _parse_json_list(market.get("outcomePrices"))
        prices = [_safe_float(value) or 0.0 for value in prices_raw]
        return [str(item) for item in outcomes], prices


def _find_by_slug(markets: Iterable[dict[str, Any]], slug: str) -> dict[str, Any] | None:
    target = slug.strip().lower()
    for market in markets:
        if str(market.get("slug") or "").strip().lower() == target:
            return market
    return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _normalize_iso(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(microsecond=0).isoformat()
    return None
