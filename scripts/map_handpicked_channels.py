#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, TypeVar

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.polymarket.config import PolymarketConfig
from src.polymarket.llm_runtime import LLMRuntimeUnavailable, resolve_reasoning_client
from src.polymarket.market_intel_repository import MarketIntelRepository
from src.polymarket.prompt_store import load_prompt_template, render_prompt_template

T = TypeVar("T")


@dataclass(frozen=True)
class MappingDecision:
    chat_id: int
    market_id: str
    candidate_id: str
    confidence: float
    reason_short: str
    channel_title: str
    market_label: str


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch map active Telegram channels to matched handpicked markets.")
    parser.add_argument("--env-file", default=".env", help="Path to runtime env file.")
    parser.add_argument(
        "--source-file",
        default=str((ROOT / "handpicked.txt").resolve()),
        help="Source file path recorded in handpicked_market_targets.",
    )
    parser.add_argument("--channel-limit", type=int, default=140, help="Limit active channels considered.")
    parser.add_argument("--market-limit", type=int, default=120, help="Limit matched handpicked markets considered.")
    parser.add_argument("--batch-size", type=int, default=28, help="Candidate markets per model call.")
    parser.add_argument("--min-confidence", type=float, default=0.72, help="Minimum confidence to write a link.")
    parser.add_argument(
        "--model",
        default="",
        help="Override model. Defaults to AI_TELEGRAM_CHANNEL_RELEVANCE_MODEL or OPENROUTER_MODEL fallback.",
    )
    parser.add_argument(
        "--link-source",
        default="ai_handpicked_batch_v1",
        help="link_source value written into channel_market_map.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write channel_market_map rows.")
    parser.add_argument(
        "--print-limit",
        type=int,
        default=40,
        help="How many accepted decisions to print in the final preview.",
    )
    return parser


def chunked(items: list[T], size: int) -> list[list[T]]:
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[index : index + size] for index in range(0, len(items), size)]


def clean_channel_notes(value: str | None) -> str:
    lines = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("auto_inactive:"):
            continue
        lines.append(line)
    return "\n".join(lines[:6])


def fetch_channels(*, db_url: str, limit: int) -> list[dict[str, Any]]:
    effective_limit = max(1, min(int(limit), 1000))
    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  chat_id,
                  title,
                  username,
                  description,
                  member_count,
                  language_hint,
                  tags_json,
                  notes
                FROM telegram_channels
                WHERE is_active = TRUE
                ORDER BY member_count DESC NULLS LAST, chat_id ASC
                LIMIT %s;
                """,
                (effective_limit,),
            )
            rows = [dict(row) for row in cur.fetchall()]

    normalized = []
    for row in rows:
        normalized.append(
            {
                "chat_id": int(row["chat_id"]),
                "title": str(row.get("title") or ""),
                "username": str(row.get("username") or ""),
                "description": str(row.get("description") or "")[:1200],
                "member_count": int(row.get("member_count") or 0),
                "language_hint": [str(item) for item in list(row.get("language_hint") or []) if str(item).strip()][:6],
                "tags_json": [str(item) for item in list(row.get("tags_json") or []) if str(item).strip()][:10],
                "notes": clean_channel_notes(row.get("notes")),
            }
        )
    return normalized


def fetch_matched_handpicked_markets(*, db_url: str, source_file: str, limit: int) -> list[dict[str, Any]]:
    effective_limit = max(1, min(int(limit), 500))
    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  t.target_id,
                  t.source_line_number,
                  t.requested_name,
                  t.requested_bucket,
                  t.matched_group_slug,
                  t.representative_market_id AS market_id,
                  t.matched_group_title,
                  t.matched_scope_label,
                  t.notes,
                  m.slug,
                  m.question,
                  m.description,
                  mg.sample_questions
                FROM handpicked_market_targets t
                JOIN markets m
                  ON m.market_id = t.representative_market_id
                LEFT JOIN market_groups mg
                  ON mg.group_slug = t.matched_group_slug
                WHERE t.source_file = %s
                  AND t.match_status = 'matched'
                  AND t.representative_market_id IS NOT NULL
                ORDER BY t.source_line_number ASC
                LIMIT %s;
                """,
                (source_file, effective_limit),
            )
            rows = [dict(row) for row in cur.fetchall()]

    normalized = []
    for row in rows:
        sample_questions = row.get("sample_questions") if isinstance(row.get("sample_questions"), list) else []
        normalized.append(
            {
                "target_id": int(row["target_id"]),
                "source_line_number": int(row["source_line_number"]),
                "market_id": str(row["market_id"]),
                "requested_name": str(row.get("requested_name") or ""),
                "requested_bucket": str(row.get("requested_bucket") or ""),
                "group_slug": str(row.get("matched_group_slug") or ""),
                "group_title": str(row.get("matched_group_title") or ""),
                "scope_label": str(row.get("matched_scope_label") or ""),
                "slug": str(row.get("slug") or ""),
                "question": str(row.get("question") or ""),
                "description": str(row.get("description") or "")[:400],
                "sample_questions": [str(item) for item in sample_questions[:3]],
                "notes": str(row.get("notes") or "")[:240],
            }
        )
    return normalized


