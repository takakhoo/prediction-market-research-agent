#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import os
import socket
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
from src.polymarket.telegram_pipeline import MarketTelegramDiscoveryService, MarketTelegramListenerService

AGENT_NAME = "telegram-market-agent"


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
        description="Single-process Telegram market agent (channel discovery + message listener) sharing one TDLib session."
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Env file path(s). Can be passed multiple times. Defaults to .env if omitted.",
    )
    parser.add_argument("--discover-interval-seconds", type=int, default=120, help="Channel discovery interval.")
    parser.add_argument("--listen-interval-seconds", type=int, default=8, help="Message listener interval.")
    parser.add_argument("--once", action="store_true", help="Run one discovery+listener cycle and exit.")

    parser.add_argument("--market-limit", type=int, default=30, help="Track_now markets scanned per discovery cycle.")
    parser.add_argument("--target-channels-per-market", type=int, default=25, help="Desired channels per market.")
    parser.add_argument("--global-max-channels", type=int, default=500, help="Unique channels cap per discovery cycle.")
    parser.add_argument("--query-results-limit", type=int, default=20, help="TDLib search results per query.")
    parser.add_argument("--max-queries-per-market", type=int, default=6, help="Queries generated per market.")
    parser.add_argument(
        "--enable-google-serp",
        action="store_true",
        help="Use SERP API (SERPER_API_KEY/SERPAPI_API_KEY) to discover official t.me handles before TDLib search.",
    )
    parser.add_argument(
        "--max-google-queries-per-market",
        type=int,
        default=8,
        help="Google SERP queries used per market when --enable-google-serp is set.",
    )
    parser.add_argument(
        "--google-results-per-query",
        type=int,
        default=8,
        help="SERP hits fetched per Google query.",
    )
    parser.add_argument("--similar-per-seed", type=int, default=10, help="Similar channels per seed.")
    parser.add_argument("--similar-seed-channels", type=int, default=3, help="Seed channels used for similar expansion.")
    parser.add_argument("--min-channel-members", type=int, default=None, help="Reject discovered channels below this member floor.")
    parser.add_argument(
        "--min-channel-relevance-score",
        type=float,
        default=None,
        help="Reject discovered channels below this market-channel relevance score.",
    )

    parser.add_argument("--channel-limit", type=int, default=500, help="Channels polled per listener cycle.")
    parser.add_argument("--markets-per-channel", type=int, default=25, help="Markets evaluated per channel.")
    parser.add_argument("--history-limit", type=int, default=10, help="Messages fetched per channel per cycle.")
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrent TDLib history fetches.")
    parser.add_argument("--max-new-messages", type=int, default=3000, help="Max new messages processed per cycle.")
    parser.add_argument("--pooled", action="store_true", help="Use pooled DB URL for writes.")
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


def create_services(
    *,
    use_pooled: bool,
) -> tuple[MarketIntelRepository, MarketTelegramDiscoveryService, MarketTelegramListenerService, TDLibDiscoveryClient]:
    poly_config = PolymarketConfig.from_env()
    db_url = poly_config.database_url if use_pooled else poly_config.direct_url
    if not db_url:
        raise RuntimeError(
            "No DB URL configured. Set SUPABASE_DIRECT_DB_URL (preferred) or SUPABASE_DB_URL in env."
        )

    discovery_settings = DiscoverySettings()
    repository = MarketIntelRepository(db_url)
    tdlib_client = TDLibDiscoveryClient(discovery_settings)
    discovery_service = MarketTelegramDiscoveryService(
        repository=repository,
        tdlib_client=tdlib_client,
        log_fn=print,
    )
    listener_service = MarketTelegramListenerService(
        repository=repository,
        tdlib_client=tdlib_client,
        log_fn=print,
    )
    return repository, discovery_service, listener_service, tdlib_client


