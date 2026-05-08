#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.discovery.config import DiscoverySettings
from src.discovery.tdlib_client import TDLibDiscoveryClient
from src.polymarket.config import PolymarketConfig
from src.polymarket.market_intel_repository import MarketIntelRepository
from src.polymarket.realtime_listener import (
    MarketTelegramRealtimeListenerService,
    RealtimeMessageBatchMatcher,
)

AGENT_NAME = "telegram-realtime-listener"


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


def resolve_env_files(raw_paths: list[str]) -> list[Path]:
    if not raw_paths:
        raw_paths = [".env"]
    resolved: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        resolved.append(path)
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Real-time Telegram listener restricted to the saved handpicked channel-market graph."
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Env file path(s). Can be passed multiple times. Defaults to .env if omitted.",
    )
    parser.add_argument("--link-source", default="ai_handpicked_batch_v1", help="channel_market_map link_source filter.")
    parser.add_argument("--source-file", default="", help="Optional handpicked source_file filter.")
    parser.add_argument("--channel-limit", type=int, default=500, help="Max watched channels.")
    parser.add_argument("--markets-per-channel", type=int, default=25, help="Max linked markets evaluated per channel.")
    parser.add_argument("--worker-concurrency", type=int, default=4, help="Concurrent message workers.")
    parser.add_argument("--bindings-refresh-seconds", type=int, default=90, help="Saved graph refresh interval.")
    parser.add_argument("--candidate-batch-size", type=int, default=24, help="Candidate markets per AI call.")
    parser.add_argument("--min-confidence", type=float, default=0.80, help="Minimum match confidence.")
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=5, help="Runtime heartbeat interval.")
    parser.add_argument("--pooled", action="store_true", help="Use pooled DB URL for writes.")
    return parser


def create_repository(*, use_pooled: bool) -> MarketIntelRepository:
    config = PolymarketConfig.from_env()
    db_url = config.database_url if use_pooled else config.direct_url
    if not db_url:
        raise RuntimeError(
            "No DB URL configured. Set SUPABASE_DIRECT_DB_URL (preferred) or SUPABASE_DB_URL in env."
        )
    return MarketIntelRepository(db_url)


