#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.polymarket.config import PolymarketConfig
from src.polymarket.gamma_client import GammaMarketsClient
from src.polymarket.market_ingest import MarketIngestService
from src.polymarket.market_intel_repository import MarketIntelRepository

_EVENT_SLUG_RE = re.compile(r"/event/([a-z0-9-]+)", re.IGNORECASE)


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
    parser = argparse.ArgumentParser(description="Ingest active Polymarket markets into Postgres.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to runtime env file.",
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
        "--page-limit",
        type=int,
        default=None,
        help="Override MARKET_INGEST_PAGE_LIMIT for this run.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override MARKET_INGEST_MAX_PAGES for this run.",
    )
    parser.add_argument(
        "--source-url",
        action="append",
        default=[],
        help="Polymarket page URL to scrape event slugs from (repeatable).",
    )
    parser.add_argument(
        "--source-url-file",
        default=None,
        help="Optional newline-delimited file containing Polymarket source URLs.",
    )
    parser.add_argument(
        "--max-slugs-per-source",
        type=int,
        default=150,
        help="Max event slugs extracted per source URL.",
    )
    parser.add_argument(
        "--source-timeout-seconds",
        type=int,
        default=25,
        help="HTTP timeout when downloading source pages.",
    )
    return parser


def create_service(use_pooled: bool) -> MarketIngestService:
    config = PolymarketConfig.from_env()
    db_url = config.database_url if use_pooled else config.direct_url
    if not db_url:
        raise RuntimeError(
            "No DB URL configured. Set SUPABASE_DIRECT_DB_URL (preferred) or SUPABASE_DB_URL in .env."
        )

    gamma = GammaMarketsClient(config)
    repository = MarketIntelRepository(db_url)
    return MarketIngestService(config=config, gamma=gamma, repository=repository, log_fn=print)


def run_once(service: MarketIngestService) -> int:
    started = time.time()
    stats = service.ingest_once()
    elapsed_ms = int((time.time() - started) * 1000)
    print(
        "ingest_complete "
        f"fetched={stats.fetched_markets} "
        f"upserted={stats.upserted_markets} "
        f"outcomes={stats.total_outcomes} "
        f"high_competition={stats.high_competition_markets} "
        f"elapsed_ms={elapsed_ms}"
    )
    return 0


def run_source_once(
    service: MarketIngestService,
    *,
    source_urls: list[str],
    max_slugs_per_source: int,
    source_timeout_seconds: int,
) -> int:
    started = time.time()
    stats = ingest_from_source_urls(
        service,
        source_urls=source_urls,
        max_slugs_per_source=max_slugs_per_source,
        timeout_seconds=source_timeout_seconds,
    )
    elapsed_ms = int((time.time() - started) * 1000)
    print(
        "ingest_complete "
        f"fetched={stats.fetched_markets} "
        f"upserted={stats.upserted_markets} "
        f"outcomes={stats.total_outcomes} "
        f"high_competition={stats.high_competition_markets} "
        f"elapsed_ms={elapsed_ms}"
    )
    return 0


