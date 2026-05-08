#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from psycopg.errors import QueryCanceled

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compact high-volume market tables (snapshots/outcomes/analysis history)."
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file with DB URL")
    parser.add_argument(
        "--truncate-snapshots",
        action="store_true",
        help="Delete all rows from market_snapshots.",
    )
    parser.add_argument(
        "--truncate-outcomes",
        action="store_true",
        help="Delete all rows from market_outcomes.",
    )
    parser.add_argument(
        "--compact-analysis-latest",
        action="store_true",
        help="Keep only latest market_analysis row per market_id.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, command is dry-run.",
    )
    parser.add_argument(
        "--snapshot-batch-size",
        type=int,
        default=50000,
        help="Batch size for fallback snapshot deletion if truncate times out.",
    )
    return parser.parse_args()


def _db_url_from_env() -> str:
    return (
        os.getenv("SUPABASE_DB_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
        or os.getenv("SUPABASE_DIRECT_DB_URL", "").strip()
        or os.getenv("DIRECT_URL", "").strip()
    )


def _count(cur: psycopg.Cursor, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table};")
    return int(cur.fetchone()[0])


def main() -> int:
    args = parse_args()
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    load_env_file(env_file)

    db_url = _db_url_from_env()
    if not db_url:
        print("Missing DB URL. Set SUPABASE_DB_URL or DATABASE_URL.", file=sys.stderr)
        return 1

    if not (args.truncate_snapshots or args.truncate_outcomes or args.compact_analysis_latest):
        print("Nothing selected. Add at least one action flag.", file=sys.stderr)
        return 1

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            before = {
                "market_snapshots": _count(cur, "market_snapshots"),
                "market_outcomes": _count(cur, "market_outcomes"),
                "market_analysis": _count(cur, "market_analysis"),
            }
            print("before:", before)

            if not args.apply:
                print("dry-run: no changes applied (add --apply to execute)")
                return 0

            if args.truncate_snapshots:
                try:
                    cur.execute("TRUNCATE TABLE market_snapshots;")
                    print("applied: truncated market_snapshots")
                except QueryCanceled:
                    conn.rollback()
                    batch_size = max(1000, min(int(args.snapshot_batch_size), 250000))
                    deleted_total = 0
                    print(
                        "truncate timed out; switching to batched delete for market_snapshots "
                        f"(batch_size={batch_size})"
                    )
                    while True:
                        with conn.cursor() as batch_cur:
                            batch_cur.execute(
                                """
                                DELETE FROM market_snapshots
                                WHERE snapshot_id IN (
                                  SELECT snapshot_id
                                  FROM market_snapshots
                                  ORDER BY snapshot_id
                                  LIMIT %s
                                );
                                """,
                                (batch_size,),
                            )
                            deleted = int(batch_cur.rowcount or 0)
                        conn.commit()
                        deleted_total += deleted
                        print(f"snapshot_delete_progress deleted={deleted_total}")
                        if deleted == 0:
                            break
                    print(f"applied: deleted market_snapshots rows={deleted_total}")

            if args.truncate_outcomes:
                cur.execute("TRUNCATE TABLE market_outcomes;")
                print("applied: truncated market_outcomes")

            if args.compact_analysis_latest:
                cur.execute(
                    """
                    DELETE FROM market_analysis ma
                    USING market_analysis newer
                    WHERE ma.market_id = newer.market_id
                      AND (
                        ma.analyzed_at < newer.analyzed_at
                        OR (ma.analyzed_at = newer.analyzed_at AND ma.analysis_id < newer.analysis_id)
                      );
                    """
                )
                print(f"applied: compacted market_analysis, deleted_rows={cur.rowcount}")

        conn.commit()

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            after = {
                "market_snapshots": _count(cur, "market_snapshots"),
                "market_outcomes": _count(cur, "market_outcomes"),
                "market_analysis": _count(cur, "market_analysis"),
            }
            print("after:", after)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
