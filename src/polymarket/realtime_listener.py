from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable

from src.discovery.tdlib_client import (
    TDLibDiscoveryClient,
    extract_td_message_text,
    td_message_content_type,
    td_timestamp_to_iso,
)

from .config import PolymarketConfig
from .llm_runtime import JSONReasoningClient, LLMRuntimeUnavailable, OpenAIJSONReasoningClient, resolve_reasoning_client
from .market_intel_repository import MarketIntelRepository
from .prompt_store import load_prompt_template, render_prompt_template
from .validation import probability


@dataclass(frozen=True)
class RealtimeBatchMatchDecision:
    market_id: str
    confidence: float
    reason_short: str
    market_label: str


@dataclass(frozen=True)
class RealtimeListenerSnapshot:
    started: bool
    watched_channels: int
    watched_markets: int
    queued_messages: int
    received_messages: int
    stored_messages: int
    evaluated_messages: int
    matched_messages: int
    matched_pairs: int
    activations_inserted: int
    ai_failures: int
    last_binding_refresh_at: str | None
    last_message_at: str | None
    last_message_chat_id: int | None
    last_message_id: int | None
    last_message_preview: str
    link_source: str
    source_file: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    effective_size = max(1, int(size))
    return [items[index : index + effective_size] for index in range(0, len(items), effective_size)]


def _safe_sender_payload(message: Any) -> dict[str, Any]:
    sender = getattr(message, "sender_id", None)
    if sender is None:
        return {}
    payload = {"sender_type": str(getattr(sender, "ID", "") or "")}
    user_id = getattr(sender, "user_id", None)
    if user_id is not None:
        try:
            payload["sender_user_id"] = int(user_id)
        except (TypeError, ValueError):
            pass
    chat_id = getattr(sender, "chat_id", None)
    if chat_id is not None:
        try:
            payload["sender_chat_id"] = int(chat_id)
        except (TypeError, ValueError):
            pass
    return payload