def mapper_system_prompt() -> str:
    fallback = (
        "You are reviewing Telegram channel relevance for a curated set of Polymarket markets. "
        "Select only markets this channel is likely to consistently cover. Return strict JSON only."
    )
    return load_prompt_template("telegram_channel_mapper/system.txt", fallback)


def mapper_user_prompt(*, channel_payload: dict[str, Any], candidate_payload: list[dict[str, Any]]) -> str:
    fallback = (
        "Review this Telegram channel against the candidate markets below.\n\n"
        "CHANNEL_JSON:\n{{CHANNEL_JSON}}\n\n"
        "CANDIDATE_MARKETS_JSON:\n{{MARKETS_JSON}}"
    )
    template = load_prompt_template("telegram_channel_mapper/user.txt", fallback)
    return render_prompt_template(
        template,
        {
            "CHANNEL_JSON": json.dumps(channel_payload, ensure_ascii=False, indent=2),
            "MARKETS_JSON": json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        },
    )


def channel_mapper_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "confidence": {"type": "number"},
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


def build_channel_payload(channel: dict[str, Any]) -> dict[str, Any]:
    return {
        "chat_id": channel["chat_id"],
        "title": channel["title"],
        "username": channel["username"],
        "description": channel["description"],
        "member_count": channel["member_count"],
        "language_hint": channel["language_hint"],
        "tags": channel["tags_json"],
        "notes": channel["notes"],
    }


