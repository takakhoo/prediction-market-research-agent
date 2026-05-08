from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .config import PolymarketConfig
from .gamma_client import GammaMarketsClient
from .market_intel_repository import MarketBundle, MarketIntelRepository


@dataclass(frozen=True)
class MarketIngestStats:
    fetched_markets: int
    upserted_markets: int
    total_outcomes: int
    high_competition_markets: int


class MarketIngestService:
    """Fetches active/open Polymarket markets and persists normalized rows to Postgres."""

    def __init__(
        self,
        config: PolymarketConfig,
        gamma: GammaMarketsClient,
        repository: MarketIntelRepository,
        log_fn: Callable[[str], None] | None = None,
    ):
        self.config = config
        self.gamma = gamma
        self.repository = repository
        self._log = log_fn or (lambda _: None)

    def ingest_once(self) -> MarketIngestStats:
        markets = self.fetch_open_markets()
        return self.ingest_market_rows(markets)

    def ingest_market_rows(self, markets: list[dict[str, Any]], *, active_only: bool = True) -> MarketIngestStats:
        if active_only:
            markets = [
                market
                for market in markets
                if bool(market.get("active")) and not bool(market.get("closed")) and not bool(market.get("archived"))
            ]

        bundles: list[MarketBundle] = []
        high_competition = 0
        total_outcomes = 0

        observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        for market in markets:
            bundle = self._normalize_market_bundle(market, observed_at=observed_at)
            bundles.append(bundle)
            total_outcomes += len(bundle.outcomes)
            if bool(bundle.market.get("high_competition")):
                high_competition += 1

        upserted = self.repository.upsert_market_bundles(
            bundles,
            store_outcomes=self.config.market_store_outcomes,
            store_snapshots=self.config.market_store_snapshots,
        )

        return MarketIngestStats(
            fetched_markets=len(markets),
            upserted_markets=upserted,
            total_outcomes=total_outcomes,
            high_competition_markets=high_competition,
        )

    def fetch_open_markets(self) -> list[dict[str, Any]]:
        all_markets: list[dict[str, Any]] = []
        offset = 0
        for page_num in range(1, self.config.ingest_max_pages + 1):
            self._log(f"fetch_page page={page_num} offset={offset} limit={self.config.ingest_page_limit}")
            page = self.gamma.list_markets(
                limit=self.config.ingest_page_limit,
                offset=offset,
                active=True,
                closed=False,
                archived=False,
            )
            self._log(f"fetch_page_result page={page_num} count={len(page)}")
            if not page:
                break
            all_markets.extend(page)
            if len(page) < self.config.ingest_page_limit:
                break
            offset += len(page)

        # Keep only active/open rows even if upstream filtering behavior changes.
        return [m for m in all_markets if bool(m.get("active")) and not bool(m.get("closed"))]

    def _normalize_market_bundle(self, market: dict[str, Any], *, observed_at: str) -> MarketBundle:
        market_id = str(market.get("id") or "")
        if not market_id:
            raise ValueError("Gamma market row is missing id")

        outcomes = self._normalize_outcomes(market, market_id=market_id)
        event_meta = _extract_event_metadata(market)
        volume_usd = _safe_float(market.get("volumeNum") or market.get("volume"))
        liquidity_usd = _safe_float(market.get("liquidityNum") or market.get("liquidity"))
        rules_text = _extract_rules_text(market)
        market_context = _extract_market_context(market)
        question = str(market.get("question") or "").strip()
        rules_hash = _rules_hash(question=question, rules_text=rules_text)
        archetype = _classify_market_archetype(market, outcomes)

        market_row = {
            "market_id": market_id,
            "condition_id": _optional_text(market.get("conditionId")),
            "question_id": _optional_text(market.get("questionID")),
            "event_id": event_meta["event_id"],
            "event_slug": event_meta["event_slug"],
            "slug": _optional_text(market.get("slug")),
            "question": question or market_id,
            "description": _optional_text(market.get("description")),
            "rules_text": rules_text,
            "market_context": market_context,
            "market_archetype": archetype,
            "is_local_candidate": None,
            "local_score": None,
            "local_reason_json": {},
            "active": bool(market.get("active", False)),
            "closed": bool(market.get("closed", False)),
            "archived": bool(market.get("archived", False)),
            "accepting_orders": _optional_bool(market.get("acceptingOrders")),
            "enable_order_book": _optional_bool(market.get("enableOrderBook")),
            "high_competition": bool(
                volume_usd is not None and volume_usd >= self.config.high_competition_volume_usd
            ),
            "end_date": _optional_text(market.get("endDate")),
            "rules_hash": rules_hash,
            "raw_json": market,
        }

        snapshot_row = {
            "market_id": market_id,
            "observed_at": observed_at,
            "best_bid": _safe_float(market.get("bestBid")),
            "best_ask": _safe_float(market.get("bestAsk")),
            "last_trade_price": _safe_float(market.get("lastTradePrice")),
            "volume_usd": volume_usd,
            "liquidity_usd": liquidity_usd,
            "spread": _safe_float(market.get("spread")),
            "raw_json": {
                "id": market_id,
                "question": question,
                "active": bool(market.get("active", False)),
                "closed": bool(market.get("closed", False)),
                "bestBid": market.get("bestBid"),
                "bestAsk": market.get("bestAsk"),
                "lastTradePrice": market.get("lastTradePrice"),
                "volume": market.get("volume"),
                "volumeNum": market.get("volumeNum"),
                "liquidity": market.get("liquidity"),
                "liquidityNum": market.get("liquidityNum"),
            },
        }

        return MarketBundle(market=market_row, outcomes=outcomes, snapshot=snapshot_row)

    def _normalize_outcomes(self, market: dict[str, Any], *, market_id: str) -> list[dict[str, Any]]:
        labels, prices = self.gamma.parse_outcomes(market)
        token_ids = _parse_json_list(market.get("clobTokenIds"))

        items: list[dict[str, Any]] = []
        for index, label in enumerate(labels):
            probability = prices[index] if index < len(prices) else None
            token_id = str(token_ids[index]) if index < len(token_ids) else None
            is_likely = bool(
                probability is not None and probability >= self.config.likely_probability_threshold
            )
            is_unlikely = bool(
                probability is not None and probability <= self.config.unlikely_probability_threshold
            )
            items.append(
                {
                    "market_id": market_id,
                    "outcome_index": index,
                    "outcome_label": str(label),
                    "token_id": token_id,
                    "price": probability,
                    "probability": probability,
                    "is_likely": is_likely,
                    "is_unlikely": is_unlikely,
                    "raw_json": {
                        "label": label,
                        "price": probability,
                        "token_id": token_id,
                    },
                }
            )
        return items


