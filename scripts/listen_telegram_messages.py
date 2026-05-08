#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.discovery.config import DiscoverySettings
from src.discovery.tdlib_client import TDLibDiscoveryClient
from src.polymarket.config import PolymarketConfig
from src.polymarket.market_intel_repository import MarketIntelRepository
from src.polymarket.telegram_pipeline import MarketTelegramListenerService


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
    parser = argparse.ArgumentParser(
        description="Poll mapped Telegram channels, persist messages, and evaluate market-rule matches."
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Env file path(s). Can be passed multiple times. Defaults to .env if omitted.",
    )
    parser.add_argument("--watch", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-seconds", type=int, default=8, help="Watch loop interval.")
    parser.add_argument("--channel-limit", type=int, default=500, help="Max channels polled per cycle.")
    parser.add_argument(
        "--markets-per-channel",
        type=int,
        default=25,
        help="Max mapped markets evaluated per channel.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=10,
        help="Recent messages fetched per channel per cycle.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Concurrent TDLib history fetches.",
    )
    parser.add_argument(
        "--max-new-messages",
        type=int,
        default=3000,
        help="Global cap on newly processed messages per cycle.",
    )
    parser.add_argument(
        "--pooled",
        action="store_true",
        help="Use pooled DB URL for writes (defaults to direct URL preference).",
    )
    return parser


def resolve_env_files(raw_paths: list[str]) -> list[Path]:
    if not raw_paths:
        raw_paths = [".env"]
    resolved = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        resolved.append(path)
    return resolved


def create_service(*, use_pooled: bool) -> tuple[MarketTelegramListenerService, TDLibDiscoveryClient]:
    poly_config = PolymarketConfig.from_env()
    db_url = poly_config.database_url if use_pooled else poly_config.direct_url
    if not db_url:
        raise RuntimeError(
            "No DB URL configured. Set SUPABASE_DIRECT_DB_URL (preferred) or SUPABASE_DB_URL in env."
        )

    discovery_settings = DiscoverySettings()
    repository = MarketIntelRepository(db_url)
    tdlib_client = TDLibDiscoveryClient(discovery_settings)
    service = MarketTelegramListenerService(
        repository=repository,
        tdlib_client=tdlib_client,
        log_fn=print,
    )
    return service, tdlib_client


async def run_once(args: argparse.Namespace, service: MarketTelegramListenerService) -> int:
    started = time.time()
    stats = await service.listen_once(
        channel_limit=max(1, min(int(args.channel_limit), 5000)),
        markets_per_channel=max(1, min(int(args.markets_per_channel), 200)),
        history_limit=max(1, min(int(args.history_limit), 50)),
        concurrency=max(1, min(int(args.concurrency), 32)),
        max_new_messages=max(1, min(int(args.max_new_messages), 100000)),
    )
    elapsed_ms = int((time.time() - started) * 1000)
    print(
        "listener_complete "
        f"channels_polled={stats.channels_polled} "
        f"fetch_errors={stats.fetch_errors} "
        f"new_messages={stats.new_messages} "
        f"evaluated_pairs={stats.evaluated_pairs} "
        f"matched_pairs={stats.matched_pairs} "
        f"activations_inserted={stats.activations_inserted} "
        f"elapsed_ms={elapsed_ms}"
    )
    return 0


async def async_main(args: argparse.Namespace) -> int:
    service, tdlib_client = create_service(use_pooled=args.pooled)
    print(
        f"listener_config channel_limit={args.channel_limit} "
        f"markets_per_channel={args.markets_per_channel} "
        f"history_limit={args.history_limit} "
        f"concurrency={args.concurrency} "
        f"max_new_messages={args.max_new_messages}"
    )

    try:
        if not args.watch:
            return await run_once(args, service)

        interval = max(2, int(args.interval_seconds))
        print(f"watch_mode enabled interval_seconds={interval}")
        while True:
            try:
                await run_once(args, service)
            except KeyboardInterrupt:
                print("watch_mode stopped by user")
                return 130
            except Exception as exc:
                print(f"listener_error {type(exc).__name__}: {exc}", file=sys.stderr)
            await asyncio.sleep(interval)
    finally:
        await tdlib_client.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    for env_path in resolve_env_files(args.env_file):
        load_env_file(env_path)

    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