class AgentRuntimeReporter:
    def __init__(self, repository: MarketIntelRepository, *, agent_name: str = AGENT_NAME):
        self.repository = repository
        self.agent_name = agent_name
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.repository.ensure_agent_runtime_tables()

    def status(self, **patch: object) -> None:
        try:
            base: dict[str, object] = {
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
            pass

    def event(
        self,
        *,
        level: str,
        stage: str,
        event_type: str,
        message: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        try:
            self.repository.append_agent_runtime_event(
                agent_name=self.agent_name,
                level=level,
                stage=stage,
                event_type=event_type,
                message=message,
                payload=payload or {},
            )
        except Exception:
            pass


def _log_and_report(message: str, reporter: AgentRuntimeReporter) -> None:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    print(f"{timestamp} {message}", flush=True)

    lower = message.lower()
    level = "error" if ("error" in lower or "failure" in lower) else "info"
    event_type = (message.split(" ", 1)[0].strip().lower() or "listener_event")[:80]
    reporter.event(
        level=level,
        stage="listener",
        event_type=event_type,
        message=message,
    )


async def _heartbeat_loop(
    *,
    service: MarketTelegramRealtimeListenerService,
    reporter: AgentRuntimeReporter,
    link_source: str,
    source_file: str,
    matcher: RealtimeMessageBatchMatcher,
    interval_seconds: int,
) -> None:
    while True:
        snapshot = service.snapshot()
        reporter.status(
            stage="listener",
            state="running" if snapshot.started else "starting",
            link_source=link_source,
            source_file=source_file or None,
            matcher_version=matcher.matcher_version,
            matcher_model=matcher.model,
            candidate_batch_size=int(matcher.candidate_batch_size),
            min_confidence=float(matcher.min_confidence),
            watched_channels=int(snapshot.watched_channels),
            watched_markets=int(snapshot.watched_markets),
            queued_messages=int(snapshot.queued_messages),
            received_messages=int(snapshot.received_messages),
            stored_messages=int(snapshot.stored_messages),
            evaluated_messages=int(snapshot.evaluated_messages),
            matched_messages=int(snapshot.matched_messages),
            matched_pairs=int(snapshot.matched_pairs),
            activations_inserted=int(snapshot.activations_inserted),
            ai_failures=int(snapshot.ai_failures),
            last_binding_refresh_at=snapshot.last_binding_refresh_at,
            last_message_at=snapshot.last_message_at,
            last_message_chat_id=snapshot.last_message_chat_id,
            last_message_id=snapshot.last_message_id,
            last_message_preview=snapshot.last_message_preview,
        )
        await asyncio.sleep(interval_seconds)


async def main_async(args: argparse.Namespace) -> int:
    repository = create_repository(use_pooled=args.pooled)
    reporter = AgentRuntimeReporter(repository)
    tdlib_client = TDLibDiscoveryClient(DiscoverySettings())
    matcher = RealtimeMessageBatchMatcher(
        config=PolymarketConfig.from_env(),
        candidate_batch_size=max(1, min(int(args.candidate_batch_size), 40)),
        min_confidence=max(0.0, min(float(args.min_confidence), 1.0)),
    )
    service = MarketTelegramRealtimeListenerService(
        repository=repository,
        tdlib_client=tdlib_client,
        matcher=matcher,
        log_fn=lambda message: _log_and_report(message, reporter),
    )

    reporter.status(
        stage="boot",
        state="starting",
        link_source=str(args.link_source or "").strip() or "ai_handpicked_batch_v1",
        source_file=str(args.source_file or "").strip() or None,
        candidate_batch_size=int(matcher.candidate_batch_size),
        min_confidence=float(matcher.min_confidence),
        worker_concurrency=max(1, min(int(args.worker_concurrency), 16)),
    )
    reporter.event(
        level="info",
        stage="boot",
        event_type="agent_start",
        message="Real-time Telegram listener starting",
    )

    heartbeat_task: asyncio.Task[None] | None = None
    try:
        await service.start(
            channel_limit=max(1, min(int(args.channel_limit), 5000)),
            markets_per_channel=max(1, min(int(args.markets_per_channel), 200)),
            link_source=str(args.link_source or "").strip() or "ai_handpicked_batch_v1",
            source_file=str(args.source_file or "").strip() or None,
            worker_concurrency=max(1, min(int(args.worker_concurrency), 16)),
            bindings_refresh_seconds=max(10, min(int(args.bindings_refresh_seconds), 3600)),
        )
        snapshot = service.snapshot()
        reporter.status(
            stage="listener",
            state="running",
            watched_channels=int(snapshot.watched_channels),
            watched_markets=int(snapshot.watched_markets),
        )
        reporter.event(
            level="info",
            stage="listener",
            event_type="listener_started",
            message="Real-time Telegram listener started",
            payload={
                "watched_channels": int(snapshot.watched_channels),
                "watched_markets": int(snapshot.watched_markets),
            },
        )

        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(
                service=service,
                reporter=reporter,
                link_source=str(args.link_source or "").strip() or "ai_handpicked_batch_v1",
                source_file=str(args.source_file or "").strip(),
                matcher=matcher,
                interval_seconds=max(2, min(int(args.heartbeat_interval_seconds), 60)),
            )
        )
        await tdlib_client.idle()
        return 0
    except KeyboardInterrupt:
        reporter.status(stage="stopped", state="keyboard_interrupt")
        reporter.event(
            level="info",
            stage="listener",
            event_type="listener_stopped",
            message="Real-time Telegram listener stopped by user",
        )
        return 130
    except Exception as exc:
        reporter.status(stage="listener", state="error", last_error=f"{type(exc).__name__}: {exc}")
        reporter.event(
            level="error",
            stage="listener",
            event_type="listener_error",
            message=f"{type(exc).__name__}: {exc}",
        )
        print(f"listener_error {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        reporter.status(stage="shutdown", state="closing")
        try:
            await service.stop()
        finally:
            await tdlib_client.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    for env_path in resolve_env_files(args.env_file):
        load_env_file(env_path)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
