#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.polymarket.config import PolymarketConfig
from src.polymarket.market_analysis import LocalMarketRuleClassifier, MarketAnalysisService
from src.polymarket.market_intel_repository import MarketIntelRepository


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
        description="Analyze ingested Polymarket markets and classify local-information edge."
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to runtime env file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max pending markets to analyze in one pass.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Loop interval for --watch mode.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously at interval instead of single run.",
    )
    parser.add_argument(
        "--pooled",
        action="store_true",
        help="Use pooled DB URL for writes (defaults to direct URL preference).",
    )
    parser.add_argument(
        "--analysis-version",
        default="",
        help="Optional analysis version marker override written to market_analysis rows.",
    )
    parser.add_argument(
        "--prompt-version",
        default="",
        help="Optional prompt version marker override written to market_analysis rows.",
    )
    return parser


def create_service(*, use_pooled: bool, analysis_version: str, prompt_version: str) -> MarketAnalysisService:
    config = PolymarketConfig.from_env()
    db_url = config.database_url if use_pooled else config.direct_url
    if not db_url:
        raise RuntimeError(
            "No DB URL configured. Set SUPABASE_DIRECT_DB_URL (preferred) or SUPABASE_DB_URL in .env."
        )

    repository = MarketIntelRepository(db_url)
    classifier = LocalMarketRuleClassifier(
        analysis_version=analysis_version or None,
        prompt_version=prompt_version or None,
    )
    return MarketAnalysisService(repository=repository, classifier=classifier, log_fn=print)


def run_once(service: MarketAnalysisService, *, limit: int) -> int:
    started = time.time()
    stats = service.analyze_pending(limit=limit)
    elapsed_ms = int((time.time() - started) * 1000)
    print(
        "analysis_complete "
        f"pending={stats.pending_markets} "
        f"analyzed={stats.analyzed_markets} "
        f"local_candidates={stats.local_candidates} "
        f"track_now={stats.track_now} "
        f"track_later={stats.track_later} "
        f"ignored={stats.ignored} "
        f"elapsed_ms={elapsed_ms}"
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    load_env_file(env_file)

    limit = max(1, min(int(args.limit), 1000))
    service = create_service(
        use_pooled=args.pooled,
        analysis_version=args.analysis_version,
        prompt_version=args.prompt_version,
    )
    print(
        f"analysis_config limit={limit} "
        f"analysis_version={args.analysis_version or 'auto'} "
        f"prompt_version={args.prompt_version or 'auto'}"
    )

    if not args.watch:
        return run_once(service, limit=limit)

    interval = max(5, int(args.interval_seconds))
    print(f"watch_mode enabled interval_seconds={interval}")
    while True:
        try:
            run_once(service, limit=limit)
        except KeyboardInterrupt:
            print("watch_mode stopped by user")
            return 130
        except Exception as exc:
            print(f"analysis_error {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