class AgentRuntimeReporter:
    def __init__(self, repository: MarketIntelRepository, *, agent_name: str = AGENT_NAME):
        self.repository = repository
        self.agent_name = agent_name
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.repository.ensure_agent_runtime_tables()

    def status(self, **patch: object) -> None:
        try:
            base = {
                "agent_name": self.agent_name,
                "hostname": self.hostname,
                "pid": self.pid,
                "reported_at": datetime.now(timezone.utc).isoformat(),
            }
            base.update(patch)
            self.repository.upsert_agent_runtime_status(
                agent_name=self.agent_name,
                status=base,
                touch_heartbeat=True,
            )
        except Exception:
            # Runtime telemetry should never break the main worker loop.
            pass

    def event(
        self,
        *,
        level: str,
        stage: str,
        event_type: str,
        message: str,
        market_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        try:
            self.repository.append_agent_runtime_event(
                agent_name=self.agent_name,
                level=level,
                stage=stage,
                event_type=event_type,
                market_id=market_id,
                message=message,
                payload=payload or {},
            )
        except Exception:
            pass


async def main_async(args: argparse.Namespace) -> int:
    repository, discovery_service, listener_service, tdlib_client = create_services(use_pooled=args.pooled)
    reporter = AgentRuntimeReporter(repository)
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

    discover_interval = max(20, int(args.discover_interval_seconds))
    listen_interval = max(2, int(args.listen_interval_seconds))
    next_discover_at = 0.0

    print(
        f"telegram_agent_config discover_interval_seconds={discover_interval} "
        f"listen_interval_seconds={listen_interval} "
        f"market_limit={args.market_limit} "
        f"target_channels_per_market={args.target_channels_per_market} "
        f"channel_limit={args.channel_limit} "
        f"enable_google_serp={bool(args.enable_google_serp)} "
        f"max_google_queries_per_market={args.max_google_queries_per_market} "
        f"google_results_per_query={args.google_results_per_query} "
        f"min_channel_members={effective_min_members} "
        f"min_channel_relevance_score={effective_min_relevance} "
        f"history_limit={args.history_limit} "
        f"concurrency={args.concurrency}"
    )
    reporter.status(
        stage="boot",
        state="starting",
        discover_interval_seconds=int(discover_interval),
        listen_interval_seconds=int(listen_interval),
        market_limit=int(args.market_limit),
        target_channels_per_market=int(args.target_channels_per_market),
        global_max_channels=int(args.global_max_channels),
        channel_limit=int(args.channel_limit),
    )
    reporter.event(
        level="info",
        stage="boot",
        event_type="agent_start",
        message="Telegram market agent started",
    )

    try:
        while True:
            now = time.time()

            if now >= next_discover_at:
                started = time.time()
                reporter.status(
                    stage="discovery",
                    state="running",
                    current_market_id=None,
                    current_market_slug=None,
                    current_market_question=None,
                    current_market_index=None,
                    current_market_total=None,
                    discover_cycle_started_at=datetime.now(timezone.utc).isoformat(),
                )
                reporter.event(
                    level="info",
                    stage="discovery",
                    event_type="discover_start",
                    message="Discovery cycle started",
                )
                try:
                    async def _on_market_progress(progress: dict[str, object]) -> None:
                        reporter.status(
                            stage="discovery",
                            state=str(progress.get("state") or "running"),
                            current_market_id=str(progress.get("market_id") or "") or None,
                            current_market_slug=str(progress.get("market_slug") or "") or None,
                            current_market_question=str(progress.get("market_question") or "") or None,
                            current_market_index=progress.get("market_index"),
                            current_market_total=progress.get("market_total"),
                            current_market_detail=progress,
                        )

                    discovery_stats = await discovery_service.discover_once(
                        market_limit=max(1, min(int(args.market_limit), 1000)),
                        target_channels_per_market=max(1, min(int(args.target_channels_per_market), 250)),
                        global_max_channels=max(1, min(int(args.global_max_channels), 5000)),
                        query_results_limit=max(1, min(int(args.query_results_limit), 50)),
                        max_queries_per_market=max(1, min(int(args.max_queries_per_market), 20)),
                        enable_google_serp=bool(args.enable_google_serp),
                        max_google_queries_per_market=max(1, min(int(args.max_google_queries_per_market), 30)),
                        google_results_per_query=max(1, min(int(args.google_results_per_query), 20)),
                        similar_per_seed=max(0, min(int(args.similar_per_seed), 50)),
                        similar_seed_channels=max(0, min(int(args.similar_seed_channels), 10)),
                        min_channel_members=max(0, min(int(effective_min_members), 10_000_000)),
                        min_channel_relevance_score=max(0.0, min(float(effective_min_relevance), 1.0)),
                        market_progress_callback=_on_market_progress,
                    )
                    elapsed_ms = int((time.time() - started) * 1000)
                    print(
                        "telegram_agent_discover_complete "
                        f"markets_considered={discovery_stats.markets_considered} "
                        f"markets_updated={discovery_stats.markets_updated} "
                        f"links_written={discovery_stats.links_written} "
                        f"api_errors={discovery_stats.api_errors} "
                        f"elapsed_ms={elapsed_ms}"
                    )
                    reporter.status(
                        stage="discovery",
                        state="complete",
                        discover_cycle_completed_at=datetime.now(timezone.utc).isoformat(),
                        discover_markets_considered=int(discovery_stats.markets_considered),
                        discover_markets_updated=int(discovery_stats.markets_updated),
                        discover_links_written=int(discovery_stats.links_written),
                        discover_channels_written=int(discovery_stats.channels_written),
                        discover_queries_sent=int(discovery_stats.queries_sent),
                        discover_unique_channels_seen=int(discovery_stats.unique_channels_seen),
                        discover_api_errors=int(discovery_stats.api_errors),
                        discover_elapsed_ms=int(elapsed_ms),
                    )
                    reporter.event(
                        level="info",
                        stage="discovery",
                        event_type="discover_complete",
                        message="Discovery cycle complete",
                        payload={
                            "markets_considered": int(discovery_stats.markets_considered),
                            "markets_updated": int(discovery_stats.markets_updated),
                            "links_written": int(discovery_stats.links_written),
                            "api_errors": int(discovery_stats.api_errors),
                            "elapsed_ms": int(elapsed_ms),
                        },
                    )
                except Exception as exc:
                    print(f"telegram_agent_discover_error {type(exc).__name__}: {exc}", file=sys.stderr)
                    reporter.status(
                        stage="discovery",
                        state="error",
                        discover_cycle_completed_at=datetime.now(timezone.utc).isoformat(),
                        last_error=f"{type(exc).__name__}: {exc}",
                    )
                    reporter.event(
                        level="error",
                        stage="discovery",
                        event_type="discover_error",
                        message=str(exc),
                    )
                next_discover_at = time.time() + discover_interval

            listen_started = time.time()
            reporter.status(
                stage="listener",
                state="running",
                listener_cycle_started_at=datetime.now(timezone.utc).isoformat(),
            )
            try:
                listener_stats = await listener_service.listen_once(
                    channel_limit=max(1, min(int(args.channel_limit), 5000)),
                    markets_per_channel=max(1, min(int(args.markets_per_channel), 200)),
                    history_limit=max(1, min(int(args.history_limit), 50)),
                    concurrency=max(1, min(int(args.concurrency), 32)),
                    max_new_messages=max(1, min(int(args.max_new_messages), 100000)),
                )
                listen_elapsed_ms = int((time.time() - listen_started) * 1000)
                print(
                    "telegram_agent_listener_complete "
                    f"channels_polled={listener_stats.channels_polled} "
                    f"fetch_errors={listener_stats.fetch_errors} "
                    f"new_messages={listener_stats.new_messages} "
                    f"matched_pairs={listener_stats.matched_pairs} "
                    f"activations_inserted={listener_stats.activations_inserted} "
                    f"elapsed_ms={listen_elapsed_ms}"
                )
                reporter.status(
                    stage="listener",
                    state="complete",
                    listener_cycle_completed_at=datetime.now(timezone.utc).isoformat(),
                    listener_channels_polled=int(listener_stats.channels_polled),
                    listener_fetch_errors=int(listener_stats.fetch_errors),
                    listener_new_messages=int(listener_stats.new_messages),
                    listener_matched_pairs=int(listener_stats.matched_pairs),
                    listener_activations_inserted=int(listener_stats.activations_inserted),
                    listener_elapsed_ms=int(listen_elapsed_ms),
                )
                if int(listener_stats.new_messages) > 0 or int(listener_stats.fetch_errors) > 0:
                    reporter.event(
                        level="info",
                        stage="listener",
                        event_type="listener_complete",
                        message="Listener cycle complete",
                        payload={
                            "channels_polled": int(listener_stats.channels_polled),
                            "fetch_errors": int(listener_stats.fetch_errors),
                            "new_messages": int(listener_stats.new_messages),
                            "matched_pairs": int(listener_stats.matched_pairs),
                            "activations_inserted": int(listener_stats.activations_inserted),
                            "elapsed_ms": int(listen_elapsed_ms),
                        },
                    )
            except Exception as exc:
                print(f"telegram_agent_listener_error {type(exc).__name__}: {exc}", file=sys.stderr)
                reporter.status(
                    stage="listener",
                    state="error",
                    listener_cycle_completed_at=datetime.now(timezone.utc).isoformat(),
                    last_error=f"{type(exc).__name__}: {exc}",
                )
                reporter.event(
                    level="error",
                    stage="listener",
                    event_type="listener_error",
                    message=str(exc),
                )

            if args.once:
                reporter.status(stage="idle", state="once_complete")
                return 0
            await asyncio.sleep(listen_interval)
    except KeyboardInterrupt:
        print("telegram_agent stopped by user")
        reporter.status(stage="stopped", state="keyboard_interrupt")
        return 130
    finally:
        reporter.status(stage="shutdown", state="closing_tdlib")
        await tdlib_client.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    for env_path in resolve_env_files(args.env_file):
        load_env_file(env_path)

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
