#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_SOURCE_URLS = [
    "https://polymarket.com/geopolitics",
    "https://polymarket.com/predictions/israel",
    "https://polymarket.com/search?_q=iran",
]
EVENT_SLUG_RE = re.compile(r"/event/([a-z0-9-]+)", re.IGNORECASE)


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
    parser = argparse.ArgumentParser(description="Build grouped market tables from scoped Polymarket event pages.")
    parser.add_argument("--env-file", default=".env", help="Path to runtime env file.")
    parser.add_argument(
        "--source-url",
        action="append",
        default=[],
        help="Polymarket page URL to scrape event slugs from (repeatable). Defaults to geopolitics/israel/iran.",
    )
    parser.add_argument(
        "--max-slugs-per-source",
        type=int,
        default=250,
        help="Cap extracted event slugs per source URL.",
    )
    parser.add_argument(
        "--source-timeout-seconds",
        type=int,
        default=25,
        help="HTTP timeout when downloading source pages.",
    )
    parser.add_argument(
        "--apply-migration",
        action="store_true",
        help="Apply sql/002_grouped_markets.sql before rebuilding.",
    )
    return parser


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _fetch_text(url: str, *, timeout_seconds: int) -> str:
    request = Request(
        url=url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; grouped-market-rebuilder/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="ignore")


def _extract_direct_event_slug(source_url: str) -> str | None:
    parsed = urlparse(str(source_url or "").strip())
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].lower() != "event":
        return None
    slug = parts[1].strip().lower()
    if re.fullmatch(r"[a-z0-9-]+", slug):
        return slug
    return None


def extract_event_slugs_from_source(source_url: str, *, max_slugs: int, timeout_seconds: int) -> list[str]:
    direct_slug = _extract_direct_event_slug(source_url)
    if direct_slug:
        return [direct_slug]
    html = _fetch_text(source_url, timeout_seconds=timeout_seconds)
    return _dedupe_preserve([item.lower().strip() for item in EVENT_SLUG_RE.findall(html)])[: max(1, min(max_slugs, 500))]


def market_scope_label(*parts: str) -> str:
    haystack = " ".join(str(part or "") for part in parts).lower()
    if any(token in haystack for token in ("israel", "idf", "hamas", "gaza", "lebanon", "jerusalem")):
        if "iran" in haystack:
            return "Israel / Iran"
        if "gaza" in haystack or "hamas" in haystack:
            return "Gaza / Israel"
        return "Israel"
    if any(token in haystack for token in ("iran", "khamenei", "pahlavi", "tehran", "hormuz")):
        return "Iran"
    if any(token in haystack for token in ("ukraine", "russia", "zelensky", "putin")):
        return "Ukraine"
    if any(token in haystack for token in ("venezuela", "maduro", "caracas")):
        return "Venezuela"
    if any(token in haystack for token in ("oil", "crude", "shipping", "ship", "hormuz")):
        return "Oil"
    return "Other"


def is_tradable_market(row: dict[str, Any]) -> bool:
    return bool(
        row.get("active") is True
        and row.get("closed") is False
        and not bool(row.get("archived"))
        and bool(row.get("accepting_orders"))
        and bool(row.get("enable_order_book"))
    )


def humanize_group_slug(group_slug: str) -> str:
    words = re.sub(r"[-_]+", " ", str(group_slug or "").strip()).strip()
    if not words:
        return "Unknown Group"
    return re.sub(r"\b([a-z])", lambda match: match.group(1).upper(), words)


def apply_migration(conn: psycopg.Connection[Any]) -> None:
    migration_path = ROOT / "sql" / "002_grouped_markets.sql"
    sql = migration_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def choose_representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def to_timestamp(value: Any, *, fallback: float) -> float:
        if isinstance(value, datetime):
            return value.timestamp()
        return fallback

    def sort_key(row: dict[str, Any]) -> tuple[int, float, float]:
        end_date = row.get("end_date")
        last_seen_at = row.get("last_seen_at")
        end_rank = 0 if isinstance(end_date, datetime) else 1
        return (
            end_rank,
            to_timestamp(end_date, fallback=float("inf")),
            -to_timestamp(last_seen_at, fallback=0.0),
        )

    return sorted(rows, key=sort_key)[0]


