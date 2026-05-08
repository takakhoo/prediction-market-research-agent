from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import aiosqlite

from .db import init_db, utc_now_iso


class DiscoveryRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self) -> None:
        await init_db(self.db_path)

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @asynccontextmanager
    async def _connection(self):
        conn = await self._connect()
        try:
            yield conn
        finally:
            await conn.close()

    async def upsert_channels(self, channels: Iterable[Dict[str, Any]], source: str) -> None:
        items = list(channels)
        if not items:
            return

        now = utc_now_iso()
        async with self._connection() as conn:
            for channel in items:
                await conn.execute(
                    """
                    INSERT INTO channels (chat_id, title, username, description, member_count, last_seen_at, last_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET
                      title = excluded.title,
                      username = excluded.username,
                      description = excluded.description,
                      member_count = excluded.member_count,
                      last_seen_at = excluded.last_seen_at,
                      last_source = excluded.last_source;
                    """,
                    (
                        channel["chat_id"],
                        channel.get("title") or "",
                        channel.get("username"),
                        channel.get("description"),
                        channel.get("member_count"),
                        now,
                        source,
                    ),
                )
            await conn.commit()

    async def get_channel(self, chat_id: int) -> Optional[Dict[str, Any]]:
        async with self._connection() as conn:
            cursor = await conn.execute(
                """
                SELECT chat_id, title, username, description, member_count, last_seen_at, last_source
                FROM channels
                WHERE chat_id = ?;
                """,
                (chat_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def upsert_messages(self, chat_id: int, messages: Iterable[Dict[str, Any]]) -> None:
        items = list(messages)
        if not items:
            return

        async with self._connection() as conn:
            for message in items:
                await conn.execute(
                    """
                    INSERT INTO channel_messages (chat_id, message_id, posted_at, text, link)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chat_id, message_id) DO UPDATE SET
                      posted_at = excluded.posted_at,
                      text = excluded.text,
                      link = excluded.link;
                    """,
                    (
                        chat_id,
                        message["message_id"],
                        message.get("posted_at"),
                        message.get("text") or "",
                        message.get("url"),
                    ),
                )
            await conn.commit()

    async def create_discovery_run(self, query: str) -> str:
        run_id = str(uuid.uuid4())
        async with self._connection() as conn:
            await conn.execute(
                "INSERT INTO discovery_runs (run_id, query, created_at) VALUES (?, ?, ?);",
                (run_id, query, utc_now_iso()),
            )
            await conn.commit()
        return run_id

    async def save_similar_edges(self, run_id: str, edges: Iterable[Dict[str, int]]) -> None:
        items = list(edges)
        if not items:
            return

        async with self._connection() as conn:
            for edge in items:
                await conn.execute(
                    """
                    INSERT INTO similar_edges (run_id, parent_chat_id, child_chat_id, depth)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(run_id, parent_chat_id, child_chat_id) DO UPDATE SET
                      depth = excluded.depth;
                    """,
                    (
                        run_id,
                        edge["parent_chat_id"],
                        edge["child_chat_id"],
                        edge["depth"],
                    ),
                )
            await conn.commit()

    async def set_watchlist_item(
        self,
        *,
        chat_id: int,
        trust_weight: float,
        tags: List[str],
        notes: str,
    ) -> Dict[str, Any]:
        if trust_weight < 0.0 or trust_weight > 1.0:
            raise ValueError("trust_weight must be between 0.0 and 1.0")

        now = utc_now_iso()
        tags_json = json.dumps(tags, ensure_ascii=True)

        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO watchlist (chat_id, trust_weight, tags_json, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                  trust_weight = excluded.trust_weight,
                  tags_json = excluded.tags_json,
                  notes = excluded.notes,
                  updated_at = excluded.updated_at;
                """,
                (chat_id, trust_weight, tags_json, notes, now, now),
            )
            await conn.commit()

        item = await self.get_watchlist_item(chat_id)
        if item is None:
            raise RuntimeError("watchlist upsert failed")
        return item

    async def get_watchlist_item(self, chat_id: int) -> Optional[Dict[str, Any]]:
        async with self._connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                  w.chat_id,
                  c.title,
                  c.username,
                  c.description,
                  c.member_count,
                  w.trust_weight,
                  w.tags_json,
                  w.notes,
                  w.created_at,
                  w.updated_at
                FROM watchlist w
                LEFT JOIN channels c ON c.chat_id = w.chat_id
                WHERE w.chat_id = ?;
                """,
                (chat_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        return _deserialize_watchlist_row(row)

    async def patch_watchlist_item(
        self,
        *,
        chat_id: int,
        trust_weight: Optional[float],
        tags: Optional[List[str]],
        notes: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        current = await self.get_watchlist_item(chat_id)
        if current is None:
            return None

        new_trust = current["trust_weight"] if trust_weight is None else trust_weight
        new_tags = current["tags"] if tags is None else tags
        new_notes = current["notes"] if notes is None else notes

        return await self.set_watchlist_item(
            chat_id=chat_id,
            trust_weight=new_trust,
            tags=new_tags,
            notes=new_notes,
        )

    async def get_watchlist(self) -> List[Dict[str, Any]]:
        async with self._connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                  w.chat_id,
                  c.title,
                  c.username,
                  c.description,
                  c.member_count,
                  w.trust_weight,
                  w.tags_json,
                  w.notes,
                  w.created_at,
                  w.updated_at
                FROM watchlist w
                LEFT JOIN channels c ON c.chat_id = w.chat_id
                ORDER BY w.updated_at DESC;
                """
            )
            rows = await cursor.fetchall()

        return [_deserialize_watchlist_row(row) for row in rows]



def _deserialize_watchlist_row(row: aiosqlite.Row) -> Dict[str, Any]:
    item = dict(row)
    item["tags"] = json.loads(item.pop("tags_json") or "[]")
    return item
