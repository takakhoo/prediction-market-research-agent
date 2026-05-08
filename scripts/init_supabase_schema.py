#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

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


def resolve_db_url(use_direct: bool) -> str:
    if use_direct:
        for key in ("SUPABASE_DIRECT_DB_URL", "DIRECT_URL", "SUPABASE_DB_URL", "DATABASE_URL"):
            value = os.getenv(key, "").strip()
            if value:
                return value
    else:
        for key in ("SUPABASE_DB_URL", "DATABASE_URL", "SUPABASE_DIRECT_DB_URL", "DIRECT_URL"):
            value = os.getenv(key, "").strip()
            if value:
                return value
    raise RuntimeError(
        "No database URL found. Set one of: SUPABASE_DIRECT_DB_URL, DIRECT_URL, SUPABASE_DB_URL, DATABASE_URL"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Postgres schema SQL to Supabase.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Env file containing DB URLs.",
    )
    parser.add_argument(
        "--sql-file",
        default="sql/001_init_market_intel_schema.sql",
        help="Path to SQL schema file.",
    )
    parser.add_argument(
        "--pooled",
        action="store_true",
        help="Use pooled URL first (SUPABASE_DB_URL / DATABASE_URL).",
    )
    args = parser.parse_args()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    load_env_file(env_file)

    sql_file = Path(args.sql_file)
    if not sql_file.is_absolute():
        sql_file = ROOT / sql_file
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    db_url = resolve_db_url(use_direct=not args.pooled)
    sql_text = sql_file.read_text(encoding="utf-8")

    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError("psycopg is not installed. Install dependencies from pyproject.toml.") from exc

    masked_url = db_url.split("@", 1)[-1]
    print(f"Applying schema using {'direct' if not args.pooled else 'pooled'} URL target: {masked_url}")
    print(f"SQL file: {sql_file}")

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename;
                """
            )
            tables = [row[0] for row in cur.fetchall()]

    print(f"Schema apply complete. public tables: {len(tables)}")
    for name in tables:
        print(f" - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