def build_candidate_payload(batch: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    payload: list[dict[str, Any]] = []
    lookup: dict[str, dict[str, Any]] = {}
    for index, market in enumerate(batch, start=1):
        candidate_id = f"M{index:02d}"
        lookup[candidate_id] = market
        payload.append(
            {
                "candidate_id": candidate_id,
                "market_id": market["market_id"],
                "requested_name": market["requested_name"],
                "requested_bucket": market["requested_bucket"],
                "scope_label": market["scope_label"],
                "group_title": market["group_title"],
                "question": market["question"],
                "sample_questions": market["sample_questions"],
            }
        )
    return payload, lookup


def map_channel_batches(
    *,
    reasoning_client: Any,
    model: str,
    channel: dict[str, Any],
    markets: list[dict[str, Any]],
    batch_size: int,
    min_confidence: float,
) -> list[MappingDecision]:
    channel_payload = build_channel_payload(channel)
    decisions: list[MappingDecision] = []
    seen_market_ids: set[str] = set()

    for batch in chunked(markets, batch_size):
        candidate_payload, candidate_lookup = build_candidate_payload(batch)
        response = reasoning_client.generate_json(
            model=model,
            system_prompt=mapper_system_prompt(),
            user_prompt=mapper_user_prompt(channel_payload=channel_payload, candidate_payload=candidate_payload),
            schema_name="telegram_channel_mapper",
            schema=channel_mapper_schema(),
        )
        for item in list(response.get("matches") or []):
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidate_id") or "").strip()
            if not candidate_id or candidate_id not in candidate_lookup:
                continue
            confidence = max(0.0, min(float(item.get("confidence") or 0.0), 1.0))
            if confidence < min_confidence:
                continue
            market = candidate_lookup[candidate_id]
            market_id = str(market["market_id"])
            if market_id in seen_market_ids:
                continue
            seen_market_ids.add(market_id)
            decisions.append(
                MappingDecision(
                    chat_id=int(channel["chat_id"]),
                    market_id=market_id,
                    candidate_id=candidate_id,
                    confidence=confidence,
                    reason_short=str(item.get("reason_short") or "").strip()[:240],
                    channel_title=str(channel.get("title") or ""),
                    market_label=str(market.get("requested_name") or market.get("question") or market_id),
                )
            )
    decisions.sort(key=lambda item: (-item.confidence, item.market_id))
    return decisions


def persist_links(
    *,
    repository: MarketIntelRepository,
    decisions_by_channel: dict[int, list[MappingDecision]],
    link_source: str,
) -> int:
    links: list[dict[str, Any]] = []
    for chat_id, items in decisions_by_channel.items():
        ranked = sorted(items, key=lambda item: (-item.confidence, item.market_id))
        for rank, item in enumerate(ranked, start=1):
            links.append(
                {
                    "chat_id": int(chat_id),
                    "market_id": item.market_id,
                    "link_source": link_source,
                    "priority_rank": rank,
                    "notes": f"ai_channel_mapper confidence={item.confidence:.3f}; {item.reason_short}",
                }
            )
    return repository.upsert_channel_market_links(links)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    load_env_file(Path(args.env_file))
    config = PolymarketConfig.from_env()
    db_url = config.direct_url or config.database_url
    if not db_url:
        raise RuntimeError("No database URL configured.")

    try:
        reasoning_client = resolve_reasoning_client(config, required=True)
    except LLMRuntimeUnavailable as exc:
        raise RuntimeError(f"AI runtime is unavailable: {exc}") from exc

    model = str(args.model or config.ai_telegram_channel_relevance_model or "").strip()
    if not model:
        raise RuntimeError("No model configured. Set AI_TELEGRAM_CHANNEL_RELEVANCE_MODEL or OPENROUTER_MODEL.")

    channels = fetch_channels(db_url=db_url, limit=args.channel_limit)
    markets = fetch_matched_handpicked_markets(
        db_url=db_url,
        source_file=str(Path(args.source_file).resolve()),
        limit=args.market_limit,
    )
    if not channels:
        raise RuntimeError("No active telegram channels found.")
    if not markets:
        raise RuntimeError("No matched handpicked markets found for the requested source file.")

    decisions_by_channel: dict[int, list[MappingDecision]] = {}
    total_batches = len(channels) * math.ceil(len(markets) / max(1, int(args.batch_size)))
    completed_batches = 0
    channels_with_matches = 0
    stored_links = 0
    repository = MarketIntelRepository(db_url) if not args.dry_run else None

    for channel_index, channel in enumerate(channels, start=1):
        decisions = map_channel_batches(
            reasoning_client=reasoning_client,
            model=model,
            channel=channel,
            markets=markets,
            batch_size=max(1, min(int(args.batch_size), 60)),
            min_confidence=max(0.0, min(float(args.min_confidence), 1.0)),
        )
        completed_batches += math.ceil(len(markets) / max(1, int(args.batch_size)))
        if decisions:
            channels_with_matches += 1
            decisions_by_channel[int(channel["chat_id"])] = decisions
            if repository is not None:
                stored_links += persist_links(
                    repository=repository,
                    decisions_by_channel={int(channel["chat_id"]): decisions},
                    link_source=str(args.link_source or "ai_handpicked_batch_v1"),
                )
        print(
            f"[{channel_index}/{len(channels)}] chat_id={channel['chat_id']} "
            f"title={channel['title'][:48]!r} matches={len(decisions)} "
            f"progress_batches={completed_batches}/{total_batches}"
        )

    all_decisions = [item for items in decisions_by_channel.values() for item in items]
    preview = [
        {
            "chat_id": item.chat_id,
            "channel_title": item.channel_title,
            "market_id": item.market_id,
            "market_label": item.market_label,
            "confidence": round(item.confidence, 4),
            "reason_short": item.reason_short,
        }
        for item in sorted(all_decisions, key=lambda item: (-item.confidence, item.chat_id, item.market_id))[
            : max(1, int(args.print_limit))
        ]
    ]
    summary = {
        "provider": getattr(reasoning_client, "provider_name", "unknown"),
        "model": model,
        "source_file": str(Path(args.source_file).resolve()),
        "channels_considered": len(channels),
        "markets_considered": len(markets),
        "batch_size": max(1, min(int(args.batch_size), 60)),
        "min_confidence": max(0.0, min(float(args.min_confidence), 1.0)),
        "channels_with_matches": channels_with_matches,
        "accepted_links": len(all_decisions),
        "stored_links": stored_links,
        "dry_run": bool(args.dry_run),
        "preview": preview,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
