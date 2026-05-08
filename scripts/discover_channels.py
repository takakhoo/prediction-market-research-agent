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
from src.polymarket.telegram_pipeline import MarketTelegramDiscoveryService


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
        description="Discover Telegram channels for track_now markets and upsert channel mappings."
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Env file path(s). Can be passed multiple times. Defaults to .env if omitted.",
    )
    parser.add_argument("--watch", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-seconds", type=int, default=120, help="Watch loop interval.")
    parser.add_argument("--market-limit", type=int, default=30, help="Track_now markets scanned per run.")
    parser.add_argument(
        "--target-channels-per-market",
        type=int,
        default=25,
        help="Desired active linked channels per market.",
    )
    parser.add_argument(
        "--global-max-channels",
        type=int,
        default=500,
        help="Cap on unique discovered channels per run.",
    )
    parser.add_argument("--query-results-limit", type=int, default=20, help="TDLib search results per query.")
    parser.add_argument("--max-queries-per-market", type=int, default=6, help="Queries generated per market.")
    parser.add_argument("--similar-per-seed", type=int, default=10, help="Similar channels per seed channel.")
    parser.add_argument(
        "--similar-seed-channels",
        type=int,
        default=3,
        help="Top discovered channels per market used for similar expansion.",
    )
    parser.add_argument(
        "--min-channel-members",
        type=int,
        default=None,
        help="Reject discovered channels below this member count floor.",
    )
    parser.add_argument(
        "--min-channel-relevance-score",
        type=float,
        default=None,
        help="Reject discovered channels below this market-channel relevance score.",
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


def create_service(*, use_pooled: bool) -> tuple[MarketTelegramDiscoveryService, TDLibDiscoveryClient]:
    poly_config = PolymarketConfig.from_env()
    db_url = poly_config.database_url if use_pooled else poly_config.direct_url
    if not db_url:
        raise RuntimeError(
            "No DB URL configured. Set SUPABASE_DIRECT_DB_URL (preferred) or SUPABASE_DB_URL in env."
        )

    discovery_settings = DiscoverySettings()
    repository = MarketIntelRepository(db_url)
    tdlib_client = TDLibDiscoveryClient(discovery_settings)
    service = MarketTelegramDiscoveryService(
        repository=repository,
        tdlib_client=tdlib_client,
        log_fn=print,
    )
    return service, tdlib_client


async def run_once(args: argparse.Namespace, service: MarketTelegramDiscoveryService) -> int:
    started = time.time()
    config = PolymarketConfig.from_env()
    min_channel_members = (
        config.telegram_min_channel_members
        if args.min_channel_members is None
        else args.min_channel_members
    )
    min_channel_relevance_score = (
        config.telegram_min_channel_relevance_score
        if args.min_channel_relevance_score is None
        else args.min_channel_relevance_score
    )
    stats = await service.discover_once(
        market_limit=max(1, min(int(args.market_limit), 1000)),
        target_channels_per_market=max(1, min(int(args.target_channels_per_market), 250)),
        global_max_channels=max(1, min(int(args.global_max_channels), 5000)),
        query_results_limit=max(1, min(int(args.query_results_limit), 50)),
        max_queries_per_market=max(1, min(int(args.max_queries_per_market), 20)),
        similar_per_seed=max(0, min(int(args.similar_per_seed), 50)),
        similar_seed_channels=max(0, min(int(args.similar_seed_channels), 10)),
        min_channel_members=max(0, min(int(min_channel_members), 10_000_000)),
        min_channel_relevance_score=max(0.0, min(float(min_channel_relevance_score), 1.0)),
    )
    elapsed_ms = int((time.time() - started) * 1000)
    print(
        "discover_complete "
        f"markets_considered={stats.markets_considered} "
        f"markets_updated={stats.markets_updated} "
        f"queries_sent={stats.queries_sent} "
        f"channels_written={stats.channels_written} "
        f"links_written={stats.links_written} "
        f"unique_channels_seen={stats.unique_channels_seen} "
        f"api_errors={stats.api_errors} "
        f"elapsed_ms={elapsed_ms}"
    )
    return 0


async def async_main(args: argparse.Namespace) -> int:
    service, tdlib_client = create_service(use_pooled=args.pooled)
    config = PolymarketConfig.from_env()
    effective_min_members = (
        config.telegram_min_channel_members
        if args.min_channel_members is None
        else args.min_channel_members
    )
    effective_min_relevance = (
        config.telegram_min_channel_relevance_score
        if args.min_channel_relevance_score is None
        else args.min_channel_relevance_score
    )
    print(
        f"discover_config market_limit={args.market_limit} "
        f"target_channels_per_market={args.target_channels_per_market} "
        f"global_max_channels={args.global_max_channels} "
        f"query_results_limit={args.query_results_limit} "
        f"max_queries_per_market={args.max_queries_per_market} "
        f"similar_per_seed={args.similar_per_seed} "
        f"similar_seed_channels={args.similar_seed_channels} "
        f"min_channel_members={effective_min_members} "
        f"min_channel_relevance_score={effective_min_relevance}"
    )

    try:
        if not args.watch:
            return await run_once(args, service)

        interval = max(10, int(args.interval_seconds))
        print(f"watch_mode enabled interval_seconds={interval}")
        while True:
            try:
                await run_once(args, service)
            except KeyboardInterrupt:
                print("watch_mode stopped by user")
                return 130
            except Exception as exc:
                print(f"discover_error {type(exc).__name__}: {exc}", file=sys.stderr)
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