def _rules_hash(*, question: str, rules_text: str | None) -> str | None:
    merged = f"{question.strip()}||{(rules_text or '').strip()}".strip()
    if not merged:
        return None
    return hashlib.sha256(merged.encode("utf-8")).hexdigest()


def _extract_event_metadata(market: dict[str, Any]) -> dict[str, str | None]:
    event_id = _optional_text(market.get("eventId"))
    event_slug = _optional_text(market.get("eventSlug"))

    events = market.get("events")
    if isinstance(events, list) and events:
        first = events[0] if isinstance(events[0], dict) else {}
        if event_id is None:
            event_id = _optional_text(first.get("id"))
        if event_slug is None:
            event_slug = _optional_text(first.get("slug"))

    return {"event_id": event_id, "event_slug": event_slug}


def _extract_rules_text(market: dict[str, Any]) -> str | None:
    # Gamma fields vary by market age/version; prioritize explicit rule-like fields.
    for key in ("rules", "resolutionCriteria", "description"):
        value = _optional_text(market.get(key))
        if value:
            return value
    return None


def _extract_market_context(market: dict[str, Any]) -> str | None:
    for key in ("marketContext", "additionalContext", "context"):
        value = _optional_text(market.get(key))
        if value:
            return value
    return None


def _classify_market_archetype(market: dict[str, Any], outcomes: list[dict[str, Any]]) -> str:
    labels = [item["outcome_label"].strip().lower() for item in outcomes]
    count = len(labels)
    group_item_title = _optional_text(market.get("groupItemTitle"))
    question = _optional_text(market.get("question")) or ""
    question_lower = question.lower()

    if count == 0:
        return "unknown"
    if count == 2 and set(labels) == {"yes", "no"}:
        if group_item_title:
            return "binary_recurring"
        if " by " in question_lower:
            return "binary_deadline_series"
        return "binary_oneoff"
    if count > 2:
        return "categorical_group"
    if count == 2 and set(labels) == {"long", "short"}:
        return "scalar"
    return "unknown"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
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
