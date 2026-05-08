from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS channels (
      chat_id INTEGER PRIMARY KEY,
      title TEXT NOT NULL,
      username TEXT,
      description TEXT,
      member_count INTEGER,
      last_seen_at TEXT NOT NULL,
      last_source TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS channel_messages (
      chat_id INTEGER NOT NULL,
      message_id INTEGER NOT NULL,
      posted_at TEXT,
      text TEXT,
      link TEXT,
      PRIMARY KEY (chat_id, message_id),
      FOREIGN KEY (chat_id) REFERENCES channels(chat_id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
      chat_id INTEGER PRIMARY KEY,
      trust_weight REAL NOT NULL CHECK(trust_weight >= 0.0 AND trust_weight <= 1.0),
      tags_json TEXT NOT NULL,
      notes TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY (chat_id) REFERENCES channels(chat_id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS discovery_runs (
      run_id TEXT PRIMARY KEY,
      query TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS similar_edges (
      run_id TEXT NOT NULL,
      parent_chat_id INTEGER NOT NULL,
      child_chat_id INTEGER NOT NULL,
      depth INTEGER NOT NULL,
      PRIMARY KEY (run_id, parent_chat_id, child_chat_id),
      FOREIGN KEY (run_id) REFERENCES discovery_runs(run_id) ON DELETE CASCADE,
      FOREIGN KEY (parent_chat_id) REFERENCES channels(chat_id) ON DELETE CASCADE,
      FOREIGN KEY (child_chat_id) REFERENCES channels(chat_id) ON DELETE CASCADE
    );
    """,
]


async def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA foreign_keys = ON;")
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)
        await conn.commit()



def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