def rebuild_grouped_tables(
    *,
    db_url: str,
    source_urls: list[str],
    max_slugs_per_source: int,
    source_timeout_seconds: int,
) -> dict[str, Any]:
    unique_urls = _dedupe_preserve(source_urls or list(DEFAULT_SOURCE_URLS))
    slug_sources: dict[str, list[str]] = defaultdict(list)
    source_slug_counts: dict[str, int] = {}
    event_slugs: list[str] = []
    for source_url in unique_urls:
        source_slugs = extract_event_slugs_from_source(
            source_url,
            max_slugs=max_slugs_per_source,
            timeout_seconds=source_timeout_seconds,
        )
        source_slug_counts[source_url] = len(source_slugs)
        for event_slug in source_slugs:
            slug_sources[event_slug].append(source_url)
        event_slugs.extend(source_slugs)
    event_slugs = _dedupe_preserve(event_slugs)
    if not event_slugs:
        raise RuntimeError("No scoped event slugs were extracted from the provided source URLs.")

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  m.market_id,
                  m.event_id,
                  m.event_slug,
                  m.slug,
                  m.question,
                  m.description,
                  m.market_context,
                  m.market_archetype,
                  m.active,
                  m.closed,
                  COALESCE(m.archived, FALSE) AS archived,
                  COALESCE(m.accepting_orders, FALSE) AS accepting_orders,
                  COALESCE(m.enable_order_book, FALSE) AS enable_order_book,
                  m.end_date,
                  m.last_seen_at
                FROM markets m
                WHERE m.event_slug = ANY(%s)
                ORDER BY m.event_slug, m.end_date ASC NULLS LAST, m.last_seen_at DESC;
                """,
                (event_slugs,),
            )
            market_rows = [dict(row) for row in cur.fetchall()]

        grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in market_rows:
            grouped_rows[str(row.get("event_slug") or "")].append(row)

        group_records: list[dict[str, Any]] = []
        member_records: list[dict[str, Any]] = []

        for group_slug in sorted(grouped_rows):
            rows = grouped_rows[group_slug]
            tradable_rows = [row for row in rows if is_tradable_market(row)]
            if not tradable_rows:
                continue
            representative = choose_representative(tradable_rows)
            scope_label = market_scope_label(
                group_slug,
                representative.get("slug"),
                representative.get("question"),
                representative.get("description"),
                representative.get("market_context"),
            )
            source_list = _dedupe_preserve(list(slug_sources.get(group_slug, [])))
            sample_questions = _dedupe_preserve([str(row.get("question") or "").strip() for row in tradable_rows if row.get("question")])[:5]
            market_ids = [str(row["market_id"]) for row in tradable_rows]
            market_slugs = [str(row.get("slug") or "") for row in tradable_rows if row.get("slug")]
            group_records.append(
                {
                    "group_slug": group_slug,
                    "event_id": representative.get("event_id"),
                    "scope_label": scope_label,
                    "group_title": humanize_group_slug(group_slug),
                    "representative_market_id": representative["market_id"],
                    "market_count": len(rows),
                    "tradable_market_count": len(tradable_rows),
                    "earliest_end_date": min((row.get("end_date") for row in tradable_rows if row.get("end_date")), default=None),
                    "latest_end_date": max((row.get("end_date") for row in tradable_rows if row.get("end_date")), default=None),
                    "last_seen_at": max((row.get("last_seen_at") for row in tradable_rows if row.get("last_seen_at")), default=None),
                    "source_urls": Jsonb(source_list),
                    "sample_questions": Jsonb(sample_questions),
                    "raw_json": Jsonb(
                        {
                            "market_ids": market_ids,
                            "market_slugs": market_slugs,
                            "source_urls": source_list,
                            "scoped_event_slug": group_slug,
                        }
                    ),
                }
            )
            for rank, row in enumerate(tradable_rows, start=1):
                member_records.append(
                    {
                        "group_slug": group_slug,
                        "market_id": row["market_id"],
                        "event_slug": group_slug,
                        "is_tradable": True,
                        "priority_rank": rank,
                        "source_urls": Jsonb(source_list),
                    }
                )

        with conn.cursor() as cur:
            cur.execute("TRUNCATE market_group_members, market_groups;")
            if group_records:
                cur.executemany(
                    """
                    INSERT INTO market_groups (
                      group_slug, event_id, scope_label, group_title, representative_market_id,
                      market_count, tradable_market_count, earliest_end_date, latest_end_date,
                      last_seen_at, source_urls, sample_questions, raw_json, generated_at, updated_at
                    ) VALUES (
                      %(group_slug)s, %(event_id)s, %(scope_label)s, %(group_title)s, %(representative_market_id)s,
                      %(market_count)s, %(tradable_market_count)s, %(earliest_end_date)s, %(latest_end_date)s,
                      %(last_seen_at)s, %(source_urls)s, %(sample_questions)s, %(raw_json)s, NOW(), NOW()
                    );
                    """,
                    group_records,
                )
            if member_records:
                cur.executemany(
                    """
                    INSERT INTO market_group_members (
                      group_slug, market_id, event_slug, is_tradable, priority_rank, source_urls, created_at
                    ) VALUES (
                      %(group_slug)s, %(market_id)s, %(event_slug)s, %(is_tradable)s, %(priority_rank)s, %(source_urls)s, NOW()
                    );
                    """,
                    member_records,
                )
        conn.commit()

    scope_counts: dict[str, int] = defaultdict(int)
    for group in group_records:
        scope_counts[str(group["scope_label"])] += 1

    return {
        "source_urls": unique_urls,
        "source_slug_counts": source_slug_counts,
        "scoped_event_slugs": len(event_slugs),
        "group_count": len(group_records),
        "member_count": len(member_records),
        "scope_counts": dict(sorted(scope_counts.items(), key=lambda item: (-item[1], item[0]))),
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    load_env_file(Path(args.env_file))
    db_url = os.environ.get("SUPABASE_DIRECT_DB_URL") or os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("No database URL configured. Set SUPABASE_DIRECT_DB_URL or SUPABASE_DB_URL in the env file.")

    source_urls = _dedupe_preserve(list(args.source_url or [])) or list(DEFAULT_SOURCE_URLS)

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        if args.apply_migration:
            apply_migration(conn)

    result = rebuild_grouped_tables(
        db_url=db_url,
        source_urls=source_urls,
        max_slugs_per_source=max(1, min(int(args.max_slugs_per_source), 500)),
        source_timeout_seconds=max(5, min(int(args.source_timeout_seconds), 120)),
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
