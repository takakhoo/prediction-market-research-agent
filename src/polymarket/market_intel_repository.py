from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
import json

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class MarketBundle:
    market: dict[str, Any]
    outcomes: list[dict[str, Any]]
    snapshot: dict[str, Any]


class MarketIntelRepository:
    """Postgres repository for market intelligence tables."""

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    def upsert_market_bundles(
        self,
        bundles: Iterable[MarketBundle],
        *,
        store_outcomes: bool = True,
        store_snapshots: bool = True,
    ) -> int:
        items = list(bundles)
        if not items:
            return 0

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                for bundle in items:
                    self._upsert_market(cur, bundle.market)
                    if store_outcomes:
                        self._replace_market_outcomes(cur, bundle.market["market_id"], bundle.outcomes)
                    if store_snapshots:
                        self._insert_snapshot(cur, bundle.snapshot)
            conn.commit()
        return len(items)

    def count_public_tables(self) -> int:
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM pg_catalog.pg_tables
                    WHERE schemaname = 'public';
                    """
                )
                return int(cur.fetchone()[0])

    def get_pending_market_analysis_rows(self, *, limit: int = 100) -> list[dict[str, Any]]:
        effective_limit = max(1, min(int(limit), 1000))
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                      m.*,
                      latest.rules_hash AS latest_rules_hash,
                      COALESCE(
                        json_agg(
                          json_build_object(
                            'outcome_index', mo.outcome_index,
                            'outcome_label', mo.outcome_label,
                            'token_id', mo.token_id,
                            'price', mo.price,
                            'probability', mo.probability,
                            'is_likely', mo.is_likely,
                            'is_unlikely', mo.is_unlikely,
                            'raw_json', mo.raw_json
                          )
                          ORDER BY mo.outcome_index
                        ) FILTER (WHERE mo.market_id IS NOT NULL),
                        '[]'::json
                      ) AS outcomes
                    FROM markets m
                    LEFT JOIN market_outcomes mo ON mo.market_id = m.market_id
                    LEFT JOIN LATERAL (
                      SELECT rules_hash
                      FROM market_analysis ma
                      WHERE ma.market_id = m.market_id
                      ORDER BY ma.analyzed_at DESC
                      LIMIT 1
                    ) latest ON TRUE
                    WHERE m.active = TRUE
                      AND m.closed = FALSE
                      AND (
                        latest.rules_hash IS NULL
                        OR latest.rules_hash IS DISTINCT FROM m.rules_hash
                      )
                    GROUP BY m.market_id, latest.rules_hash
                    ORDER BY m.last_seen_at DESC
                    LIMIT %s;
                    """,
                    (effective_limit,),
                )
                return list(cur.fetchall())

    def save_market_analysis_results(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        keep_history: bool = True,
    ) -> int:
        items = list(rows)
        if not items:
            return 0

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                if not keep_history:
                    market_ids = sorted({str(item["market_id"]) for item in items if item.get("market_id")})
                    if market_ids:
                        cur.execute(
                            "DELETE FROM market_analysis WHERE market_id = ANY(%s);",
                            (market_ids,),
                        )

                cur.executemany(
                    """
                    INSERT INTO market_analysis (
                      market_id, analyzed_at, analysis_version, prompt_version, rules_hash, is_local,
                      local_score, classification, reason_json, status
                    ) VALUES (
                      %(market_id)s, NOW(), %(analysis_version)s, %(prompt_version)s, %(rules_hash)s, %(is_local)s,
                      %(local_score)s, %(classification)s, %(reason_json)s, %(status)s
                    );
                    """,
                    [
                        {
                            **item,
                            "reason_json": Jsonb(item.get("reason_json") or {}),
                        }
                        for item in items
                    ],
                )

                cur.executemany(
                    """
                    UPDATE markets
                    SET
                      is_local_candidate = %(is_local)s,
                      local_score = %(local_score)s,
                      local_reason_json = %(reason_json)s,
                      updated_at = NOW()
                    WHERE market_id = %(market_id)s;
                    """,
                    [
                        {
                            "market_id": item["market_id"],
                            "is_local": item["is_local"],
                            "local_score": item.get("local_score"),
                            "reason_json": Jsonb(item.get("reason_json") or {}),
                        }
                        for item in items
                    ],
                )
            conn.commit()
        return len(items)

    def get_track_now_markets(self, *, limit: int = 100) -> list[dict[str, Any]]:
        effective_limit = max(1, min(int(limit), 1000))
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH latest_analysis AS (
                      SELECT DISTINCT ON (ma.market_id)
                        ma.market_id,
                        ma.classification,
                        ma.reason_json,
                        ma.analyzed_at
                      FROM market_analysis ma
                      WHERE ma.status = 'active'
                      ORDER BY ma.market_id, ma.analyzed_at DESC
                    )
                    SELECT
                      m.market_id,
                      m.slug,
                      m.question,
                      m.description,
                      m.rules_text,
                      m.market_context,
                      m.market_archetype,
                      m.local_score,
                      m.high_competition,
                      m.last_seen_at,
                      latest_analysis.reason_json AS analysis_reason_json,
                      COALESCE(
                        COUNT(cmm.chat_id) FILTER (WHERE cmm.link_status = 'active'),
                        0
                      )::INT AS mapped_channels
                    FROM markets m
                    JOIN latest_analysis ON latest_analysis.market_id = m.market_id
                    LEFT JOIN channel_market_map cmm
                      ON cmm.market_id = m.market_id
                     AND cmm.link_status = 'active'
                    WHERE m.active = TRUE
                      AND m.closed = FALSE
                      AND latest_analysis.classification = 'track_now'
                    GROUP BY
                      m.market_id, m.slug, m.question, m.description, m.rules_text, m.market_context,
                      m.market_archetype, m.local_score, m.high_competition, m.last_seen_at,
                      latest_analysis.reason_json
                    ORDER BY m.local_score DESC NULLS LAST, m.last_seen_at DESC
                    LIMIT %s;
                    """,
                    (effective_limit,),
                )
                return list(cur.fetchall())

    def get_market_by_ref(self, market_ref: str) -> dict[str, Any] | None:
        ref = str(market_ref or "").strip()
        if not ref:
            return None

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH latest_analysis AS (
                      SELECT DISTINCT ON (ma.market_id)
                        ma.market_id,
                        ma.classification,
                        ma.reason_json,
                        ma.local_score AS analysis_local_score,
                        ma.analyzed_at
                      FROM market_analysis ma
                      WHERE ma.status = 'active'
                      ORDER BY ma.market_id, ma.analyzed_at DESC
                    )
                    SELECT
                      m.market_id,
                      m.slug,
                      m.question,
                      m.description,
                      m.rules_text,
                      m.market_context,
                      m.market_archetype,
                      m.local_score,
                      m.high_competition,
                      m.last_seen_at,
                      COALESCE(latest_analysis.classification, 'unclassified') AS classification,
                      latest_analysis.reason_json AS analysis_reason_json,
                      COALESCE(latest_analysis.analysis_local_score, m.local_score) AS analysis_local_score,
                      COALESCE(
                        COUNT(cmm.chat_id) FILTER (WHERE cmm.link_status = 'active'),
                        0
                      )::INT AS mapped_channels
                    FROM markets m
                    LEFT JOIN latest_analysis ON latest_analysis.market_id = m.market_id
                    LEFT JOIN channel_market_map cmm
                      ON cmm.market_id = m.market_id
                     AND cmm.link_status = 'active'
                    WHERE m.active = TRUE
                      AND m.closed = FALSE
                      AND (
                        m.market_id = %s
                        OR m.slug = %s
                      )
                    GROUP BY
                      m.market_id, m.slug, m.question, m.description, m.rules_text, m.market_context,
                      m.market_archetype, m.local_score, m.high_competition, m.last_seen_at,
                      latest_analysis.classification, latest_analysis.reason_json, latest_analysis.analysis_local_score
                    ORDER BY
                      CASE WHEN m.market_id = %s THEN 0 ELSE 1 END,
                      COALESCE(latest_analysis.analysis_local_score, m.local_score) DESC NULLS LAST,
                      m.last_seen_at DESC
                    LIMIT 1;
                    """,
                    (ref, ref, ref),
                )
                return cur.fetchone()

    def upsert_telegram_channels(self, channels: Iterable[dict[str, Any]], *, source: str) -> int:
        items = list(channels)
        if not items:
            return 0

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO telegram_channels (
                      chat_id, title, username, description, member_count, language_hint,
                      is_public, is_active, trust_weight, tags_json, notes, first_seen_at, last_seen_at, raw_json
                    ) VALUES (
                      %(chat_id)s, %(title)s, %(username)s, %(description)s, %(member_count)s, %(language_hint)s,
                      TRUE, TRUE, %(trust_weight)s, %(tags_json)s, %(notes)s, NOW(), NOW(), %(raw_json)s
                    )
                    ON CONFLICT (chat_id) DO UPDATE SET
                      title = EXCLUDED.title,
                      username = EXCLUDED.username,
                      description = EXCLUDED.description,
                      member_count = EXCLUDED.member_count,
                      language_hint = EXCLUDED.language_hint,
                      is_active = TRUE,
                      last_seen_at = NOW(),
                      raw_json = EXCLUDED.raw_json;
                    """,
                    [
                        {
                            "chat_id": int(item["chat_id"]),
                            "title": str(item.get("title") or "").strip() or str(item["chat_id"]),
                            "username": _optional_text(item.get("username")),
                            "description": _optional_text(item.get("description")),
                            "member_count": _safe_int(item.get("member_count")),
                            "language_hint": list(item.get("language_hint") or []),
                            "trust_weight": float(item.get("trust_weight", 0.5)),
                            "tags_json": Jsonb(item.get("tags_json") or []),
                            "notes": _note_with_source(item.get("notes"), source=source),
                            "raw_json": Jsonb(item.get("raw_json") or item),
                        }
                        for item in items
                    ],
                )
            conn.commit()
        return len(items)

    def upsert_channel_market_links(self, links: Iterable[dict[str, Any]]) -> int:
        items = list(links)
        if not items:
            return 0

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO channel_market_map (
                      chat_id, market_id, link_source, link_status, priority_rank, notes, created_at, updated_at
                    ) VALUES (
                      %(chat_id)s, %(market_id)s, %(link_source)s, 'active', %(priority_rank)s, %(notes)s, NOW(), NOW()
                    )
                    ON CONFLICT (chat_id, market_id) DO UPDATE SET
                      link_status = 'active',
                      link_source = CASE
                        WHEN channel_market_map.link_source = 'manual' THEN channel_market_map.link_source
                        ELSE EXCLUDED.link_source
                      END,
                      priority_rank = COALESCE(channel_market_map.priority_rank, EXCLUDED.priority_rank),
                      notes = CASE
                        WHEN COALESCE(channel_market_map.notes, '') <> '' THEN channel_market_map.notes
                        ELSE EXCLUDED.notes
                      END,
                      updated_at = NOW();
                    """,
                    [
                        {
                            "chat_id": int(item["chat_id"]),
                            "market_id": str(item["market_id"]),
                            "link_source": str(item.get("link_source") or "auto"),
                            "priority_rank": _safe_int(item.get("priority_rank")),
                            "notes": str(item.get("notes") or ""),
                        }
                        for item in items
                    ],
                )
            conn.commit()
        return len(items)

    def mark_channels_inactive(self, chat_ids: Iterable[int], *, reason: str) -> int:
        unique_chat_ids = sorted({int(chat_id) for chat_id in chat_ids})
        if not unique_chat_ids:
            return 0

        reason_text = str(reason or "inactive").strip() or "inactive"
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE telegram_channels
                    SET
                      is_active = FALSE,
                      notes = CASE
                        WHEN COALESCE(notes, '') = '' THEN %s
                        ELSE notes || E'\n' || %s
                      END,
                      last_seen_at = NOW()
                    WHERE chat_id = ANY(%s)
                      AND is_active = TRUE;
                    """,
                    (f"auto_inactive:{reason_text}", f"auto_inactive:{reason_text}", unique_chat_ids),
                )
                affected_channels = int(cur.rowcount or 0)

                cur.execute(
                    """
                    UPDATE channel_market_map
                    SET
                      link_status = 'inactive',
                      notes = CASE
                        WHEN COALESCE(notes, '') = '' THEN %s
                        ELSE notes || E'\n' || %s
                      END,
                      updated_at = NOW()
                    WHERE chat_id = ANY(%s)
                      AND link_status = 'active';
                    """,
                    (f"auto_inactive:{reason_text}", f"auto_inactive:{reason_text}", unique_chat_ids),
                )
            conn.commit()
        return affected_channels

    def get_active_channel_market_bindings(
        self,
        *,
        channel_limit: int = 500,
        markets_per_channel: int = 25,
    ) -> list[dict[str, Any]]:
        effective_channel_limit = max(1, min(int(channel_limit), 5000))
        effective_markets_per_channel = max(1, min(int(markets_per_channel), 200))

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH latest_analysis AS (
                      SELECT DISTINCT ON (ma.market_id)
                        ma.market_id,
                        ma.classification,
                        ma.analyzed_at
                      FROM market_analysis ma
                      WHERE ma.status = 'active'
                      ORDER BY ma.market_id, ma.analyzed_at DESC
                    ),
                    selected_channels AS (
                      SELECT cmm.chat_id
                      FROM channel_market_map cmm
                      JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                      JOIN markets m ON m.market_id = cmm.market_id
                      JOIN latest_analysis la ON la.market_id = m.market_id
                      WHERE cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                        AND m.active = TRUE
                        AND m.closed = FALSE
                        AND la.classification = 'track_now'
                      GROUP BY cmm.chat_id
                      ORDER BY MAX(cmm.updated_at) DESC
                      LIMIT %s
                    ),
                    ranked AS (
                      SELECT
                        cmm.chat_id,
                        tc.title AS channel_title,
                        tc.username AS channel_username,
                        tc.trust_weight,
                        cmm.market_id,
                        cmm.link_source,
                        cmm.priority_rank,
                        m.question,
                        m.rules_text,
                        m.market_context,
                        m.market_archetype,
                        m.local_score,
                        ROW_NUMBER() OVER (
                          PARTITION BY cmm.chat_id
                          ORDER BY
                            COALESCE(cmm.priority_rank, 2147483647),
                            m.local_score DESC NULLS LAST,
                            m.last_seen_at DESC
                        ) AS market_rank
                      FROM channel_market_map cmm
                      JOIN selected_channels sc ON sc.chat_id = cmm.chat_id
                      JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                      JOIN markets m ON m.market_id = cmm.market_id
                      JOIN latest_analysis la ON la.market_id = m.market_id
                      WHERE cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                        AND m.active = TRUE
                        AND m.closed = FALSE
                        AND la.classification = 'track_now'
                    )
                    SELECT
                      chat_id,
                      channel_title,
                      channel_username,
                      trust_weight,
                      market_id,
                      link_source,
                      priority_rank,
                      question,
                      rules_text,
                      market_context,
                      market_archetype,
                      local_score,
                      market_rank
                    FROM ranked
                    WHERE market_rank <= %s
                    ORDER BY chat_id, market_rank;
                    """,
                    (effective_channel_limit, effective_markets_per_channel),
                )
                return list(cur.fetchall())

    def get_saved_channel_market_bindings(
        self,
        *,
        channel_limit: int = 500,
        markets_per_channel: int = 25,
        link_source: str = "ai_handpicked_batch_v1",
        source_file: str | None = None,
    ) -> list[dict[str, Any]]:
        effective_channel_limit = max(1, min(int(channel_limit), 5000))
        effective_markets_per_channel = max(1, min(int(markets_per_channel), 200))
        normalized_link_source = str(link_source or "").strip()
        link_filter_all = normalized_link_source.lower() in {"", "all", "*"}
        source_filter = str(source_file or "").strip()

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH approved_markets AS (
                      SELECT DISTINCT ON (t.representative_market_id)
                        t.representative_market_id AS market_id,
                        t.source_file,
                        t.source_line_number,
                        t.requested_name,
                        t.requested_bucket,
                        t.matched_group_slug,
                        t.matched_group_title,
                        t.matched_scope_label
                      FROM handpicked_market_targets t
                      WHERE t.match_status = 'matched'
                        AND t.representative_market_id IS NOT NULL
                        AND (%s = '' OR t.source_file = %s)
                      ORDER BY t.representative_market_id ASC, t.source_line_number ASC
                    ),
                    selected_channels AS (
                      SELECT
                        cmm.chat_id,
                        MAX(cmm.updated_at) AS latest_link_at
                      FROM channel_market_map cmm
                      JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                      JOIN markets m ON m.market_id = cmm.market_id
                      JOIN approved_markets am ON am.market_id = cmm.market_id
                      WHERE cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                        AND m.active = TRUE
                        AND m.closed = FALSE
                        AND (%s = TRUE OR cmm.link_source = %s)
                      GROUP BY cmm.chat_id
                      ORDER BY latest_link_at DESC, cmm.chat_id ASC
                      LIMIT %s
                    ),
                    ranked AS (
                      SELECT
                        cmm.chat_id,
                        tc.title AS channel_title,
                        tc.username AS channel_username,
                        tc.trust_weight,
                        cmm.market_id,
                        cmm.link_source,
                        cmm.priority_rank,
                        m.question,
                        m.rules_text,
                        m.market_context,
                        m.market_archetype,
                        m.local_score,
                        am.source_file,
                        am.source_line_number,
                        am.requested_name,
                        am.requested_bucket,
                        am.matched_group_slug,
                        am.matched_group_title,
                        am.matched_scope_label,
                        ROW_NUMBER() OVER (
                          PARTITION BY cmm.chat_id
                          ORDER BY
                            COALESCE(cmm.priority_rank, 2147483647),
                            am.source_line_number ASC,
                            m.last_seen_at DESC
                        ) AS market_rank
                      FROM channel_market_map cmm
                      JOIN selected_channels sc ON sc.chat_id = cmm.chat_id
                      JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                      JOIN markets m ON m.market_id = cmm.market_id
                      JOIN approved_markets am ON am.market_id = cmm.market_id
                      WHERE cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                        AND m.active = TRUE
                        AND m.closed = FALSE
                        AND (%s = TRUE OR cmm.link_source = %s)
                    )
                    SELECT
                      chat_id,
                      channel_title,
                      channel_username,
                      trust_weight,
                      market_id,
                      link_source,
                      priority_rank,
                      question,
                      rules_text,
                      market_context,
                      market_archetype,
                      local_score,
                      source_file,
                      source_line_number,
                      requested_name,
                      requested_bucket,
                      matched_group_slug,
                      matched_group_title,
                      matched_scope_label,
                      market_rank
                    FROM ranked
                    WHERE market_rank <= %s
                    ORDER BY chat_id, market_rank;
                    """,
                    (
                        source_filter,
                        source_filter,
                        link_filter_all,
                        normalized_link_source,
                        effective_channel_limit,
                        link_filter_all,
                        normalized_link_source,
                        effective_markets_per_channel,
                    ),
                )
                return list(cur.fetchall())

    def get_channel_last_message_ids(self, chat_ids: Iterable[int]) -> dict[int, int]:
        unique_chat_ids = sorted({int(chat_id) for chat_id in chat_ids})
        if not unique_chat_ids:
            return {}

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT chat_id, COALESCE(MAX(message_id), 0)::BIGINT AS max_message_id
                    FROM telegram_messages
                    WHERE chat_id = ANY(%s)
                    GROUP BY chat_id;
                    """,
                    (unique_chat_ids,),
                )
                rows = list(cur.fetchall())
        return {int(row["chat_id"]): int(row["max_message_id"]) for row in rows}

    def upsert_telegram_messages(self, rows: Iterable[dict[str, Any]]) -> int:
        items = list(rows)
        if not items:
            return 0

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO telegram_messages (
                      chat_id, message_id, posted_at, ingested_at, text, language, has_media, raw_json
                    ) VALUES (
                      %(chat_id)s, %(message_id)s, %(posted_at)s, NOW(), %(text)s, %(language)s, %(has_media)s, %(raw_json)s
                    )
                    ON CONFLICT (chat_id, message_id) DO UPDATE SET
                      posted_at = EXCLUDED.posted_at,
                      text = EXCLUDED.text,
                      language = EXCLUDED.language,
                      has_media = EXCLUDED.has_media,
                      raw_json = EXCLUDED.raw_json;
                    """,
                    [
                        {
                            "chat_id": int(item["chat_id"]),
                            "message_id": int(item["message_id"]),
                            "posted_at": item.get("posted_at"),
                            "text": str(item.get("text") or ""),
                            "language": _optional_text(item.get("language")),
                            "has_media": bool(item.get("has_media", False)),
                            "raw_json": Jsonb(item.get("raw_json") or item),
                        }
                        for item in items
                    ],
                )
            conn.commit()
        return len(items)

    def upsert_message_market_matches(self, rows: Iterable[dict[str, Any]]) -> int:
        items = list(rows)
        if not items:
            return 0

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO message_market_matches (
                      chat_id, message_id, market_id, evaluated_at, is_match, matched_outcome_index,
                      match_reason_short, matcher_version, raw_json
                    ) VALUES (
                      %(chat_id)s, %(message_id)s, %(market_id)s, NOW(), %(is_match)s, %(matched_outcome_index)s,
                      %(match_reason_short)s, %(matcher_version)s, %(raw_json)s
                    )
                    ON CONFLICT (chat_id, message_id, market_id) DO UPDATE SET
                      evaluated_at = NOW(),
                      is_match = EXCLUDED.is_match,
                      matched_outcome_index = EXCLUDED.matched_outcome_index,
                      match_reason_short = EXCLUDED.match_reason_short,
                      matcher_version = EXCLUDED.matcher_version,
                      raw_json = EXCLUDED.raw_json;
                    """,
                    [
                        {
                            "chat_id": int(item["chat_id"]),
                            "message_id": int(item["message_id"]),
                            "market_id": str(item["market_id"]),
                            "is_match": bool(item.get("is_match", False)),
                            "matched_outcome_index": _safe_int(item.get("matched_outcome_index")),
                            "match_reason_short": _optional_text(item.get("match_reason_short")),
                            "matcher_version": str(item.get("matcher_version") or "v1"),
                            "raw_json": Jsonb(item.get("raw_json") or {}),
                        }
                        for item in items
                    ],
                )
            conn.commit()
        return len(items)

    def insert_market_activations_if_absent(self, rows: Iterable[dict[str, Any]]) -> int:
        items = list(rows)
        if not items:
            return 0

        inserted = 0
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                for item in items:
                    cur.execute(
                        """
                        INSERT INTO market_activations (
                          market_id, activation_time, trigger_chat_id, trigger_message_id, trigger_match_id,
                          activation_source, notes
                        ) VALUES (
                          %(market_id)s, %(activation_time)s, %(trigger_chat_id)s, %(trigger_message_id)s, %(trigger_match_id)s,
                          %(activation_source)s, %(notes)s
                        )
                        ON CONFLICT (market_id) DO NOTHING;
                        """,
                        {
                            "market_id": str(item["market_id"]),
                            "activation_time": item.get("activation_time"),
                            "trigger_chat_id": int(item["trigger_chat_id"]),
                            "trigger_message_id": int(item["trigger_message_id"]),
                            "trigger_match_id": _safe_int(item.get("trigger_match_id")),
                            "activation_source": str(item.get("activation_source") or "telegram_match"),
                            "notes": str(item.get("notes") or ""),
                        },
                    )
                    inserted += int(cur.rowcount or 0)
            conn.commit()
        return inserted

    def save_telegram_backtest_run(
        self,
        *,
        market_ref: str,
        payload: dict[str, Any],
        params_json: dict[str, Any] | None = None,
        summary_json: dict[str, Any] | None = None,
    ) -> int:
        market = payload.get("market") if isinstance(payload, dict) else {}
        market_id = str((market or {}).get("market_id") or "") or None
        market_slug = str((market or {}).get("slug") or "") or None
        params = params_json if isinstance(params_json, dict) else (payload.get("meta") if isinstance(payload, dict) else {})
        summary = summary_json if isinstance(summary_json, dict) else (payload.get("summary") if isinstance(payload, dict) else {})

        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                self._ensure_telegram_backtest_tables(cur)
                cur.execute(
                    """
                    INSERT INTO telegram_backtest_runs (
                      market_ref, market_id, market_slug, params_json, summary_json, payload_json
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s
                    )
                    RETURNING run_id;
                    """,
                    (
                        str(market_ref or "").strip(),
                        market_id,
                        market_slug,
                        Jsonb(_json_sanitize(params or {})),
                        Jsonb(_json_sanitize(summary or {})),
                        Jsonb(_json_sanitize(payload or {})),
                    ),
                )
                run_id = int(cur.fetchone()[0])
            conn.commit()
        return run_id

    def list_telegram_backtest_runs(
        self,
        *,
        limit: int = 20,
        market_ref: str | None = None,
    ) -> list[dict[str, Any]]:
        effective_limit = max(1, min(int(limit), 200))
        ref = str(market_ref or "").strip() or None
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                self._ensure_telegram_backtest_tables(cur)
                if ref:
                    cur.execute(
                        """
                        SELECT
                          run_id,
                          created_at,
                          market_ref,
                          market_id,
                          market_slug,
                          params_json,
                          summary_json
                        FROM telegram_backtest_runs
                        WHERE market_ref = %s
                           OR market_slug = %s
                           OR market_id = %s
                        ORDER BY run_id DESC
                        LIMIT %s;
                        """,
                        (ref, ref, ref, effective_limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                          run_id,
                          created_at,
                          market_ref,
                          market_id,
                          market_slug,
                          params_json,
                          summary_json
                        FROM telegram_backtest_runs
                        ORDER BY run_id DESC
                        LIMIT %s;
                        """,
                        (effective_limit,),
                    )
                return list(cur.fetchall())

    def get_telegram_backtest_run(self, run_id: int) -> dict[str, Any] | None:
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                self._ensure_telegram_backtest_tables(cur)
                cur.execute(
                    """
                    SELECT
                      run_id,
                      created_at,
                      market_ref,
                      market_id,
                      market_slug,
                      params_json,
                      summary_json,
                      payload_json
                    FROM telegram_backtest_runs
                    WHERE run_id = %s
                    LIMIT 1;
                    """,
                    (int(run_id),),
                )
                return cur.fetchone()

    def ensure_agent_runtime_tables(self) -> None:
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                self._ensure_agent_runtime_tables(cur)
            conn.commit()

    def upsert_agent_runtime_status(
        self,
        *,
        agent_name: str,
        status: dict[str, Any],
        touch_heartbeat: bool = True,
    ) -> None:
        normalized_agent = str(agent_name or "").strip()
        if not normalized_agent:
            return
        payload = _json_sanitize(status or {})
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                self._ensure_agent_runtime_tables(cur)
                cur.execute(
                    """
                    INSERT INTO agent_runtime_status (
                      agent_name, heartbeat_at, updated_at, status_json
                    ) VALUES (
                      %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW(), %s
                    )
                    ON CONFLICT (agent_name) DO UPDATE SET
                      heartbeat_at = CASE WHEN %s THEN NOW() ELSE agent_runtime_status.heartbeat_at END,
                      updated_at = NOW(),
                      status_json = COALESCE(agent_runtime_status.status_json, '{}'::jsonb) || EXCLUDED.status_json;
                    """,
                    (
                        normalized_agent,
                        bool(touch_heartbeat),
                        Jsonb(payload),
                        bool(touch_heartbeat),
                    ),
                )
            conn.commit()

    def append_agent_runtime_event(
        self,
        *,
        agent_name: str,
        level: str,
        event_type: str,
        message: str,
        stage: str | None = None,
        market_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_agent = str(agent_name or "").strip()
        if not normalized_agent:
            return
        with psycopg.connect(self.database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                self._ensure_agent_runtime_tables(cur)
                cur.execute(
                    """
                    INSERT INTO agent_runtime_events (
                      agent_name, event_time, level, stage, event_type, market_id, message, payload_json
                    ) VALUES (
                      %s, NOW(), %s, %s, %s, %s, %s, %s
                    );
                    """,
                    (
                        normalized_agent,
                        str(level or "info").strip().lower(),
                        _optional_text(stage),
                        str(event_type or "event").strip().lower(),
                        _optional_text(market_id),
                        str(message or "").strip(),
                        Jsonb(_json_sanitize(payload or {})),
                    ),
                )
            conn.commit()

    @staticmethod
    def _upsert_market(cur: psycopg.Cursor, row: dict[str, Any]) -> None:
        cur.execute(
            """
            INSERT INTO markets (
              market_id, condition_id, question_id, event_id, event_slug, slug, question,
              description, rules_text, market_context, market_archetype, is_local_candidate,
              local_score, local_reason_json, active, closed, archived, accepting_orders,
              enable_order_book, high_competition, end_date, rules_hash, raw_json, last_seen_at
            ) VALUES (
              %(market_id)s, %(condition_id)s, %(question_id)s, %(event_id)s, %(event_slug)s, %(slug)s, %(question)s,
              %(description)s, %(rules_text)s, %(market_context)s, %(market_archetype)s, %(is_local_candidate)s,
              %(local_score)s, %(local_reason_json)s, %(active)s, %(closed)s, %(archived)s, %(accepting_orders)s,
              %(enable_order_book)s, %(high_competition)s, %(end_date)s, %(rules_hash)s, %(raw_json)s, NOW()
            )
            ON CONFLICT (market_id) DO UPDATE SET
              condition_id = EXCLUDED.condition_id,
              question_id = EXCLUDED.question_id,
              event_id = EXCLUDED.event_id,
              event_slug = EXCLUDED.event_slug,
              slug = EXCLUDED.slug,
              question = EXCLUDED.question,
              description = EXCLUDED.description,
              rules_text = EXCLUDED.rules_text,
              market_context = EXCLUDED.market_context,
              market_archetype = EXCLUDED.market_archetype,
              is_local_candidate = EXCLUDED.is_local_candidate,
              local_score = EXCLUDED.local_score,
              local_reason_json = EXCLUDED.local_reason_json,
              active = EXCLUDED.active,
              closed = EXCLUDED.closed,
              archived = EXCLUDED.archived,
              accepting_orders = EXCLUDED.accepting_orders,
              enable_order_book = EXCLUDED.enable_order_book,
              high_competition = EXCLUDED.high_competition,
              end_date = EXCLUDED.end_date,
              rules_hash = EXCLUDED.rules_hash,
              raw_json = EXCLUDED.raw_json,
              updated_at = NOW(),
              last_seen_at = NOW();
            """,
            {
                **row,
                "local_reason_json": Jsonb(row.get("local_reason_json") or {}),
                "raw_json": Jsonb(row.get("raw_json") or {}),
            },
        )

    @staticmethod
    def _replace_market_outcomes(cur: psycopg.Cursor, market_id: str, outcomes: list[dict[str, Any]]) -> None:
        cur.execute("DELETE FROM market_outcomes WHERE market_id = %s;", (market_id,))
        if not outcomes:
            return

        cur.executemany(
            """
            INSERT INTO market_outcomes (
              market_id, outcome_index, outcome_label, token_id, price, probability,
              is_likely, is_unlikely, last_seen_at, raw_json
            ) VALUES (
              %(market_id)s, %(outcome_index)s, %(outcome_label)s, %(token_id)s, %(price)s, %(probability)s,
              %(is_likely)s, %(is_unlikely)s, NOW(), %(raw_json)s
            );
            """,
            [
                {
                    **item,
                    "raw_json": Jsonb(item.get("raw_json") or {}),
                }
                for item in outcomes
            ],
        )

    @staticmethod
    def _insert_snapshot(cur: psycopg.Cursor, row: dict[str, Any]) -> None:
        cur.execute(
            """
            INSERT INTO market_snapshots (
              market_id, observed_at, best_bid, best_ask, last_trade_price,
              volume_usd, liquidity_usd, spread, raw_json
            ) VALUES (
              %(market_id)s, %(observed_at)s, %(best_bid)s, %(best_ask)s, %(last_trade_price)s,
              %(volume_usd)s, %(liquidity_usd)s, %(spread)s, %(raw_json)s
            );
            """,
            {
                **row,
                "raw_json": Jsonb(row.get("raw_json") or {}),
            },
        )

    @staticmethod
    def _ensure_telegram_backtest_tables(cur: psycopg.Cursor) -> None:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_backtest_runs (
              run_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              market_ref TEXT NOT NULL,
              market_id TEXT,
              market_slug TEXT,
              params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
              summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
              payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_telegram_backtest_runs_created
              ON telegram_backtest_runs (created_at DESC);
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_telegram_backtest_runs_market
              ON telegram_backtest_runs (market_ref, market_slug, market_id);
            """
        )

    @staticmethod
    def _ensure_agent_runtime_tables(cur: psycopg.Cursor) -> None:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runtime_status (
              agent_name TEXT PRIMARY KEY,
              heartbeat_at TIMESTAMPTZ,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              status_json JSONB NOT NULL DEFAULT '{}'::jsonb
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runtime_events (
              event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              agent_name TEXT NOT NULL,
              event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              level TEXT NOT NULL DEFAULT 'info',
              stage TEXT,
              event_type TEXT NOT NULL DEFAULT 'event',
              market_id TEXT,
              message TEXT NOT NULL DEFAULT '',
              payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_runtime_events_agent_time
              ON agent_runtime_events (agent_name, event_time DESC);
            """
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _note_with_source(value: Any, *, source: str) -> str:
    note = str(value or "").strip()
    if note:
        return note
    return f"source:{source}"


def _json_sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_sanitize(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_sanitize(inner) for inner in value]
    try:
        return json.loads(json.dumps(value))
    except Exception:
        return str(value)