class RealtimeMessageBatchMatcher:
    def __init__(
        self,
        *,
        config: PolymarketConfig | None = None,
        reasoning_client: JSONReasoningClient | None = None,
        model: str | None = None,
        candidate_batch_size: int = 24,
        min_confidence: float = 0.8,
    ):
        self.config = config or PolymarketConfig.from_env()
        if reasoning_client is not None:
            self.reasoning_client = reasoning_client
        elif self.config.ai_message_matcher_api_key:
            self.reasoning_client = OpenAIJSONReasoningClient(
                api_key=self.config.ai_message_matcher_api_key,
                base_url=self.config.ai_message_matcher_base_url or self.config.openai_base_url,
                http_referer=(
                    self.config.ai_message_matcher_http_referer or self.config.openai_http_referer
                ),
                app_name=(
                    self.config.ai_message_matcher_app_name or self.config.openai_app_name
                ),
                timeout_seconds=self.config.openai_timeout_seconds,
            )
        else:
            self.reasoning_client = resolve_reasoning_client(self.config, required=True)
        self.model = model or self.config.ai_telegram_message_matcher_model
        if not self.model:
            raise LLMRuntimeUnavailable(
                "No AI_TELEGRAM_MESSAGE_MATCHER_MODEL or OPENROUTER_MODEL configured."
            )
        self.candidate_batch_size = max(1, min(int(candidate_batch_size), 40))
        threshold = probability(min_confidence)
        if threshold is None:
            raise ValueError("min_confidence must be a finite number in [0,1]")
        self.min_confidence = threshold
        self.matcher_version = f"ai_message_batch_matcher_v1:{self.model}"

    def _default_system_prompt(self) -> str:
        fallback = (
            "You classify whether one Telegram message is materially relevant to any of the candidate "
            "Polymarket markets. Return strict JSON only. Be conservative. Only return markets that the "
            "message clearly updates, narrows, or helps resolve."
        )
        return load_prompt_template("telegram_live_message_matcher/system.txt", fallback)

    def _default_user_prompt(self, *, message_payload: dict[str, Any], candidate_payload: list[dict[str, Any]]) -> str:
        fallback_template = (
            "Determine which candidate markets are materially updated by this Telegram message.\n\n"
            "MESSAGE_JSON:\n{{MESSAGE_JSON}}\n\n"
            "CANDIDATE_MARKETS_JSON:\n{{MARKETS_JSON}}\n\n"
            "Return JSON with matches as an array of candidate_id/confidence/reason_short.\n"
            "Do not include non-matches."
        )
        template = load_prompt_template("telegram_live_message_matcher/user.txt", fallback_template)
        return render_prompt_template(
            template,
            {
                "MESSAGE_JSON": json.dumps(message_payload, ensure_ascii=False, indent=2),
                "MARKETS_JSON": json.dumps(candidate_payload, ensure_ascii=False, indent=2),
            },
        )

    @staticmethod
    def _schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_id": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "reason_short": {"type": "string"},
                        },
                        "required": ["candidate_id", "confidence", "reason_short"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["matches"],
            "additionalProperties": False,
        }

    @staticmethod
    def _build_message_payload(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "chat_id": int(item["chat_id"]),
            "channel_title": str(item.get("channel_title") or ""),
            "channel_username": str(item.get("channel_username") or ""),
            "message_id": int(item["message_id"]),
            "posted_at": str(item.get("posted_at") or ""),
            "text": str(item.get("text") or "")[:3000],
            "has_media": bool(item.get("has_media", False)),
            "content_type": str(item.get("content_type") or ""),
        }

    @staticmethod
    def _build_candidate_payload(batch: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        payload: list[dict[str, Any]] = []
        lookup: dict[str, dict[str, Any]] = {}
        for index, market in enumerate(batch, start=1):
            candidate_id = f"M{index:02d}"
            lookup[candidate_id] = market
            payload.append(
                {
                    "candidate_id": candidate_id,
                    "market_id": str(market["market_id"]),
                    "market_label": str(market.get("requested_name") or market.get("question") or market["market_id"]),
                    "bucket": str(market.get("requested_bucket") or market.get("matched_scope_label") or ""),
                    "question": str(market.get("question") or "")[:360],
                    "rules_text": str(market.get("rules_text") or "")[:320],
                    "market_context": str(market.get("market_context") or "")[:320],
                }
            )
        return payload, lookup

    def evaluate_message(self, *, item: dict[str, Any], markets: list[dict[str, Any]]) -> list[RealtimeBatchMatchDecision]:
        if not markets:
            return []
        message_payload = self._build_message_payload(item)
        decisions: list[RealtimeBatchMatchDecision] = []
        seen_market_ids: set[str] = set()

        for batch in _chunked(markets, self.candidate_batch_size):
            candidate_payload, candidate_lookup = self._build_candidate_payload(batch)
            payload = self.reasoning_client.generate_json(
                model=self.model,
                system_prompt=self._default_system_prompt(),
                user_prompt=self._default_user_prompt(
                    message_payload=message_payload,
                    candidate_payload=candidate_payload,
                ),
                schema_name="telegram_live_message_matcher",
                schema=self._schema(),
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
                raise ValueError("Matcher response must contain a matches array")
            for raw_item in payload["matches"]:
                if not isinstance(raw_item, dict):
                    continue
                candidate_id = str(raw_item.get("candidate_id") or "").strip()
                if not candidate_id or candidate_id not in candidate_lookup:
                    continue
                confidence = probability(raw_item.get("confidence"))
                reason = raw_item.get("reason_short")
                if confidence is None or confidence < self.min_confidence or not isinstance(reason, str) or not reason.strip():
                    continue
                market = candidate_lookup[candidate_id]
                market_id = str(market["market_id"])
                if market_id in seen_market_ids:
                    continue
                seen_market_ids.add(market_id)
                decisions.append(
                    RealtimeBatchMatchDecision(
                        market_id=market_id,
                        confidence=confidence,
                        reason_short=reason.strip()[:240],
                        market_label=str(market.get("requested_name") or market.get("question") or market_id),
                    )
                )

        decisions.sort(key=lambda item: (-item.confidence, item.market_id))
        return decisions


class MarketTelegramRealtimeListenerService:
    def __init__(
        self,
        *,
        repository: MarketIntelRepository,
        tdlib_client: TDLibDiscoveryClient,
        matcher: RealtimeMessageBatchMatcher | None = None,
        log_fn: Callable[[str], None] | None = None,
    ):
        self.repository = repository
        self.tdlib_client = tdlib_client
        self.matcher = matcher or RealtimeMessageBatchMatcher()
        self._log = log_fn or (lambda _: None)
        self._bindings_by_chat: dict[int, dict[str, Any]] = {}
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._workers: list[asyncio.Task[Any]] = []
        self._bindings_refresh_task: asyncio.Task[Any] | None = None
        self._handler_ref: Any = None
        self._started = False
        self._worker_concurrency = 4
        self._bindings_refresh_seconds = 90
        self._link_source = "ai_handpicked_batch_v1"
        self._source_file = ""
        self._channel_limit = 500
        self._markets_per_channel = 25

        self._received_messages = 0
        self._stored_messages = 0
        self._evaluated_messages = 0
        self._matched_messages = 0
        self._matched_pairs = 0
        self._activations_inserted = 0
        self._ai_failures = 0
        self._last_binding_refresh_at: str | None = None
        self._last_message_at: str | None = None
        self._last_message_chat_id: int | None = None
        self._last_message_id: int | None = None
        self._last_message_preview = ""

    async def start(
        self,
        *,
        channel_limit: int = 500,
        markets_per_channel: int = 25,
        link_source: str = "ai_handpicked_batch_v1",
        source_file: str | None = None,
        worker_concurrency: int = 4,
        bindings_refresh_seconds: int = 90,
    ) -> None:
        if self._started:
            return
        self._channel_limit = max(1, min(int(channel_limit), 5000))
        self._markets_per_channel = max(1, min(int(markets_per_channel), 200))
        self._link_source = str(link_source or "ai_handpicked_batch_v1").strip() or "ai_handpicked_batch_v1"
        self._source_file = str(source_file or "").strip()
        self._worker_concurrency = max(1, min(int(worker_concurrency), 16))
        self._bindings_refresh_seconds = max(10, min(int(bindings_refresh_seconds), 3600))

        await self.refresh_bindings()
        for index in range(self._worker_concurrency):
            self._workers.append(asyncio.create_task(self._worker_loop(index + 1)))
        self._bindings_refresh_task = asyncio.create_task(self._refresh_loop())
        self._handler_ref = await self.tdlib_client.add_update_handler(
            self._on_new_message,
            update_type="updateNewMessage",
        )
        self._started = True
        self._log(
            "realtime_listener_started "
            f"watched_channels={len(self._bindings_by_chat)} "
            f"watched_markets={self._count_watched_markets()} "
            f"link_source={self._link_source} "
            f"source_file={self._source_file or 'all'}"
        )

    async def stop(self) -> None:
        if self._bindings_refresh_task is not None:
            self._bindings_refresh_task.cancel()
            try:
                await self._bindings_refresh_task
            except asyncio.CancelledError:
                pass
            self._bindings_refresh_task = None

        if self._handler_ref is not None:
            await self.tdlib_client.remove_update_handler(self._handler_ref, update_type="updateNewMessage")
            self._handler_ref = None

        for task in self._workers:
            task.cancel()
        for task in self._workers:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._workers = []
        self._started = False

    async def refresh_bindings(self) -> None:
        rows = await asyncio.to_thread(
            self.repository.get_saved_channel_market_bindings,
            channel_limit=self._channel_limit,
            markets_per_channel=self._markets_per_channel,
            link_source=self._link_source,
            source_file=self._source_file,
        )
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            chat_id = int(row["chat_id"])
            if chat_id not in grouped:
                grouped[chat_id] = {
                    "channel_title": row.get("channel_title"),
                    "channel_username": row.get("channel_username"),
                    "markets": [],
                }
            grouped[chat_id]["markets"].append(
                {
                    "market_id": str(row["market_id"]),
                    "question": str(row.get("question") or ""),
                    "rules_text": str(row.get("rules_text") or ""),
                    "market_context": str(row.get("market_context") or ""),
                    "market_archetype": str(row.get("market_archetype") or "unknown"),
                    "market_rank": int(row.get("market_rank") or 0),
                    "priority_rank": row.get("priority_rank"),
                    "requested_name": str(row.get("requested_name") or row.get("question") or row["market_id"]),
                    "requested_bucket": str(row.get("requested_bucket") or row.get("matched_scope_label") or ""),
                    "matched_scope_label": str(row.get("matched_scope_label") or ""),
                    "matched_group_slug": str(row.get("matched_group_slug") or ""),
                    "matched_group_title": str(row.get("matched_group_title") or ""),
                }
            )
        self._bindings_by_chat = grouped
        self._last_binding_refresh_at = _utc_now_iso()
        self._log(
            "realtime_bindings_refreshed "
            f"watched_channels={len(self._bindings_by_chat)} "
            f"watched_markets={self._count_watched_markets()}"
        )

    def snapshot(self) -> RealtimeListenerSnapshot:
        return RealtimeListenerSnapshot(
            started=self._started,
            watched_channels=len(self._bindings_by_chat),
            watched_markets=self._count_watched_markets(),
            queued_messages=self._queue.qsize(),
            received_messages=self._received_messages,
            stored_messages=self._stored_messages,
            evaluated_messages=self._evaluated_messages,
            matched_messages=self._matched_messages,
            matched_pairs=self._matched_pairs,
            activations_inserted=self._activations_inserted,
            ai_failures=self._ai_failures,
            last_binding_refresh_at=self._last_binding_refresh_at,
            last_message_at=self._last_message_at,
            last_message_chat_id=self._last_message_chat_id,
            last_message_id=self._last_message_id,
            last_message_preview=self._last_message_preview,
            link_source=self._link_source,
            source_file=self._source_file,
        )

    def _count_watched_markets(self) -> int:
        market_ids = {
            str(market["market_id"])
            for binding in self._bindings_by_chat.values()
            for market in list(binding.get("markets") or [])
        }
        return len(market_ids)

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._bindings_refresh_seconds)
                await self.refresh_bindings()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log(f"realtime_bindings_refresh_error {type(exc).__name__}: {exc}")

    async def _on_new_message(self, _client: Any, update: Any) -> None:
        message = getattr(update, "message", None)
        if message is None:
            return
        chat_id = int(getattr(message, "chat_id", 0) or 0)
        binding = self._bindings_by_chat.get(chat_id)
        if binding is None:
            return

        message_id = int(getattr(message, "id", 0) or 0)
        if message_id <= 0:
            return
        text = extract_td_message_text(message).strip()
        if not text:
            return

        posted_at = td_timestamp_to_iso(getattr(message, "date", 0)) or _utc_now_iso()
        content_type = td_message_content_type(message)
        username = str(binding.get("channel_username") or "").strip()
        raw_json = {
            "source": "updateNewMessage",
            "content_type": content_type,
            "public_url": f"https://t.me/{username}/{message_id}" if username else None,
            **_safe_sender_payload(message),
        }
        item = {
            "chat_id": chat_id,
            "channel_title": str(binding.get("channel_title") or ""),
            "channel_username": username,
            "message_id": message_id,
            "posted_at": posted_at,
            "text": text,
            "has_media": content_type != "messageText",
            "content_type": content_type,
            "raw_json": raw_json,
            "markets": list(binding.get("markets") or []),
        }
        self._received_messages += 1
        self._last_message_at = posted_at
        self._last_message_chat_id = chat_id
        self._last_message_id = message_id
        self._last_message_preview = text[:180]
        await self._queue.put(item)

    async def _worker_loop(self, worker_index: int) -> None:
        while True:
            item = await self._queue.get()
            try:
                await self._process_message_item(item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log(
                    f"realtime_listener_worker_error worker={worker_index} "
                    f"chat_id={item.get('chat_id')} message_id={item.get('message_id')} "
                    f"error={type(exc).__name__}: {exc}"
                )
            finally:
                self._queue.task_done()

    async def _process_message_item(self, item: dict[str, Any]) -> None:
        message_rows = [
            {
                "chat_id": int(item["chat_id"]),
                "message_id": int(item["message_id"]),
                "posted_at": item.get("posted_at"),
                "text": str(item.get("text") or ""),
                "language": None,
                "has_media": bool(item.get("has_media", False)),
                "raw_json": item.get("raw_json") or {},
            }
        ]
        self._stored_messages += await asyncio.to_thread(self.repository.upsert_telegram_messages, message_rows)

        try:
            decisions = await asyncio.to_thread(
                self.matcher.evaluate_message,
                item=item,
                markets=list(item.get("markets") or []),
            )
        except Exception as exc:
            self._ai_failures += 1
            self._log(
                f"realtime_listener_ai_failure chat_id={item.get('chat_id')} "
                f"message_id={item.get('message_id')} error={type(exc).__name__}: {exc}"
            )
            return

        self._evaluated_messages += 1
        matched_lookup = {decision.market_id: decision for decision in decisions}
        if decisions:
            self._matched_messages += 1
            self._matched_pairs += len(decisions)

        match_rows: list[dict[str, Any]] = []
        activation_rows: list[dict[str, Any]] = []
        for market in list(item.get("markets") or []):
            market_id = str(market["market_id"])
            decision = matched_lookup.get(market_id)
            is_match = decision is not None
            raw_json = {
                "mode": "realtime_batch_matcher",
                "channel_rank": market.get("market_rank"),
                "confidence": decision.confidence if decision is not None else None,
                "requested_name": market.get("requested_name"),
                "requested_bucket": market.get("requested_bucket"),
            }
            match_rows.append(
                {
                    "chat_id": int(item["chat_id"]),
                    "message_id": int(item["message_id"]),
                    "market_id": market_id,
                    "is_match": is_match,
                    "matched_outcome_index": None,
                    "match_reason_short": (
                        decision.reason_short
                        if decision is not None
                        else "ai_batch_no_match"
                    ),
                    "matcher_version": self.matcher.matcher_version,
                    "raw_json": raw_json,
                }
            )
            if decision is not None:
                activation_rows.append(
                    {
                        "market_id": market_id,
                        "activation_time": item.get("posted_at") or _utc_now_iso(),
                        "trigger_chat_id": int(item["chat_id"]),
                        "trigger_message_id": int(item["message_id"]),
                        "trigger_match_id": None,
                        "activation_source": "telegram_realtime_match",
                        "notes": decision.reason_short,
                    }
                )

        if match_rows:
            await asyncio.to_thread(self.repository.upsert_message_market_matches, match_rows)
        if activation_rows:
            self._activations_inserted += await asyncio.to_thread(
                self.repository.insert_market_activations_if_absent,
                activation_rows,
            )