def ingest_from_source_urls(
    service: MarketIngestService,
    *,
    source_urls: list[str],
    max_slugs_per_source: int,
    timeout_seconds: int,
):
    unique_urls = _dedupe_preserve([url.strip() for url in source_urls if str(url).strip()])
    if not unique_urls:
        raise RuntimeError("No source URLs were provided.")

    event_slug_count = 0
    events_loaded = 0
    missing_events = 0
    market_rows_by_id: dict[str, dict] = {}

    for source_url in unique_urls:
        event_slugs = extract_event_slugs_from_source(
            source_url,
            max_slugs=max_slugs_per_source,
            timeout_seconds=timeout_seconds,
        )
        event_slug_count += len(event_slugs)
        print(f"source_scan url={source_url} event_slugs={len(event_slugs)}")

        for slug in event_slugs:
            event = service.gamma.get_event_by_slug(slug)
            if not isinstance(event, dict):
                missing_events += 1
                continue
            events_loaded += 1
            event_id = event.get("id")
            event_slug = event.get("slug")

            markets = event.get("markets")
            if not isinstance(markets, list):
                continue
            for market in markets:
                if not isinstance(market, dict):
                    continue
                market_id = str(market.get("id") or "").strip()
                if market_id:
                    market_row = dict(market)
                    if event_id is not None and not market_row.get("eventId"):
                        market_row["eventId"] = event_id
                    if event_slug and not market_row.get("eventSlug"):
                        market_row["eventSlug"] = event_slug
                    if event_id is not None and event_slug and not market_row.get("events"):
                        market_row["events"] = [{"id": event_id, "slug": event_slug}]
                    market_rows_by_id[market_id] = market_row

    print(
        "source_summary "
        f"urls={len(unique_urls)} "
        f"event_slugs={event_slug_count} "
        f"events_loaded={events_loaded} "
        f"events_missing={missing_events} "
        f"unique_market_rows={len(market_rows_by_id)}"
    )

    return service.ingest_market_rows(list(market_rows_by_id.values()), active_only=True)


def extract_event_slugs_from_source(source_url: str, *, max_slugs: int, timeout_seconds: int) -> list[str]:
    direct_slug = _extract_direct_event_slug(source_url)
    if direct_slug:
        return [direct_slug]

    html = _fetch_text(source_url, timeout_seconds=timeout_seconds)
    slugs = _EVENT_SLUG_RE.findall(html)
    return _dedupe_preserve(slugs)[: max(1, min(int(max_slugs), 1000))]


def _extract_direct_event_slug(source_url: str) -> str | None:
    parsed = urlparse(source_url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    if parts[0].lower() != "event":
        return None
    slug = parts[1].strip().lower()
    if re.fullmatch(r"[a-z0-9-]+", slug):
        return slug
    return None


def _fetch_text(url: str, *, timeout_seconds: int) -> str:
    request = Request(
        url=url,
        method="GET",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 (PolymarketNewsAgent/0.1)",
        },
    )
    with urlopen(request, timeout=max(5, int(timeout_seconds))) as response:
        payload = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())
    return deduped


def _load_source_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = list(args.source_url or [])
    if args.source_url_file:
        source_file = Path(args.source_url_file)
        if not source_file.is_absolute():
            source_file = ROOT / source_file
        if not source_file.exists():
            raise FileNotFoundError(f"Source URL file not found: {source_file}")
        for line in source_file.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if not item or item.startswith("#"):
                continue
            urls.append(item)
    return _dedupe_preserve(urls)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    load_env_file(env_file)
    if args.page_limit is not None:
        os.environ["MARKET_INGEST_PAGE_LIMIT"] = str(max(1, min(args.page_limit, 500)))
    if args.max_pages is not None:
        os.environ["MARKET_INGEST_MAX_PAGES"] = str(max(1, min(args.max_pages, 1000)))
    source_urls = _load_source_urls(args)

    service = create_service(use_pooled=args.pooled)
    print(
        f"ingest_config page_limit={service.config.ingest_page_limit} "
        f"max_pages={service.config.ingest_max_pages} "
        f"likely_threshold={service.config.likely_probability_threshold} "
        f"unlikely_threshold={service.config.unlikely_probability_threshold} "
        f"high_competition_volume={service.config.high_competition_volume_usd}"
    )

    if source_urls and args.watch:
        parser.error("--watch cannot be combined with --source-url/--source-url-file")
    if source_urls:
        return run_source_once(
            service,
            source_urls=source_urls,
            max_slugs_per_source=args.max_slugs_per_source,
            source_timeout_seconds=args.source_timeout_seconds,
        )

    if not args.watch:
        return run_once(service)

    interval = max(5, int(args.interval_seconds))
    print(f"watch_mode enabled interval_seconds={interval}")
    while True:
        try:
            run_once(service)
        except KeyboardInterrupt:
            print("watch_mode stopped by user")
            return 130
        except Exception as exc:
            print(f"ingest_error {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
