from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request as FastAPIRequest
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError
from psycopg.rows import dict_row

from src.discovery.api import create_app as create_telegram_app
from src.discovery.config import DiscoverySettings
from src.discovery.errors import TDLibAuthRequiredError, TDLibRequestError
from src.discovery.tdlib_client import TDLibDiscoveryClient
from src.polymarket.channel_relevance import build_market_channel_profile, evaluate_channel_relevance
from src.polymarket.config import PolymarketConfig
from src.polymarket.google_serp import GoogleSerpClient, GoogleSerpError, GoogleSerpUnavailableError
from src.polymarket.gamma_client import GammaMarketsClient
from src.polymarket.http import HttpJsonError
from src.polymarket.market_analysis import LocalMarketRuleClassifier
from src.polymarket.market_intel_repository import MarketIntelRepository
from src.polymarket.telegram_pipeline import (
    BacktestChannelReviewer,
    MarketMessageMatcher,
    MarketSearchPlanner,
    MarketTelegramDiscoveryService,
)
from src.polymarket_dashboard.api import create_app as create_polymarket_app

_EVENT_SLUG_RE = re.compile(r"/event/([a-z0-9-]+)", re.IGNORECASE)
_LINK_CONFIDENCE_RE = re.compile(r"confidence=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_PIPELINE_SCOPE_SOURCE_URLS = [
    "https://polymarket.com/geopolitics",
    "https://polymarket.com/predictions/israel",
    "https://polymarket.com/search?_q=iran",
]


class TelegramBacktestRequest(BaseModel):
    market_ref: str
    target_channels: int = 25
    query_results_limit: int = 20
    max_queries: int = 6
    similar_seed_channels: int = 3
    similar_per_seed: int = 10
    min_channel_members: Optional[float] = None
    min_channel_relevance: Optional[float] = None
    planner_system_prompt: Optional[str] = None
    planner_user_prompt: Optional[str] = None
    use_prompt_override: bool = False
    local_system_prompt: Optional[str] = None
    local_user_prompt: Optional[str] = None
    use_local_prompt_override: bool = False
    reviewer_system_prompt: Optional[str] = None
    reviewer_user_prompt: Optional[str] = None
    use_reviewer_prompt_override: bool = False
    max_review_channels: int = 20
    review_message_limit: int = 10


class MarketClassificationUpdateRequest(BaseModel):
    classification: str
    local_score: Optional[float] = None
    note: Optional[str] = None


class SourceBulkClassificationRequest(BaseModel):
    source_urls: list[str]
    classification: str = "track_now"
    local_score: Optional[float] = None
    note: Optional[str] = None
    max_slugs_per_source: int = 150
    timeout_seconds: int = 25
    dry_run: bool = False


class HandpickedTargetUpdateRequest(BaseModel):
    match_status: Optional[str] = None
    matched_group_slug: Optional[str] = None
    matched_market_id: Optional[str] = None
    note: Optional[str] = None


def _extract_saved_link_confidence(note: str | None) -> float | None:
    match = _LINK_CONFIDENCE_RE.search(str(note or ""))
    if not match:
        return None
    try:
        return max(0.0, min(float(match.group(1)), 1.0))
    except ValueError:
        return None


def _extract_saved_link_reason(note: str | None) -> str:
    text = str(note or "").strip()
    if not text:
        return ""
    if ";" in text:
        return text.split(";", 1)[1].strip()
    return text


def create_app() -> FastAPI:
    app = FastAPI(title="Workspace Dashboard")
    templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
    agent_lab_file = Path(__file__).resolve().parents[2] / "polymarket-agent-interface.html"
    backtest_lock: asyncio.Lock | None = None
    shared_discovery_settings: DiscoverySettings | None = None
    shared_tdlib_client: TDLibDiscoveryClient | None = None
    shared_tdlib_init_error: str | None = None
    workspace_tdlib_session_mode = os.getenv("WORKSPACE_TDLIB_SESSION_MODE", "isolated").strip().lower()
    workspace_tdlib_session_dir_override = os.getenv("WORKSPACE_TDLIB_SESSION_DIR", "").strip()
    try:
        base_discovery_settings = DiscoverySettings()
        if hasattr(base_discovery_settings, "telegram_session_dir") and hasattr(base_discovery_settings, "model_copy"):
            if workspace_tdlib_session_mode == "primary":
                session_dir_value = base_discovery_settings.telegram_session_dir
            elif workspace_tdlib_session_dir_override:
                session_dir_value = Path(workspace_tdlib_session_dir_override)
            else:
                session_dir_value = Path(f"{base_discovery_settings.telegram_session_dir}_workspace")
            shared_discovery_settings = base_discovery_settings.model_copy(
                update={"telegram_session_dir": session_dir_value}
            )
        else:
            # Test doubles may patch DiscoverySettings with a generic object.
            shared_discovery_settings = base_discovery_settings
        shared_tdlib_client = TDLibDiscoveryClient(shared_discovery_settings)
        try:
            telegram_app = create_telegram_app(
                settings=shared_discovery_settings,
                tdlib_client=shared_tdlib_client,
            )
        except TypeError:
            # Test doubles may patch create_telegram_app with a zero-arg lambda.
            telegram_app = create_telegram_app()
    except ValidationError as exc:
        shared_tdlib_init_error = str(exc)
        telegram_app = create_telegram_app()
    polymarket_app = create_polymarket_app()

    app.mount("/telegram", telegram_app)
    app.mount("/polymarket", polymarket_app)

    @app.on_event("shutdown")
    async def close_backtest_tdlib_client() -> None:
        nonlocal shared_tdlib_client
        if shared_tdlib_client is not None:
            await shared_tdlib_client.close()
            shared_tdlib_client = None

    @app.get("/", response_class=HTMLResponse)
    async def index(request: FastAPIRequest):
        return templates.TemplateResponse(request, "dashboard.html")

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "tabs": ["telegram", "polymarket", "pipeline", "storedmarkets", "savedmap", "livelistener", "handpicked", "agentlab", "backtest", "classified", "marketrail", "runtime", "prompts"],
        }

    @app.get("/agent-lab", response_class=HTMLResponse)
    async def agent_lab():
        if not agent_lab_file.exists():
            raise HTTPException(status_code=404, detail="polymarket-agent-interface.html not found")
        return HTMLResponse(agent_lab_file.read_text(encoding="utf-8"))

    @app.get("/pipeline-map", response_class=HTMLResponse)
    async def pipeline_map(request: FastAPIRequest):
        return templates.TemplateResponse(request, "pipeline_map.html")

    @app.get("/stored-markets", response_class=HTMLResponse)
    async def stored_markets(request: FastAPIRequest):
        return templates.TemplateResponse(request, "stored_markets.html")

    @app.get("/handpicked-review", response_class=HTMLResponse)
    async def handpicked_review(request: FastAPIRequest):
        return templates.TemplateResponse(request, "handpicked_review.html")

    @app.get("/saved-channel-map", response_class=HTMLResponse)
    async def saved_channel_map(request: FastAPIRequest):
        return templates.TemplateResponse(request, "saved_channel_map.html")

    @app.get("/telegram-live", response_class=HTMLResponse)
    async def telegram_live(request: FastAPIRequest):
        return templates.TemplateResponse(request, "telegram_live.html")

    @app.get("/prompt-lab", response_class=HTMLResponse)
    async def prompt_lab(request: FastAPIRequest):
        return templates.TemplateResponse(request, "prompt_lab.html")

    @app.get("/backtest", response_class=HTMLResponse)
    async def backtest(request: FastAPIRequest):
        return templates.TemplateResponse(request, "backtest.html")

    @app.get("/classified-markets", response_class=HTMLResponse)
    async def classified_markets(request: FastAPIRequest):
        return templates.TemplateResponse(request, "classified_markets.html")

    @app.get("/market-rail", response_class=HTMLResponse)
    async def market_rail(request: FastAPIRequest):
        return templates.TemplateResponse(request, "market_rail.html")

    @app.get("/agent-runtime", response_class=HTMLResponse)
    async def agent_runtime(request: FastAPIRequest):
        return templates.TemplateResponse(request, "agent_runtime.html")

    @app.get("/api/intel/classified-markets")
    async def classified_markets_api(
        classification: Optional[str] = Query(default="all"),
        limit: int = Query(default=120, ge=1, le=500),
        min_local_score: Optional[float] = Query(default=None, ge=0.0, le=1.0),
        search: Optional[str] = Query(default=None),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        normalized_classification = str(classification or "all").strip().lower()
        if normalized_classification in {"", "all", "*"}:
            normalized_classification = "all"
        elif normalized_classification not in {"track_now", "track_later", "ignore", "unclassified"}:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported classification filter: {classification}",
            )

        try:
            payload = _fetch_classified_markets_snapshot(
                db_url=db_url,
                classification=normalized_classification,
                limit=limit,
                min_local_score=min_local_score,
                search=search,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build classified markets snapshot: {exc}") from exc
        return payload

    @app.get("/api/intel/market-rail")
    async def market_rail_api(
        classification: Optional[str] = Query(default="track_now"),
        limit: int = Query(default=80, ge=1, le=300),
        channels_per_market: int = Query(default=30, ge=1, le=120),
        search: Optional[str] = Query(default=None),
        mapped_only: bool = Query(default=False),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        normalized_classification = str(classification or "track_now").strip().lower()
        if normalized_classification in {"", "all", "*"}:
            normalized_classification = "all"
        elif normalized_classification not in {"track_now", "track_later", "ignore", "unclassified"}:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported classification filter: {classification}",
            )
        try:
            payload = _fetch_market_rail_snapshot(
                db_url=db_url,
                classification=normalized_classification,
                limit=limit,
                channels_per_market=channels_per_market,
                search=search,
                mapped_only=mapped_only,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build market rail snapshot: {exc}") from exc
        return payload

    @app.post("/api/intel/classified-markets/{market_id}/classification")
    async def set_market_classification(market_id: str, payload: MarketClassificationUpdateRequest):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        normalized_market_id = str(market_id or "").strip()
        if not normalized_market_id:
            raise HTTPException(status_code=422, detail="market_id is required")
        classification = _normalize_classification(payload.classification)
        if classification is None:
            raise HTTPException(
                status_code=422,
                detail="classification must be one of: track_now, track_later, ignore",
            )
        local_score = _resolve_manual_local_score(payload.local_score, classification=classification)
        result = _apply_manual_market_classification(
            db_url=db_url,
            market_id=normalized_market_id,
            classification=classification,
            local_score=local_score,
            note=payload.note,
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Active/open market not found: {normalized_market_id}",
            )
        return result

    @app.post("/api/intel/classified-markets/bulk-source-classification")
    async def bulk_source_classification(payload: SourceBulkClassificationRequest):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        classification = _normalize_classification(payload.classification)
        if classification is None:
            raise HTTPException(
                status_code=422,
                detail="classification must be one of: track_now, track_later, ignore",
            )
        source_urls = [str(item).strip() for item in list(payload.source_urls or []) if str(item).strip()]
        if not source_urls:
            raise HTTPException(status_code=422, detail="source_urls must contain at least one URL")
        local_score = _resolve_manual_local_score(payload.local_score, classification=classification)
        result = _apply_bulk_source_classification(
            db_url=db_url,
            source_urls=source_urls,
            classification=classification,
            local_score=local_score,
            note=payload.note,
            max_slugs_per_source=max(1, min(int(payload.max_slugs_per_source), 500)),
            timeout_seconds=max(5, min(int(payload.timeout_seconds), 60)),
            dry_run=bool(payload.dry_run),
        )
        return result

    @app.get("/api/intel/prompts")
    async def prompt_registry():
        return {
            "generated_at": datetime.now(timezone.utc),
            "items": _build_prompt_registry(),
        }

    @app.get("/api/intel/workspace-overview")
    async def workspace_overview():
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _fetch_workspace_overview_snapshot(db_url=db_url)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build workspace overview: {exc}") from exc
        return payload

    @app.get("/api/intel/pipeline-map")
    async def pipeline_map_snapshot(
        market_limit: int = Query(default=220, ge=1, le=800),
        channel_limit: int = Query(default=180, ge=1, le=500),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _fetch_pipeline_map_snapshot(
                db_url=db_url,
                market_limit=market_limit,
                channel_limit=channel_limit,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build pipeline map snapshot: {exc}") from exc
        return payload

    @app.get("/api/intel/stored-markets")
    async def stored_markets_snapshot(
        group_limit: int = Query(default=160, ge=1, le=500),
        member_limit: int = Query(default=40, ge=1, le=200),
        scope: str = Query(default="all"),
        search: Optional[str] = Query(default=None),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _fetch_stored_markets_snapshot(
                db_url=db_url,
                group_limit=group_limit,
                member_limit=member_limit,
                scope=scope,
                search=search,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build stored markets snapshot: {exc}") from exc
        return payload

    @app.get("/api/intel/saved-channel-map")
    async def saved_channel_map_snapshot(
        source_file: Optional[str] = Query(default=None),
        link_source: str = Query(default="ai_handpicked_batch_v1"),
        include_unlinked: bool = Query(default=True),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _fetch_saved_channel_map_snapshot(
                db_url=db_url,
                source_file=source_file,
                link_source=link_source,
                include_unlinked=include_unlinked,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build saved channel map snapshot: {exc}") from exc
        return payload

    @app.get("/api/intel/telegram-live")
    async def telegram_live_snapshot(
        source_file: Optional[str] = Query(default=None),
        link_source: str = Query(default="ai_handpicked_batch_v1"),
        message_limit: int = Query(default=80, ge=1, le=300),
        event_limit: int = Query(default=30, ge=1, le=120),
        activation_limit: int = Query(default=20, ge=1, le=80),
        agent_name: str = Query(default="telegram-realtime-listener"),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _fetch_telegram_live_snapshot(
                db_url=db_url,
                source_file=source_file,
                link_source=link_source,
                message_limit=message_limit,
                event_limit=event_limit,
                activation_limit=activation_limit,
                agent_name=agent_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build telegram live snapshot: {exc}") from exc
        return payload

    @app.get("/api/intel/handpicked-review")
    async def handpicked_review_snapshot(
        status: str = Query(default="review"),
        limit: int = Query(default=140, ge=1, le=500),
        search: Optional[str] = Query(default=None),
        source_file: Optional[str] = Query(default=None),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _fetch_handpicked_review_snapshot(
                db_url=db_url,
                status=status,
                limit=limit,
                search=search,
                source_file=source_file,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build handpicked review snapshot: {exc}") from exc
        return payload

    @app.get("/api/intel/handpicked-review/options")
    async def handpicked_review_options(
        search: str = Query(default=""),
        limit: int = Query(default=24, ge=1, le=100),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _search_handpicked_resolution_options(
                db_url=db_url,
                search=search,
                limit=limit,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to search handpicked resolution options: {exc}") from exc
        return payload

    @app.post("/api/intel/handpicked-review/{target_id}")
    async def update_handpicked_review_target(target_id: int, payload: HandpickedTargetUpdateRequest):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            result = _apply_handpicked_target_update(
                db_url=db_url,
                target_id=target_id,
                match_status=payload.match_status,
                matched_group_slug=payload.matched_group_slug,
                matched_market_id=payload.matched_market_id,
                note=payload.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to update handpicked review target: {exc}") from exc
        if result is None:
            raise HTTPException(status_code=404, detail=f"Handpicked target not found: {target_id}")
        return result

    @app.get("/api/intel/agent-runtime")
    async def agent_runtime_snapshot(
        agent_name: str = Query(default="telegram-market-agent"),
        event_limit: int = Query(default=80, ge=1, le=500),
    ):
        db_url = _resolve_db_url()
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )
        try:
            payload = _fetch_agent_runtime_snapshot(
                db_url=db_url,
                agent_name=str(agent_name or "telegram-market-agent").strip() or "telegram-market-agent",
                event_limit=event_limit,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build agent runtime snapshot: {exc}") from exc
        return payload

    @app.get("/api/intel/graph")
    async def intel_graph(
        market_limit: int = Query(default=80, ge=1, le=500),
        channel_limit: int = Query(default=220, ge=1, le=1000),
        edge_limit: int = Query(default=3000, ge=1, le=15000),
        track_now_only: bool = Query(default=True),
        min_channel_members: Optional[int] = Query(default=None, ge=0, le=10000000),
        min_channel_relevance: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    ):
        config = PolymarketConfig.from_env()
        db_url = config.direct_url or config.database_url
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )

        effective_min_channel_members = (
            config.telegram_min_channel_members
            if min_channel_members is None
            else min_channel_members
        )
        effective_min_channel_relevance = (
            config.telegram_min_channel_relevance_score
            if min_channel_relevance is None
            else min_channel_relevance
        )

        try:
            payload = _fetch_graph_snapshot(
                db_url=db_url,
                market_limit=market_limit,
                channel_limit=channel_limit,
                edge_limit=edge_limit,
                track_now_only=track_now_only,
                min_channel_members=effective_min_channel_members,
                min_channel_relevance=effective_min_channel_relevance,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to build graph snapshot: {exc}") from exc

        return payload

    async def _run_telegram_backtest(
        *,
        market_ref: str,
        target_channels: int,
        query_results_limit: int,
        max_queries: int,
        similar_seed_channels: int,
        similar_per_seed: int,
        min_channel_members: Optional[float],
        min_channel_relevance: Optional[float],
        planner_system_prompt: str | None = None,
        planner_user_prompt: str | None = None,
        use_prompt_override: bool = False,
        local_system_prompt: str | None = None,
        local_user_prompt: str | None = None,
        use_local_prompt_override: bool = False,
        reviewer_system_prompt: str | None = None,
        reviewer_user_prompt: str | None = None,
        use_reviewer_prompt_override: bool = False,
        max_review_channels: int = 20,
        review_message_limit: int = 10,
    ) -> dict[str, Any]:
        config = PolymarketConfig.from_env()
        db_url = config.direct_url or config.database_url
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )

        normalized_ref = _normalize_market_ref(market_ref)
        repository = MarketIntelRepository(db_url)
        market = repository.get_market_by_ref(normalized_ref)
        if not market:
            market = _fetch_market_for_backtest(config, normalized_ref)
        if not market:
            raise HTTPException(
                status_code=404,
                detail=f"Active market not found for reference: {normalized_ref}",
            )

        classifier = LocalMarketRuleClassifier()
        if use_local_prompt_override and classifier.runtime_mode != "ai":
            raise HTTPException(
                status_code=503,
                detail="Local classifier prompt editing requires AI runtime. Add OPENAI_API_KEY and rerun.",
            )
        local_review = classifier.classify_with_trace_overrides(
            market,
            system_prompt_override=local_system_prompt if use_local_prompt_override else None,
            user_prompt_override=local_user_prompt if use_local_prompt_override else None,
        )
        local_result = local_review.get("result") or {}
        market = {
            **market,
            "classification": str(local_result.get("classification") or market.get("classification") or "unknown"),
            "analysis_local_score": local_result.get(
                "local_score",
                market.get("analysis_local_score", market.get("local_score")),
            ),
            "analysis_reason_json": local_result.get("reason_json") or market.get("analysis_reason_json") or {},
        }

        effective_min_channel_members = (
            config.telegram_min_channel_members
            if min_channel_members is None
            else int(min_channel_members)
        )
        effective_min_channel_relevance = (
            config.telegram_min_channel_relevance_score
            if min_channel_relevance is None
            else float(min_channel_relevance)
        )

        if shared_discovery_settings is None or shared_tdlib_client is None:
            detail = "Telegram discovery environment is invalid."
            if shared_tdlib_init_error:
                detail = f"{detail} {shared_tdlib_init_error}"
            raise HTTPException(
                status_code=503,
                detail=detail,
            )

        planner = MarketSearchPlanner()
        reviewer = BacktestChannelReviewer()
        if use_prompt_override and planner.runtime_mode != "ai":
            raise HTTPException(
                status_code=503,
                detail="Planner prompt editing requires AI runtime. Add OPENAI_API_KEY and rerun.",
            )
        if use_reviewer_prompt_override and reviewer.runtime_mode != "ai":
            raise HTTPException(
                status_code=503,
                detail="Channel reviewer prompt editing requires AI runtime. Add OPENAI_API_KEY and rerun.",
            )

        nonlocal backtest_lock
        if backtest_lock is None:
            backtest_lock = asyncio.Lock()

        async with backtest_lock:
            service = MarketTelegramDiscoveryService(
                repository=repository,
                tdlib_client=shared_tdlib_client,
                planner=planner,
                channel_reviewer=reviewer,
            )
            try:
                payload = await service.backtest_market(
                    market,
                    target_channels_per_market=target_channels,
                    query_results_limit=query_results_limit,
                    max_queries_per_market=max_queries,
                    similar_seed_channels=similar_seed_channels,
                    similar_per_seed=similar_per_seed,
                    min_channel_members=effective_min_channel_members,
                    min_channel_relevance_score=effective_min_channel_relevance,
                    planner_system_prompt_override=planner_system_prompt if use_prompt_override else None,
                    planner_user_prompt_override=planner_user_prompt if use_prompt_override else None,
                    reviewer_system_prompt_override=reviewer_system_prompt if use_reviewer_prompt_override else None,
                    reviewer_user_prompt_override=reviewer_user_prompt if use_reviewer_prompt_override else None,
                    include_channel_ai_review=True,
                    max_review_channels=max(1, min(int(max_review_channels), 50)),
                    review_message_limit=max(1, min(int(review_message_limit), 20)),
                    use_relevance_scoring=False,
                )
            except TDLibAuthRequiredError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Telegram session is not ready: {exc}",
                ) from exc
            except TDLibRequestError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Telegram backtest failed: {exc}",
                ) from exc

        payload["local_market_review"] = local_review
        payload["meta"] = {
            "generated_at": datetime.now(timezone.utc),
            "market_ref": normalized_ref,
            "target_channels": int(target_channels),
            "query_results_limit": int(query_results_limit),
            "max_queries": int(max_queries),
            "similar_seed_channels": int(similar_seed_channels),
            "similar_per_seed": int(similar_per_seed),
            "min_channel_members": int(effective_min_channel_members),
            "min_channel_relevance": float(effective_min_channel_relevance),
            "engine": "telegram_discovery_backtest_v2",
            "planner_runtime_mode": planner.runtime_mode,
            "planner_prompt_editable": planner.runtime_mode == "ai",
            "use_prompt_override": bool(use_prompt_override),
            "local_classifier_runtime_mode": classifier.runtime_mode,
            "local_prompt_editable": classifier.runtime_mode == "ai",
            "use_local_prompt_override": bool(use_local_prompt_override),
            "reviewer_runtime_mode": reviewer.runtime_mode,
            "reviewer_prompt_editable": reviewer.runtime_mode == "ai",
            "use_reviewer_prompt_override": bool(use_reviewer_prompt_override),
            "max_review_channels": max(1, min(int(max_review_channels), 50)),
            "review_message_limit": max(1, min(int(review_message_limit), 20)),
        }

        try:
            run_id = repository.save_telegram_backtest_run(
                market_ref=normalized_ref,
                payload=payload,
                params_json=payload.get("meta") if isinstance(payload, dict) else {},
                summary_json=payload.get("summary") if isinstance(payload, dict) else {},
            )
            payload["meta"]["backtest_run_id"] = int(run_id)
            payload["meta"]["backtest_saved"] = True
        except Exception as exc:
            payload["meta"]["backtest_run_id"] = None
            payload["meta"]["backtest_saved"] = False
            payload["meta"]["backtest_save_error"] = str(exc)
        return payload

    @app.get("/api/intel/telegram-backtest")
    async def telegram_backtest(
        market_ref: str = Query(..., min_length=1),
        target_channels: int = Query(default=25, ge=1, le=100),
        query_results_limit: int = Query(default=20, ge=1, le=50),
        max_queries: int = Query(default=6, ge=1, le=12),
        similar_seed_channels: int = Query(default=3, ge=0, le=10),
        similar_per_seed: int = Query(default=10, ge=0, le=25),
        min_channel_members: Optional[int] = Query(default=None, ge=0, le=10000000),
        min_channel_relevance: Optional[float] = Query(default=None, ge=0.0, le=1.0),
        max_review_channels: int = Query(default=20, ge=1, le=50),
        review_message_limit: int = Query(default=10, ge=1, le=20),
    ):
        return await _run_telegram_backtest(
            market_ref=market_ref,
            target_channels=target_channels,
            query_results_limit=query_results_limit,
            max_queries=max_queries,
            similar_seed_channels=similar_seed_channels,
            similar_per_seed=similar_per_seed,
            min_channel_members=min_channel_members,
            min_channel_relevance=min_channel_relevance,
            max_review_channels=max_review_channels,
            review_message_limit=review_message_limit,
        )

    @app.post("/api/intel/telegram-backtest")
    async def telegram_backtest_post(request: TelegramBacktestRequest):
        return await _run_telegram_backtest(
            market_ref=request.market_ref,
            target_channels=max(1, min(int(request.target_channels), 100)),
            query_results_limit=max(1, min(int(request.query_results_limit), 50)),
            max_queries=max(1, min(int(request.max_queries), 12)),
            similar_seed_channels=max(0, min(int(request.similar_seed_channels), 10)),
            similar_per_seed=max(0, min(int(request.similar_per_seed), 25)),
            min_channel_members=request.min_channel_members,
            min_channel_relevance=request.min_channel_relevance,
            planner_system_prompt=request.planner_system_prompt,
            planner_user_prompt=request.planner_user_prompt,
            use_prompt_override=bool(request.use_prompt_override),
            local_system_prompt=request.local_system_prompt,
            local_user_prompt=request.local_user_prompt,
            use_local_prompt_override=bool(request.use_local_prompt_override),
            reviewer_system_prompt=request.reviewer_system_prompt,
            reviewer_user_prompt=request.reviewer_user_prompt,
            use_reviewer_prompt_override=bool(request.use_reviewer_prompt_override),
            max_review_channels=max(1, min(int(request.max_review_channels), 50)),
            review_message_limit=max(1, min(int(request.review_message_limit), 20)),
        )

    @app.get("/api/intel/telegram-backtest/runs")
    async def telegram_backtest_runs(
        limit: int = Query(default=20, ge=1, le=200),
        market_ref: Optional[str] = Query(default=None),
    ):
        db_url = _resolve_db_url()
        repository = MarketIntelRepository(db_url)
        items = repository.list_telegram_backtest_runs(
            limit=limit,
            market_ref=market_ref,
        )
        return {"items": items, "count": len(items)}

    @app.get("/api/intel/telegram-backtest/runs/{run_id}")
    async def telegram_backtest_run_detail(run_id: int):
        db_url = _resolve_db_url()
        repository = MarketIntelRepository(db_url)
        row = repository.get_telegram_backtest_run(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found")
        payload = row.get("payload_json")
        if isinstance(payload, dict):
            payload = {
                **payload,
                "run_record": {
                    "run_id": row.get("run_id"),
                    "created_at": row.get("created_at"),
                    "market_ref": row.get("market_ref"),
                    "market_id": row.get("market_id"),
                    "market_slug": row.get("market_slug"),
                },
            }
        return payload

    @app.get("/api/intel/telegram-serp-preview")
    async def telegram_serp_preview(
        market_ref: str = Query(..., min_length=1),
        max_queries: int = Query(default=12, ge=1, le=40),
        results_per_query: int = Query(default=8, ge=1, le=20),
    ):
        config = PolymarketConfig.from_env()
        db_url = config.direct_url or config.database_url
        if not db_url:
            raise HTTPException(
                status_code=503,
                detail="No database URL found. Set SUPABASE_DB_URL/DATABASE_URL (or direct URL) in environment.",
            )

        normalized_ref = _normalize_market_ref(market_ref)
        repository = MarketIntelRepository(db_url)
        market = repository.get_market_by_ref(normalized_ref)
        if not market:
            market = _fetch_market_for_backtest(config, normalized_ref)
        if not market:
            raise HTTPException(
                status_code=404,
                detail=f"Active market not found for reference: {normalized_ref}",
            )

        planner = MarketSearchPlanner()
        plan = planner.build_query_plan(
            market,
            max_queries=max(1, min(int(max_queries), 40)),
            include_debug=True,
        )
        google_queries = [
            " ".join(str(query).split()).strip()
            for query in list(plan.get("google_queries") or [])
            if " ".join(str(query).split()).strip()
        ][: max(1, min(int(max_queries), 40))]

        serp_client = GoogleSerpClient.from_config(config)
        if not serp_client.enabled:
            return {
                "generated_at": datetime.now(timezone.utc),
                "market_ref": normalized_ref,
                "market": {
                    "market_id": market.get("market_id"),
                    "slug": market.get("slug"),
                    "question": market.get("question"),
                },
                "planner_runtime_mode": planner.runtime_mode,
                "google_queries": google_queries,
                "serp_enabled": False,
                "provider": serp_client.provider,
                "error": "SERP is disabled. Set SERPER_API_KEY or SERPAPI_API_KEY in .env.",
                "query_runs": [],
                "unique_handles": [],
                "unique_links": [],
            }

        query_runs: list[dict[str, Any]] = []
        unique_handles_seen: set[str] = set()
        unique_handles: list[str] = []
        unique_links_seen: set[str] = set()
        unique_links: list[str] = []
        failed_queries = 0

        for query in google_queries:
            try:
                run = serp_client.search_tme(
                    query,
                    max_results=max(1, min(int(results_per_query), 20)),
                )
                error_message = None
            except GoogleSerpUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except GoogleSerpError as exc:
                failed_queries += 1
                run = None
                error_message = str(exc)

            if run is not None:
                for handle in run.handles:
                    key = handle.lower()
                    if key in unique_handles_seen:
                        continue
                    unique_handles_seen.add(key)
                    unique_handles.append(handle)
                for link in run.links:
                    key = link.lower()
                    if key in unique_links_seen:
                        continue
                    unique_links_seen.add(key)
                    unique_links.append(link)

            query_runs.append(
                {
                    "query": query,
                    "status": "ok" if run is not None else "error",
                    "provider": run.provider if run is not None else serp_client.provider,
                    "raw_result_count": int(run.raw_count) if run is not None else 0,
                    "link_count": int(len(run.links)) if run is not None else 0,
                    "handle_count": int(len(run.handles)) if run is not None else 0,
                    "handles": list(run.handles) if run is not None else [],
                    "links": list(run.links) if run is not None else [],
                    "error": error_message,
                }
            )

        return {
            "generated_at": datetime.now(timezone.utc),
            "market_ref": normalized_ref,
            "market": {
                "market_id": market.get("market_id"),
                "slug": market.get("slug"),
                "question": market.get("question"),
            },
            "planner_runtime_mode": planner.runtime_mode,
            "serp_enabled": True,
            "provider": serp_client.provider,
            "google_query_count": len(google_queries),
            "failed_query_count": int(failed_queries),
            "google_queries": google_queries,
            "query_runs": query_runs,
            "unique_handles": unique_handles,
            "unique_links": unique_links,
            "summary": {
                "queries_run": len(query_runs),
                "queries_ok": len(query_runs) - int(failed_queries),
                "queries_failed": int(failed_queries),
                "unique_handles": len(unique_handles),
                "unique_links": len(unique_links),
            },
        }
        return row

    return app


app = create_app()


def _resolve_db_url() -> str:
    config = PolymarketConfig.from_env()
    return config.direct_url or config.database_url


def _pipeline_market_scope(market: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            str(market.get("event_slug") or ""),
            str(market.get("slug") or ""),
            str(market.get("question") or ""),
            str(market.get("description") or ""),
            str(market.get("market_context") or ""),
        ]
    ).lower()

    if any(token in haystack for token in ("israel", "idf", "hamas", "gaza", "lebanon", "jerusalem")):
        if "iran" in haystack:
            return "Israel / Iran"
        if "gaza" in haystack or "hamas" in haystack:
            return "Gaza / Israel"
        return "Israel"
    if any(token in haystack for token in ("iran", "khamenei", "pahlavi", "tehran", "hormuz")):
        return "Iran"
    if any(token in haystack for token in ("ukraine", "russia", "zelensky", "putin")):
        return "Ukraine"
    if any(token in haystack for token in ("venezuela", "maduro", "caracas")):
        return "Venezuela"
    if any(token in haystack for token in ("oil", "crude", "hormuz", "ship", "shipping")):
        return "Oil"
    return "Other"


def _normalize_classification(value: str | None) -> str | None:
    key = str(value or "").strip().lower()
    if key in {"track_now", "track_later", "ignore"}:
        return key
    return None


def _resolve_manual_local_score(value: float | None, *, classification: str) -> float:
    if value is not None:
        try:
            parsed = float(value)
            if parsed < 0.0:
                return 0.0
            if parsed > 1.0:
                return 1.0
            return parsed
        except (TypeError, ValueError):
            pass
    if classification == "track_now":
        return 0.9
    if classification == "track_later":
        return 0.5
    return 0.1


def _apply_manual_market_classification(
    *,
    db_url: str,
    market_id: str,
    classification: str,
    local_score: float,
    note: str | None,
) -> dict[str, Any] | None:
    reason_json = {
        "source": "manual_swipe",
        "classification": classification,
        "local_score": float(local_score),
        "note": str(note or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT market_id, rules_hash, slug, question
                FROM markets
                WHERE market_id = %s
                  AND active = TRUE
                  AND closed = FALSE
                LIMIT 1;
                """,
                (market_id,),
            )
            market = cur.fetchone()
            if market is None:
                return None
            cur.execute(
                """
                INSERT INTO market_analysis (
                  market_id, analyzed_at, analysis_version, prompt_version, rules_hash,
                  is_local, local_score, classification, reason_json, status
                ) VALUES (
                  %s, NOW(), 'manual_swipe_v1', 'manual_swipe_v1', %s,
                  %s, %s, %s, %s::jsonb, 'active'
                );
                """,
                (
                    market_id,
                    market.get("rules_hash"),
                    classification == "track_now",
                    float(local_score),
                    classification,
                    json.dumps(reason_json, ensure_ascii=False),
                ),
            )
            cur.execute(
                """
                UPDATE markets
                SET
                  is_local_candidate = %s,
                  local_score = %s,
                  local_reason_json = %s::jsonb,
                  updated_at = NOW()
                WHERE market_id = %s;
                """,
                (
                    classification == "track_now",
                    float(local_score),
                    json.dumps(reason_json, ensure_ascii=False),
                    market_id,
                ),
            )
        conn.commit()
    return {
        "ok": True,
        "market_id": market_id,
        "classification": classification,
        "local_score": float(local_score),
        "note": str(note or "").strip(),
    }


def _apply_bulk_source_classification(
    *,
    db_url: str,
    source_urls: list[str],
    classification: str,
    local_score: float,
    note: str | None,
    max_slugs_per_source: int,
    timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    unique_urls = _dedupe_preserve(source_urls)
    slug_map: dict[str, list[str]] = {}
    all_slugs: list[str] = []
    for source_url in unique_urls:
        source_slugs = _extract_event_slugs_from_source_url(
            source_url,
            max_slugs_per_source=max_slugs_per_source,
            timeout_seconds=timeout_seconds,
        )
        slug_map[source_url] = source_slugs
        all_slugs.extend(source_slugs)
    event_slugs = _dedupe_preserve(all_slugs)
    if not event_slugs:
        return {
            "ok": True,
            "dry_run": bool(dry_run),
            "source_urls": unique_urls,
            "event_slugs": [],
            "updated_markets": 0,
            "classification": classification,
            "local_score": float(local_score),
            "note": str(note or "").strip(),
            "source_slug_counts": {url: len(slugs) for url, slugs in slug_map.items()},
        }

    reason_json = {
        "source": "manual_source_bulk",
        "classification": classification,
        "local_score": float(local_score),
        "note": str(note or "").strip(),
        "source_urls": unique_urls,
        "event_slugs_count": len(event_slugs),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    updated_markets = 0
    matched_markets = 0
    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::INT
                FROM markets
                WHERE active = TRUE
                  AND closed = FALSE
                  AND event_slug = ANY(%s);
                """,
                (event_slugs,),
            )
            matched_markets = int(cur.fetchone()[0] or 0)
            if not dry_run:
                cur.execute(
                    """
                    INSERT INTO market_analysis (
                      market_id, analyzed_at, analysis_version, prompt_version, rules_hash,
                      is_local, local_score, classification, reason_json, status
                    )
                    SELECT
                      m.market_id,
                      NOW(),
                      'manual_source_bulk_v1',
                      'manual_source_bulk_v1',
                      m.rules_hash,
                      %s,
                      %s,
                      %s,
                      %s::jsonb,
                      'active'
                    FROM markets m
                    WHERE m.active = TRUE
                      AND m.closed = FALSE
                      AND m.event_slug = ANY(%s);
                    """,
                    (
                        classification == "track_now",
                        float(local_score),
                        classification,
                        json.dumps(reason_json, ensure_ascii=False),
                        event_slugs,
                    ),
                )
                cur.execute(
                    """
                    UPDATE markets
                    SET
                      is_local_candidate = %s,
                      local_score = %s,
                      local_reason_json = %s::jsonb,
                      updated_at = NOW()
                    WHERE active = TRUE
                      AND closed = FALSE
                      AND event_slug = ANY(%s);
                    """,
                    (
                        classification == "track_now",
                        float(local_score),
                        json.dumps(reason_json, ensure_ascii=False),
                        event_slugs,
                    ),
                )
                updated_markets = int(cur.rowcount or 0)
        if not dry_run:
            conn.commit()
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "source_urls": unique_urls,
        "event_slugs": event_slugs,
        "source_slug_counts": {url: len(slugs) for url, slugs in slug_map.items()},
        "matched_markets": matched_markets,
        "updated_markets": updated_markets if not dry_run else matched_markets,
        "classification": classification,
        "local_score": float(local_score),
        "note": str(note or "").strip(),
    }


def _extract_event_slugs_from_source_url(
    source_url: str,
    *,
    max_slugs_per_source: int,
    timeout_seconds: int,
) -> list[str]:
    direct_slug = _extract_direct_event_slug(source_url)
    if direct_slug:
        return [direct_slug]
    html = _fetch_source_html(source_url, timeout_seconds=timeout_seconds)
    slugs = [item.lower().strip() for item in _EVENT_SLUG_RE.findall(html)]
    return _dedupe_preserve(slugs)[: max(1, min(int(max_slugs_per_source), 500))]


def _extract_direct_event_slug(source_url: str) -> str | None:
    parsed = urlparse(str(source_url or "").strip())
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    if parts[0].lower() != "event":
        return None
    slug = parts[1].strip().lower()
    if re.fullmatch(r"[a-z0-9-]+", slug):
        return slug
    return None


def _fetch_source_html(source_url: str, *, timeout_seconds: int) -> str:
    request = UrlRequest(
        url=source_url,
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
    out: list[str] = []
    for item in items:
        key = str(item or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _normalize_market_ref(raw_value: str) -> str:
    ref = str(raw_value or "").strip()
    if not ref:
        return ""

    if "/event/" in ref:
        ref = ref.split("/event/", 1)[1]
    ref = ref.split("?", 1)[0]
    ref = ref.split("#", 1)[0]
    return ref.strip().strip("/")


def _fetch_market_for_backtest(config: PolymarketConfig, normalized_ref: str) -> dict[str, Any] | None:
    gamma = GammaMarketsClient(config)
    try:
        event = gamma.get_event_by_slug(normalized_ref)
    except HttpJsonError:
        event = None
    if isinstance(event, dict):
        primary_market = _select_primary_event_market(event)
        if primary_market is not None:
            normalized = _normalize_gamma_market_for_backtest(primary_market)
            event_id = str(event.get("id") or "")
            event_slug = str(event.get("slug") or normalized_ref)
            child_markets = [item for item in list(event.get("markets") or []) if isinstance(item, dict)]
            context_lines = _event_market_context_lines(event)
            child_ids = [
                str(item.get("id") or "")
                for item in child_markets
                if str(item.get("id") or "")
            ]
            combined_context = "\n".join(
                [
                    str(normalized.get("market_context") or "").strip(),
                    context_lines,
                ]
            ).strip()
            return {
                **normalized,
                "market_context": combined_context,
                "source_kind": "gamma_event_primary_market",
                "source_event_id": event_id,
                "source_event_slug": event_slug,
                "source_market_count": len(child_markets),
                "source_child_market_ids": child_ids,
                "source_primary_market_id": str(normalized.get("market_id") or ""),
            }
        return _normalize_gamma_event_for_backtest(event)

    try:
        market = gamma.get_market_by_slug(normalized_ref)
    except HttpJsonError:
        market = None
    if isinstance(market, dict):
        return _normalize_gamma_market_for_backtest(market)

    if normalized_ref.isdigit():
        try:
            market = gamma.get_market_by_id(normalized_ref)
        except HttpJsonError:
            market = None
        if isinstance(market, dict):
            return _normalize_gamma_market_for_backtest(market)

    return None


def _normalize_gamma_event_for_backtest(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("id") or "")
    slug = str(event.get("slug") or event.get("ticker") or event_id)
    title = str(event.get("title") or event.get("question") or slug.replace("-", " "))
    description = str(event.get("description") or "")
    child_markets = [item for item in list(event.get("markets") or []) if isinstance(item, dict)]
    active_children = [
        item
        for item in child_markets
        if bool(item.get("active", False)) and not bool(item.get("closed", False))
    ]
    preview_children = active_children[:5] if active_children else child_markets[:5]
    child_context_lines = [
        f"- {str(item.get('question') or item.get('groupItemTitle') or item.get('slug') or '').strip()}"
        for item in preview_children
        if str(item.get("question") or item.get("groupItemTitle") or item.get("slug") or "").strip()
    ]
    market_context_parts = []
    resolution_source = str(event.get("resolutionSource") or "").strip()
    if resolution_source:
        market_context_parts.append(f"Resolution source: {resolution_source}")
    if child_context_lines:
        market_context_parts.append(
            "Representative active child markets:\n" + "\n".join(child_context_lines)
        )
    return {
        "market_id": f"event:{event_id or slug}",
        "slug": slug,
        "question": title,
        "description": description,
        "rules_text": description,
        "market_context": "\n\n".join(part for part in market_context_parts if part),
        "market_archetype": _infer_market_archetype_from_event(event, child_markets),
        "active": bool(event.get("active", False)),
        "closed": bool(event.get("closed", False)),
        "outcomes": [],
        "classification": "backtest_event",
        "analysis_reason_json": {},
        "analysis_local_score": None,
        "local_score": None,
        "mapped_channels": 0,
        "source_kind": "gamma_event",
        "source_event_id": event_id,
        "source_market_count": len(child_markets),
    }


def _select_primary_event_market(event: dict[str, Any]) -> dict[str, Any] | None:
    child_markets = [item for item in list(event.get("markets") or []) if isinstance(item, dict)]
    if not child_markets:
        return None
    active_children = [
        item
        for item in child_markets
        if bool(item.get("active", False)) and not bool(item.get("closed", False))
    ]
    pool = active_children if active_children else child_markets
    if not pool:
        return None

    def _score(item: dict[str, Any]) -> tuple[float, float]:
        volume = _to_float(item.get("volumeNum"), fallback=_to_float(item.get("volume"), fallback=0.0))
        liquidity = _to_float(item.get("liquidityNum"), fallback=_to_float(item.get("liquidity"), fallback=0.0))
        return volume, liquidity

    ranked = sorted(pool, key=_score, reverse=True)
    return ranked[0] if ranked else None


def _event_market_context_lines(event: dict[str, Any]) -> str:
    child_markets = [item for item in list(event.get("markets") or []) if isinstance(item, dict)]
    active_children = [
        item
        for item in child_markets
        if bool(item.get("active", False)) and not bool(item.get("closed", False))
    ]
    preview_children = active_children[:5] if active_children else child_markets[:5]
    child_context_lines = [
        f"- {str(item.get('question') or item.get('groupItemTitle') or item.get('slug') or '').strip()}"
        for item in preview_children
        if str(item.get("question") or item.get("groupItemTitle") or item.get("slug") or "").strip()
    ]
    market_context_parts = []
    resolution_source = str(event.get("resolutionSource") or "").strip()
    if resolution_source:
        market_context_parts.append(f"Resolution source: {resolution_source}")
    if child_context_lines:
        market_context_parts.append(
            "Representative active child markets:\n" + "\n".join(child_context_lines)
        )
    return "\n\n".join(part for part in market_context_parts if part)


def _normalize_gamma_market_for_backtest(market: dict[str, Any]) -> dict[str, Any]:
    market_id = str(market.get("id") or "")
    slug = str(market.get("slug") or market_id)
    description = str(market.get("description") or "")
    group_title = str(market.get("groupItemTitle") or "").strip()
    market_context_parts = []
    if group_title:
        market_context_parts.append(f"Outcome group / schedule label: {group_title}")
    category = str(market.get("category") or "").strip()
    if category:
        market_context_parts.append(f"Category: {category}")
    return {
        "market_id": market_id or slug,
        "slug": slug,
        "question": str(market.get("question") or slug.replace("-", " ")),
        "description": description,
        "rules_text": description,
        "market_context": "\n".join(market_context_parts),
        "market_archetype": _infer_market_archetype_from_market(market),
        "active": bool(market.get("active", False)),
        "closed": bool(market.get("closed", False)),
        "outcomes": _parse_market_outcomes(market),
        "classification": "backtest_market",
        "analysis_reason_json": {},
        "analysis_local_score": None,
        "local_score": None,
        "mapped_channels": 0,
        "source_kind": "gamma_market",
    }


def _infer_market_archetype_from_event(event: dict[str, Any], child_markets: list[dict[str, Any]]) -> str:
    if len(child_markets) > 1:
        return "event_group"
    if child_markets:
        return _infer_market_archetype_from_market(child_markets[0])
    if bool(event.get("showAllOutcomes")):
        return "categorical_event"
    return "binary_event"


def _infer_market_archetype_from_market(market: dict[str, Any]) -> str:
    outcomes = market.get("outcomes")
    if isinstance(outcomes, str):
        outcomes_count = outcomes.count(",") + 1 if outcomes.strip().startswith("[") else 0
    elif isinstance(outcomes, list):
        outcomes_count = len(outcomes)
    else:
        outcomes_count = 0
    if outcomes_count > 2:
        return "categorical"
    return "binary"


def _parse_market_outcomes(market: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes_raw = market.get("outcomes")
    prices_raw = market.get("outcomePrices")
    outcomes: list[str]
    prices: list[Any]
    if isinstance(outcomes_raw, str):
        try:
            parsed = json.loads(outcomes_raw)
            outcomes = parsed if isinstance(parsed, list) else []
        except Exception:
            outcomes = []
    elif isinstance(outcomes_raw, list):
        outcomes = [str(item) for item in outcomes_raw]
    else:
        outcomes = []

    if isinstance(prices_raw, str):
        try:
            parsed = json.loads(prices_raw)
            prices = parsed if isinstance(parsed, list) else []
        except Exception:
            prices = []
    elif isinstance(prices_raw, list):
        prices = list(prices_raw)
    else:
        prices = []

    output = []
    for idx, label in enumerate(outcomes):
        probability = None
        if idx < len(prices):
            try:
                probability = float(prices[idx])
            except (TypeError, ValueError):
                probability = None
        output.append(
            {
                "outcome_index": idx,
                "outcome_label": label,
                "probability": probability,
            }
        )
    return output


def _to_float(value: Any, *, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _build_prompt_registry() -> list[dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[2]

    classifier = LocalMarketRuleClassifier()
    planner = MarketSearchPlanner()
    matcher = MarketMessageMatcher()

    prompt_specs = [
        {
            "id": "market-local-classifier",
            "title": "Market Local Classifier",
            "scope": "Polymarket market analysis",
            "status": "template + live runtime",
            "runtime_version": classifier.prompt_version,
            "runtime_engine": classifier.analysis_version,
            "runtime_mode": getattr(classifier, "runtime_mode", "heuristic_legacy"),
            "summary": "Decides whether a market has local-information edge and which languages/regions to prioritize.",
            "template_path": repo_root / "configs/prompts/local_market/system.txt",
            "runtime_source_path": repo_root / "src/polymarket/market_analysis.py",
        },
        {
            "id": "telegram-query-planner",
            "title": "Telegram Query Planner",
            "scope": "Telegram discovery stage 1",
            "status": "template + live runtime",
            "runtime_version": planner.prompt_version,
            "runtime_engine": planner.planner_version,
            "runtime_mode": getattr(planner, "runtime_mode", "heuristic_legacy"),
            "summary": "Generates Telegram search queries from market question, rules, slug, and region hints.",
            "template_path": repo_root / "configs/prompts/telegram_query_planner/system.txt",
            "runtime_source_path": repo_root / "src/polymarket/telegram_pipeline.py",
        },
        {
            "id": "telegram-channel-relevance",
            "title": "Telegram Channel Relevance",
            "scope": "Telegram discovery stage 2",
            "status": "template + live heuristic",
            "runtime_version": "telegram-channel-relevance-v1",
            "runtime_engine": "heuristic_relevance_v1",
            "runtime_mode": "heuristic",
            "summary": "Filters Telegram channels against market entities, phrases, scripts, and noise penalties.",
            "template_path": repo_root / "docs/polymarket/TELEGRAM_CHANNEL_RELEVANCE_PROMPT_TEMPLATE.md",
            "runtime_source_path": repo_root / "src/polymarket/channel_relevance.py",
        },
        {
            "id": "telegram-message-matcher",
            "title": "Telegram Message Matcher",
            "scope": "Telegram listener stage",
            "status": "template + live heuristic",
            "runtime_version": "telegram-message-match-v1",
            "runtime_engine": matcher.matcher_version,
            "runtime_mode": "heuristic",
            "summary": "Evaluates whether a Telegram message should count as a match for one market.",
            "template_path": repo_root / "docs/polymarket/TELEGRAM_MESSAGE_MATCH_PROMPT_TEMPLATE.md",
            "runtime_source_path": repo_root / "src/polymarket/telegram_pipeline.py",
        },
        {
            "id": "telegram-backtest-review",
            "title": "Telegram Backtest Review Layer",
            "scope": "Telegram discovery stage 3 (backtest)",
            "status": "template + live runtime",
            "runtime_version": "telegram-channel-review-v1-ai",
            "runtime_engine": "ai_channel_reviewer_v1",
            "runtime_mode": "ai_or_heuristic_fallback",
            "summary": "Reviews each candidate Telegram channel with market context and recent messages before final keep/drop in backtest.",
            "template_path": repo_root / "configs/prompts/telegram_channel_reviewer/system.txt",
            "runtime_source_path": repo_root / "src/polymarket/telegram_pipeline.py",
        },
    ]

    items: list[dict[str, Any]] = []
    for spec in prompt_specs:
        template_path = spec.get("template_path")
        runtime_source_path = spec.get("runtime_source_path")
        template_content = _safe_read_text(template_path) if template_path else ""
        runtime_excerpt = _read_runtime_excerpt(runtime_source_path) if runtime_source_path else ""
        items.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "scope": spec["scope"],
                "status": spec["status"],
                "runtime_version": spec["runtime_version"],
                "runtime_engine": spec["runtime_engine"],
                "runtime_mode": spec["runtime_mode"],
                "summary": spec["summary"],
                "template_path": _relative_path(template_path, repo_root) if template_path else None,
                "runtime_source_path": _relative_path(runtime_source_path, repo_root) if runtime_source_path else None,
                "template_available": bool(template_content),
                "template_content": template_content,
                "runtime_excerpt": runtime_excerpt,
            }
        )
    return items


def _safe_read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_runtime_excerpt(path: Path | None, *, max_lines: int = 80) -> str:
    if path is None or not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[:max_lines])


def _relative_path(path: Path | None, repo_root: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _fetch_classified_markets_snapshot(
    *,
    db_url: str,
    classification: str,
    limit: int,
    min_local_score: float | None,
    search: str | None,
) -> dict[str, Any]:
    class_filter = None if classification == "all" else classification
    search_text = str(search or "").strip()
    search_filter = search_text if search_text else None
    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH latest_analysis AS (
                  SELECT DISTINCT ON (ma.market_id)
                    ma.market_id,
                    ma.classification,
                    ma.reason_json,
                    ma.local_score AS analysis_local_score,
                    ma.analyzed_at
                  FROM market_analysis ma
                  WHERE ma.status = 'active'
                  ORDER BY ma.market_id, ma.analyzed_at DESC
                ),
                event_counts AS (
                  SELECT event_id, COUNT(*)::INT AS event_market_count
                  FROM markets
                  WHERE event_id IS NOT NULL
                  GROUP BY event_id
                ),
                scoped_markets AS (
                  SELECT
                    m.market_id,
                    m.slug,
                    m.question,
                    m.description,
                    m.rules_text,
                    m.market_context,
                    m.market_archetype,
                    m.local_score,
                    m.high_competition,
                    m.event_id,
                    m.event_slug,
                    m.end_date,
                    m.last_seen_at,
                    COALESCE(latest_analysis.classification, 'unclassified') AS classification,
                    COALESCE(latest_analysis.analysis_local_score, m.local_score) AS analysis_local_score,
                    COALESCE(latest_analysis.reason_json, '{}'::jsonb) AS reason_json,
                    COALESCE(ec.event_market_count, 1) AS event_market_count,
                    COALESCE(
                      COUNT(cmm.chat_id) FILTER (WHERE cmm.link_status = 'active'),
                      0
                    )::INT AS mapped_channels
                  FROM markets m
                  LEFT JOIN latest_analysis ON latest_analysis.market_id = m.market_id
                  LEFT JOIN event_counts ec ON ec.event_id = m.event_id
                  LEFT JOIN channel_market_map cmm ON cmm.market_id = m.market_id
                  WHERE m.active = TRUE
                    AND m.closed = FALSE
                    AND (%s::text IS NULL OR COALESCE(latest_analysis.classification, 'unclassified') = %s::text)
                    AND (%s::numeric IS NULL OR COALESCE(latest_analysis.analysis_local_score, m.local_score) >= %s::numeric)
                    AND (
                      %s::text IS NULL
                      OR m.question ILIKE ('%%' || %s::text || '%%')
                      OR COALESCE(m.slug, '') ILIKE ('%%' || %s::text || '%%')
                      OR COALESCE(m.event_slug, '') ILIKE ('%%' || %s::text || '%%')
                      OR COALESCE(m.description, '') ILIKE ('%%' || %s::text || '%%')
                    )
                  GROUP BY
                    m.market_id, m.slug, m.question, m.description, m.rules_text, m.market_context,
                    m.market_archetype, m.local_score, m.high_competition, m.event_id, m.event_slug,
                    m.end_date, m.last_seen_at,
                    latest_analysis.classification, latest_analysis.analysis_local_score, latest_analysis.reason_json,
                    ec.event_market_count
                )
                SELECT
                  sm.*,
                  COALESCE(
                    json_agg(
                      json_build_object(
                        'outcome_index', mo.outcome_index,
                        'outcome_label', mo.outcome_label,
                        'probability', mo.probability,
                        'is_likely', mo.is_likely,
                        'is_unlikely', mo.is_unlikely
                      )
                      ORDER BY mo.outcome_index
                    ) FILTER (WHERE mo.market_id IS NOT NULL),
                    '[]'::json
                  ) AS outcomes
                FROM scoped_markets sm
                LEFT JOIN market_outcomes mo ON mo.market_id = sm.market_id
                GROUP BY
                  sm.market_id, sm.slug, sm.question, sm.description, sm.rules_text, sm.market_context,
                  sm.market_archetype, sm.local_score, sm.high_competition, sm.event_id, sm.event_slug,
                  sm.end_date, sm.last_seen_at, sm.classification, sm.analysis_local_score, sm.reason_json,
                  sm.event_market_count, sm.mapped_channels
                ORDER BY
                  CASE sm.classification
                    WHEN 'track_now' THEN 0
                    WHEN 'track_later' THEN 1
                    WHEN 'ignore' THEN 2
                    ELSE 3
                  END,
                  sm.analysis_local_score DESC NULLS LAST,
                  sm.last_seen_at DESC
                LIMIT %s;
                """,
                (
                    class_filter,
                    class_filter,
                    min_local_score,
                    min_local_score,
                    search_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                    int(limit),
                ),
            )
            markets = list(cur.fetchall())

            cur.execute(
                """
                WITH latest_analysis AS (
                  SELECT DISTINCT ON (ma.market_id)
                    ma.market_id,
                    ma.classification,
                    ma.local_score AS analysis_local_score
                  FROM market_analysis ma
                  WHERE ma.status = 'active'
                  ORDER BY ma.market_id, ma.analyzed_at DESC
                )
                SELECT
                  COALESCE(latest_analysis.classification, 'unclassified') AS classification,
                  COUNT(*)::INT AS market_count
                FROM markets m
                LEFT JOIN latest_analysis ON latest_analysis.market_id = m.market_id
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND (%s::numeric IS NULL OR COALESCE(latest_analysis.analysis_local_score, m.local_score) >= %s::numeric)
                  AND (
                    %s::text IS NULL
                    OR m.question ILIKE ('%%' || %s::text || '%%')
                    OR COALESCE(m.slug, '') ILIKE ('%%' || %s::text || '%%')
                    OR COALESCE(m.event_slug, '') ILIKE ('%%' || %s::text || '%%')
                    OR COALESCE(m.description, '') ILIKE ('%%' || %s::text || '%%')
                  )
                GROUP BY COALESCE(latest_analysis.classification, 'unclassified')
                ORDER BY market_count DESC;
                """,
                (
                    min_local_score,
                    min_local_score,
                    search_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                ),
            )
            counts_rows = list(cur.fetchall())

    counts = {str(item["classification"]): int(item["market_count"]) for item in counts_rows}
    total_open = sum(counts.values())
    out_markets: list[dict[str, Any]] = []
    for row in markets:
        outcomes = row.get("outcomes")
        if not isinstance(outcomes, list):
            outcomes = []
        # Keep outcomes compact in cards: show up to first 8 choices.
        compact_outcomes = [
            {
                "outcome_index": item.get("outcome_index"),
                "outcome_label": item.get("outcome_label"),
                "probability": item.get("probability"),
                "is_likely": item.get("is_likely"),
                "is_unlikely": item.get("is_unlikely"),
            }
            for item in outcomes[:8]
            if isinstance(item, dict)
        ]
        out_markets.append(
            {
                "market_id": row.get("market_id"),
                "slug": row.get("slug"),
                "question": row.get("question"),
                "description": row.get("description"),
                "market_archetype": row.get("market_archetype"),
                "classification": row.get("classification"),
                "analysis_local_score": row.get("analysis_local_score"),
                "reason_json": row.get("reason_json") if isinstance(row.get("reason_json"), dict) else {},
                "mapped_channels": row.get("mapped_channels"),
                "high_competition": row.get("high_competition"),
                "event_id": row.get("event_id"),
                "event_slug": row.get("event_slug"),
                "event_market_count": row.get("event_market_count"),
                "end_date": row.get("end_date"),
                "last_seen_at": row.get("last_seen_at"),
                "rules_text": row.get("rules_text"),
                "market_context": row.get("market_context"),
                "outcomes": compact_outcomes,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc),
        "classification_filter": classification,
        "min_local_score": min_local_score,
        "search": search_filter,
        "limit": int(limit),
        "counts": counts,
        "total_open_markets": total_open,
        "count_returned": len(out_markets),
        "markets": out_markets,
    }


def _fetch_market_rail_snapshot(
    *,
    db_url: str,
    classification: str,
    limit: int,
    channels_per_market: int,
    search: str | None,
    mapped_only: bool,
) -> dict[str, Any]:
    class_filter = None if classification == "all" else classification
    search_filter = str(search or "").strip() or None

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH latest_analysis AS (
                  SELECT DISTINCT ON (ma.market_id)
                    ma.market_id,
                    ma.classification,
                    ma.reason_json,
                    ma.local_score AS analysis_local_score,
                    ma.analyzed_at
                  FROM market_analysis ma
                  WHERE ma.status = 'active'
                  ORDER BY ma.market_id, ma.analyzed_at DESC
                )
                SELECT
                  m.market_id,
                  m.slug,
                  m.event_slug,
                  m.question,
                  m.description,
                  m.rules_text,
                  m.market_context,
                  m.market_archetype,
                  m.high_competition,
                  m.last_seen_at,
                  COALESCE(la.classification, 'unclassified') AS classification,
                  COALESCE(la.analysis_local_score, m.local_score) AS analysis_local_score,
                  COALESCE(la.reason_json, '{}'::jsonb) AS reason_json,
                  COALESCE(
                    (
                      SELECT COUNT(*)::INT
                      FROM channel_market_map cmm
                      JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                      WHERE cmm.market_id = m.market_id
                        AND cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                    ),
                    0
                  ) AS mapped_channels
                FROM markets m
                LEFT JOIN latest_analysis la ON la.market_id = m.market_id
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND (%s::text IS NULL OR COALESCE(la.classification, 'unclassified') = %s::text)
                  AND (
                    %s::text IS NULL
                    OR m.question ILIKE ('%%' || %s::text || '%%')
                    OR COALESCE(m.slug, '') ILIKE ('%%' || %s::text || '%%')
                    OR COALESCE(m.event_slug, '') ILIKE ('%%' || %s::text || '%%')
                    OR COALESCE(m.description, '') ILIKE ('%%' || %s::text || '%%')
                    OR COALESCE(m.rules_text, '') ILIKE ('%%' || %s::text || '%%')
                  )
                  AND (
                    %s = FALSE
                    OR EXISTS (
                      SELECT 1
                      FROM channel_market_map cmm2
                      JOIN telegram_channels tc2 ON tc2.chat_id = cmm2.chat_id
                      WHERE cmm2.market_id = m.market_id
                        AND cmm2.link_status = 'active'
                        AND tc2.is_active = TRUE
                    )
                  )
                ORDER BY
                  mapped_channels DESC,
                  CASE COALESCE(la.classification, 'unclassified')
                    WHEN 'track_now' THEN 0
                    WHEN 'track_later' THEN 1
                    WHEN 'ignore' THEN 2
                    ELSE 3
                  END,
                  COALESCE(la.analysis_local_score, m.local_score) DESC NULLS LAST,
                  m.last_seen_at DESC
                LIMIT %s;
                """,
                (
                    class_filter,
                    class_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                    search_filter,
                    bool(mapped_only),
                    int(limit),
                ),
            )
            markets = [dict(row) for row in cur.fetchall()]

            if not markets:
                return {
                    "generated_at": datetime.now(timezone.utc),
                    "classification_filter": classification,
                    "search": search_filter,
                    "limit": int(limit),
                    "channels_per_market": int(channels_per_market),
                    "count_markets": 0,
                    "count_channels_unique": 0,
                    "markets": [],
                }

            market_ids = [str(item["market_id"]) for item in markets]

            cur.execute(
                """
                SELECT
                  mo.market_id,
                  mo.outcome_index,
                  mo.outcome_label,
                  mo.probability,
                  mo.is_likely,
                  mo.is_unlikely
                FROM market_outcomes mo
                WHERE mo.market_id = ANY(%s)
                ORDER BY mo.market_id, mo.outcome_index;
                """,
                (market_ids,),
            )
            outcome_rows = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                WITH ranked_links AS (
                  SELECT
                    cmm.market_id,
                    tc.chat_id,
                    tc.title,
                    tc.username,
                    tc.description,
                    tc.member_count,
                    tc.trust_weight,
                    tc.last_seen_at,
                    tc.notes,
                    cmm.link_source,
                    cmm.priority_rank,
                    cmm.updated_at,
                    ROW_NUMBER() OVER (
                      PARTITION BY cmm.market_id
                      ORDER BY
                        COALESCE(cmm.priority_rank, 2147483647),
                        tc.member_count DESC NULLS LAST,
                        cmm.updated_at DESC
                    ) AS link_rank
                  FROM channel_market_map cmm
                  JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                  WHERE cmm.market_id = ANY(%s)
                    AND cmm.link_status = 'active'
                    AND tc.is_active = TRUE
                )
                SELECT
                  market_id,
                  chat_id,
                  title,
                  username,
                  description,
                  member_count,
                  trust_weight,
                  last_seen_at,
                  notes,
                  link_source,
                  priority_rank,
                  updated_at,
                  link_rank
                FROM ranked_links
                WHERE link_rank <= %s
                ORDER BY market_id, link_rank;
                """,
                (market_ids, int(channels_per_market)),
            )
            channel_rows = [dict(row) for row in cur.fetchall()]

            unique_chat_ids = sorted({int(row["chat_id"]) for row in channel_rows})
            message_by_chat: dict[int, dict[str, Any]] = {}
            if unique_chat_ids:
                cur.execute(
                    """
                    SELECT DISTINCT ON (tm.chat_id)
                      tm.chat_id,
                      tm.message_id,
                      tm.posted_at,
                      tm.text
                    FROM telegram_messages tm
                    WHERE tm.chat_id = ANY(%s)
                    ORDER BY tm.chat_id, tm.posted_at DESC NULLS LAST, tm.message_id DESC;
                    """,
                    (unique_chat_ids,),
                )
                for row in cur.fetchall():
                    chat_id = int(row["chat_id"])
                    message_by_chat[chat_id] = {
                        "message_id": int(row["message_id"]),
                        "posted_at": row.get("posted_at"),
                        "text": str(row.get("text") or "")[:300],
                    }

    outcomes_by_market: dict[str, list[dict[str, Any]]] = {}
    for row in outcome_rows:
        market_id = str(row["market_id"])
        outcomes_by_market.setdefault(market_id, []).append(
            {
                "outcome_index": row.get("outcome_index"),
                "outcome_label": row.get("outcome_label"),
                "probability": row.get("probability"),
                "is_likely": row.get("is_likely"),
                "is_unlikely": row.get("is_unlikely"),
            }
        )

    channels_by_market: dict[str, list[dict[str, Any]]] = {}
    for row in channel_rows:
        market_id = str(row["market_id"])
        username = str(row.get("username") or "").strip()
        chat_id = int(row["chat_id"])
        channels_by_market.setdefault(market_id, []).append(
            {
                "chat_id": chat_id,
                "title": row.get("title"),
                "username": username or None,
                "description": row.get("description"),
                "member_count": row.get("member_count"),
                "trust_weight": row.get("trust_weight"),
                "link_source": row.get("link_source"),
                "priority_rank": row.get("priority_rank"),
                "updated_at": row.get("updated_at"),
                "rank": row.get("link_rank"),
                "notes": row.get("notes"),
                "tme_url": f"https://t.me/{username}" if username else None,
                "last_message": message_by_chat.get(chat_id),
            }
        )

    out_markets: list[dict[str, Any]] = []
    for row in markets:
        market_id = str(row["market_id"])
        reason_json = row.get("reason_json") if isinstance(row.get("reason_json"), dict) else {}
        correction_source = str(reason_json.get("source") or "")
        out_markets.append(
            {
                "market_id": market_id,
                "slug": row.get("slug"),
                "event_slug": row.get("event_slug"),
                "question": row.get("question"),
                "description": row.get("description"),
                "rules_text": row.get("rules_text"),
                "market_context": row.get("market_context"),
                "market_archetype": row.get("market_archetype"),
                "classification": row.get("classification"),
                "analysis_local_score": row.get("analysis_local_score"),
                "reason_json": reason_json,
                "correction_source": correction_source,
                "is_corrected": correction_source.startswith("manual_"),
                "high_competition": row.get("high_competition"),
                "mapped_channels": int(row.get("mapped_channels") or 0),
                "last_seen_at": row.get("last_seen_at"),
                "outcomes": outcomes_by_market.get(market_id, [])[:12],
                "channels": channels_by_market.get(market_id, []),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc),
        "classification_filter": classification,
        "search": search_filter,
        "limit": int(limit),
        "channels_per_market": int(channels_per_market),
        "mapped_only": bool(mapped_only),
        "count_markets": len(out_markets),
        "count_channels_unique": len(unique_chat_ids),
        "markets": out_markets,
    }


def _fetch_workspace_overview_snapshot(*, db_url: str) -> dict[str, Any]:
    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH latest_analysis AS (
                  SELECT DISTINCT ON (ma.market_id)
                    ma.market_id,
                    ma.classification
                  FROM market_analysis ma
                  WHERE ma.status = 'active'
                  ORDER BY ma.market_id, ma.analyzed_at DESC
                )
                SELECT
                  COUNT(*)::INT AS open_markets,
                  COUNT(*) FILTER (WHERE COALESCE(la.classification, 'unclassified') = 'track_now')::INT AS track_now_markets,
                  COUNT(*) FILTER (WHERE COALESCE(la.classification, 'unclassified') = 'track_later')::INT AS track_later_markets,
                  COUNT(*) FILTER (WHERE COALESCE(la.classification, 'unclassified') = 'ignore')::INT AS ignore_markets,
                  COUNT(*) FILTER (WHERE COALESCE(la.classification, 'unclassified') = 'unclassified')::INT AS unclassified_markets
                FROM markets m
                LEFT JOIN latest_analysis la ON la.market_id = m.market_id
                WHERE m.active = TRUE
                  AND m.closed = FALSE;
                """
            )
            market_counts = cur.fetchone() or {}

            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS active_links,
                  COUNT(DISTINCT cmm.chat_id)::INT AS linked_channels
                FROM channel_market_map cmm
                WHERE cmm.link_status = 'active';
                """
            )
            link_counts = cur.fetchone() or {}

            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS active_channels,
                  COUNT(*) FILTER (WHERE member_count >= 1000)::INT AS channels_over_1k
                FROM telegram_channels
                WHERE is_active = TRUE;
                """
            )
            channel_counts = cur.fetchone() or {}

            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS messages_24h
                FROM telegram_messages
                WHERE ingested_at >= NOW() - INTERVAL '24 hours';
                """
            )
            messages_24h = cur.fetchone() or {}

            cur.execute(
                """
                SELECT COUNT(*)::INT AS activations_count
                FROM market_activations;
                """
            )
            activation_counts = cur.fetchone() or {}

            cur.execute(
                """
                SELECT COUNT(*)::INT AS backtest_runs
                FROM telegram_backtest_runs
                WHERE created_at >= NOW() - INTERVAL '7 days';
                """
            )
            backtest_counts = cur.fetchone() or {}

            cur.execute(
                """
                SELECT
                  m.market_id,
                  m.slug,
                  m.question,
                  m.last_seen_at
                FROM markets m
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                ORDER BY m.last_seen_at DESC
                LIMIT 1;
                """
            )
            newest_market = cur.fetchone() or {}

            cur.execute(
                """
                SELECT
                  run_id,
                  created_at,
                  market_ref,
                  market_id,
                  market_slug
                FROM telegram_backtest_runs
                ORDER BY created_at DESC
                LIMIT 1;
                """
            )
            latest_backtest = cur.fetchone() or {}

    return {
        "generated_at": datetime.now(timezone.utc),
        "markets": {
            "open": int(market_counts.get("open_markets") or 0),
            "track_now": int(market_counts.get("track_now_markets") or 0),
            "track_later": int(market_counts.get("track_later_markets") or 0),
            "ignore": int(market_counts.get("ignore_markets") or 0),
            "unclassified": int(market_counts.get("unclassified_markets") or 0),
        },
        "links": {
            "active_links": int(link_counts.get("active_links") or 0),
            "linked_channels": int(link_counts.get("linked_channels") or 0),
        },
        "channels": {
            "active": int(channel_counts.get("active_channels") or 0),
            "over_1k_members": int(channel_counts.get("channels_over_1k") or 0),
        },
        "messages": {
            "ingested_24h": int(messages_24h.get("messages_24h") or 0),
        },
        "activations": {
            "total": int(activation_counts.get("activations_count") or 0),
        },
        "backtests": {
            "runs_7d": int(backtest_counts.get("backtest_runs") or 0),
            "latest": latest_backtest,
        },
        "latest_market_seen": newest_market,
    }


def _fetch_pipeline_map_snapshot(
    *,
    db_url: str,
    market_limit: int,
    channel_limit: int,
) -> dict[str, Any]:
    effective_market_limit = max(1, min(int(market_limit), 800))
    effective_channel_limit = max(1, min(int(channel_limit), 500))
    slug_map: dict[str, list[str]] = {}
    scoped_event_slugs: list[str] = []
    for source_url in _PIPELINE_SCOPE_SOURCE_URLS:
        source_slugs = _extract_event_slugs_from_source_url(
            source_url,
            max_slugs_per_source=250,
            timeout_seconds=25,
        )
        slug_map[source_url] = source_slugs
        scoped_event_slugs.extend(source_slugs)
    scoped_event_slugs = _dedupe_preserve(scoped_event_slugs)
    if not scoped_event_slugs:
        raise RuntimeError("Failed to extract scoped event slugs from configured Polymarket source URLs.")

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS channels_total,
                  COUNT(*) FILTER (WHERE is_active = TRUE)::INT AS channels_active
                FROM telegram_channels;
                """
            )
            channel_totals_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS markets_total
                FROM markets m
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND COALESCE(m.archived, FALSE) = FALSE
                  AND COALESCE(m.accepting_orders, FALSE) = TRUE
                  AND COALESCE(m.enable_order_book, FALSE) = TRUE
                  AND m.event_slug = ANY(%s);
                """,
                (scoped_event_slugs,),
            )
            market_totals_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  m.market_id,
                  m.slug,
                  m.event_slug,
                  m.question,
                  m.description,
                  m.rules_text,
                  m.market_context,
                  m.market_archetype,
                  m.accepting_orders,
                  m.enable_order_book,
                  m.high_competition,
                  m.end_date,
                  m.last_seen_at,
                  COALESCE(
                    (
                      SELECT COUNT(*)::INT
                      FROM channel_market_map cmm
                      JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                      WHERE cmm.market_id = m.market_id
                        AND cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                    ),
                    0
                  ) AS mapped_channels
                FROM markets m
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND COALESCE(m.archived, FALSE) = FALSE
                  AND COALESCE(m.accepting_orders, FALSE) = TRUE
                  AND COALESCE(m.enable_order_book, FALSE) = TRUE
                  AND m.event_slug = ANY(%s)
                ORDER BY
                  m.high_competition DESC,
                  m.end_date ASC NULLS LAST,
                  m.last_seen_at DESC
                LIMIT %s;
                """,
                (scoped_event_slugs, effective_market_limit),
            )
            markets = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  tc.chat_id,
                  tc.title,
                  tc.username,
                  tc.description,
                  tc.member_count,
                  tc.trust_weight,
                  tc.is_active,
                  tc.last_seen_at,
                  tc.notes,
                  COALESCE(
                    (
                      SELECT COUNT(*)::INT
                      FROM channel_market_map cmm
                      WHERE cmm.chat_id = tc.chat_id
                        AND cmm.link_status = 'active'
                    ),
                    0
                  ) AS mapped_markets
                FROM telegram_channels tc
                ORDER BY
                  tc.is_active DESC,
                  tc.member_count DESC NULLS LAST,
                  tc.title ASC
                LIMIT %s;
                """,
                (effective_channel_limit,),
            )
            channels = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT COUNT(*)::INT AS active_links
                FROM channel_market_map cmm
                JOIN markets m ON m.market_id = cmm.market_id
                WHERE cmm.link_status = 'active'
                  AND m.active = TRUE
                  AND m.closed = FALSE
                  AND COALESCE(m.archived, FALSE) = FALSE
                  AND COALESCE(m.accepting_orders, FALSE) = TRUE
                  AND COALESCE(m.enable_order_book, FALSE) = TRUE
                  AND m.event_slug = ANY(%s);
                """,
                (scoped_event_slugs,),
            )
            link_count = int((cur.fetchone() or {}).get("active_links") or 0)

            cur.execute("SELECT COUNT(*)::INT AS count FROM telegram_messages;")
            message_count = int((cur.fetchone() or {}).get("count") or 0)

            cur.execute(
                """
                SELECT COUNT(*)::INT AS count
                FROM message_market_matches mmm
                JOIN markets m ON m.market_id = mmm.market_id
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND COALESCE(m.archived, FALSE) = FALSE
                  AND COALESCE(m.accepting_orders, FALSE) = TRUE
                  AND COALESCE(m.enable_order_book, FALSE) = TRUE
                  AND m.event_slug = ANY(%s);
                """,
                (scoped_event_slugs,),
            )
            match_count = int((cur.fetchone() or {}).get("count") or 0)

            cur.execute(
                """
                SELECT COUNT(*)::INT AS count
                FROM market_activations ma
                JOIN markets m ON m.market_id = ma.market_id
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND COALESCE(m.archived, FALSE) = FALSE
                  AND COALESCE(m.accepting_orders, FALSE) = TRUE
                  AND COALESCE(m.enable_order_book, FALSE) = TRUE
                  AND m.event_slug = ANY(%s);
                """,
                (scoped_event_slugs,),
            )
            activation_count = int((cur.fetchone() or {}).get("count") or 0)

            cur.execute(
                """
                SELECT
                  m.event_slug,
                  m.slug,
                  m.question,
                  m.description,
                  m.market_context
                FROM markets m
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND COALESCE(m.archived, FALSE) = FALSE
                  AND COALESCE(m.accepting_orders, FALSE) = TRUE
                  AND COALESCE(m.enable_order_book, FALSE) = TRUE
                  AND m.event_slug = ANY(%s);
                """,
                (scoped_event_slugs,),
            )
            all_markets_for_scope = [dict(row) for row in cur.fetchall()]

    scope_counts: dict[str, int] = {}
    normalized_markets: list[dict[str, Any]] = []
    for item in markets:
        scope = _pipeline_market_scope(item)
        normalized_markets.append(
            {
                **item,
                "scope_label": scope,
                "public_url": f"https://polymarket.com/event/{item['slug']}" if item.get("slug") else None,
            }
        )

    for item in all_markets_for_scope:
        scope = _pipeline_market_scope(item)
        scope_counts[scope] = scope_counts.get(scope, 0) + 1

    normalized_channels: list[dict[str, Any]] = []
    for item in channels:
        username = str(item.get("username") or "").strip()
        normalized_channels.append(
            {
                **item,
                "public_url": f"https://t.me/{username}" if username else None,
            }
        )

    scope_items = [
        {"label": label, "count": count}
        for label, count in sorted(scope_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]

    workflow = [
        {
            "id": "channels",
            "label": "Saved Channels",
            "status": "ready" if normalized_channels else "empty",
            "value": len(normalized_channels),
            "hint": "public.telegram_channels",
        },
        {
            "id": "markets",
            "label": "Tradable Markets",
            "status": "ready" if normalized_markets else "empty",
            "value": len(normalized_markets),
            "hint": "public.markets",
        },
        {
            "id": "mapping",
            "label": "AI Mapper",
            "status": "ready" if link_count > 0 else "pending",
            "value": link_count,
            "hint": "public.channel_market_map",
        },
        {
            "id": "listener",
            "label": "Live Listener",
            "status": "ready" if message_count > 0 else "pending",
            "value": message_count,
            "hint": "public.telegram_messages",
        },
        {
            "id": "paper",
            "label": "Paper Trader",
            "status": "ready" if activation_count > 0 else "pending",
            "value": activation_count,
            "hint": "paper trading not wired yet",
        },
    ]

    return {
        "generated_at": datetime.now(timezone.utc),
        "storage": {
            "channels_table": "public.telegram_channels",
            "markets_table": "public.markets",
            "outcomes_table": "public.market_outcomes",
            "links_table": "public.channel_market_map",
        },
        "scope_sources": list(_PIPELINE_SCOPE_SOURCE_URLS),
        "source_slug_counts": {url: len(slugs) for url, slugs in slug_map.items()},
        "counts": {
            "channels_total": int(channel_totals_row.get("channels_total") or 0),
            "channels_active": int(channel_totals_row.get("channels_active") or 0),
            "markets_total": int(market_totals_row.get("markets_total") or 0),
            "active_links": int(link_count),
            "messages_total": int(message_count),
            "matches_total": int(match_count),
            "activations_total": int(activation_count),
        },
        "market_scope_counts": scope_items,
        "workflow": workflow,
        "markets": normalized_markets,
        "channels": normalized_channels,
    }


def _fetch_stored_markets_snapshot(
    *,
    db_url: str,
    group_limit: int,
    member_limit: int,
    scope: str,
    search: str | None,
) -> dict[str, Any]:
    effective_group_limit = max(1, min(int(group_limit), 500))
    effective_member_limit = max(1, min(int(member_limit), 200))
    normalized_scope = str(scope or "all").strip().lower() or "all"
    search_text = str(search or "").strip()
    search_pattern = f"%{search_text}%"

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS groups_total,
                  COALESCE(SUM(tradable_market_count), 0)::INT AS member_markets_total,
                  COUNT(DISTINCT scope_label)::INT AS scopes_total,
                  MIN(earliest_end_date) AS soonest_end_date,
                  MAX(last_seen_at) AS latest_seen_at
                FROM market_groups;
                """
            )
            totals_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  scope_label,
                  COUNT(*)::INT AS groups_count,
                  COALESCE(SUM(tradable_market_count), 0)::INT AS markets_count
                FROM market_groups
                GROUP BY scope_label
                ORDER BY groups_count DESC, markets_count DESC, scope_label ASC;
                """
            )
            scope_rows = [dict(row) for row in cur.fetchall()]

            filter_params = (
                normalized_scope,
                normalized_scope,
                search_text,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
            )

            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS visible_groups,
                  COALESCE(SUM(mg.tradable_market_count), 0)::INT AS visible_markets
                FROM market_groups mg
                LEFT JOIN markets rm ON rm.market_id = mg.representative_market_id
                WHERE (%s = 'all' OR lower(mg.scope_label) = %s)
                  AND (
                    %s = ''
                    OR COALESCE(mg.group_slug, '') ILIKE %s
                    OR COALESCE(mg.group_title, '') ILIKE %s
                    OR COALESCE(mg.scope_label, '') ILIKE %s
                    OR COALESCE(mg.sample_questions::text, '') ILIKE %s
                    OR COALESCE(rm.question, '') ILIKE %s
                  );
                """,
                filter_params,
            )
            visible_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  mg.group_slug,
                  mg.event_id,
                  mg.scope_label,
                  mg.group_title,
                  mg.representative_market_id,
                  mg.market_count,
                  mg.tradable_market_count,
                  mg.earliest_end_date,
                  mg.latest_end_date,
                  mg.last_seen_at,
                  mg.generated_at,
                  mg.updated_at,
                  mg.source_urls,
                  mg.sample_questions,
                  rm.slug AS representative_slug,
                  rm.question AS representative_question,
                  rm.description AS representative_description,
                  rm.market_context AS representative_context,
                  rm.market_archetype AS representative_archetype,
                  rm.end_date AS representative_end_date
                FROM market_groups mg
                LEFT JOIN markets rm ON rm.market_id = mg.representative_market_id
                WHERE (%s = 'all' OR lower(mg.scope_label) = %s)
                  AND (
                    %s = ''
                    OR COALESCE(mg.group_slug, '') ILIKE %s
                    OR COALESCE(mg.group_title, '') ILIKE %s
                    OR COALESCE(mg.scope_label, '') ILIKE %s
                    OR COALESCE(mg.sample_questions::text, '') ILIKE %s
                    OR COALESCE(rm.question, '') ILIKE %s
                  )
                ORDER BY
                  mg.tradable_market_count DESC,
                  mg.last_seen_at DESC NULLS LAST,
                  mg.group_slug ASC
                LIMIT %s;
                """,
                (*filter_params, effective_group_limit),
            )
            groups = [dict(row) for row in cur.fetchall()]

            visible_group_slugs = [str(row.get("group_slug") or "") for row in groups if row.get("group_slug")]
            members: list[dict[str, Any]] = []
            if visible_group_slugs:
                cur.execute(
                    """
                    SELECT
                      mgm.group_slug,
                      mgm.priority_rank,
                      mgm.market_id,
                      m.slug,
                      m.question,
                      m.description,
                      m.market_context,
                      m.market_archetype,
                      m.end_date,
                      m.last_seen_at
                    FROM market_group_members mgm
                    JOIN markets m ON m.market_id = mgm.market_id
                    WHERE mgm.group_slug = ANY(%s)
                    ORDER BY mgm.group_slug ASC, mgm.priority_rank ASC, m.end_date ASC NULLS LAST;
                    """,
                    (visible_group_slugs,),
                )
                members = [dict(row) for row in cur.fetchall()]

    members_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in members:
        group_slug = str(item.get("group_slug") or "")
        members_by_group.setdefault(group_slug, []).append(
            {
                **item,
                "public_url": f"https://polymarket.com/event/{item['slug']}" if item.get("slug") else None,
            }
        )

    normalized_groups: list[dict[str, Any]] = []
    for item in groups:
        group_slug = str(item.get("group_slug") or "")
        group_members = members_by_group.get(group_slug, [])
        source_urls = item.get("source_urls")
        sample_questions = item.get("sample_questions")
        normalized_groups.append(
            {
                **item,
                "source_urls": source_urls if isinstance(source_urls, list) else [],
                "sample_questions": sample_questions if isinstance(sample_questions, list) else [],
                "representative_public_url": (
                    f"https://polymarket.com/event/{item['representative_slug']}"
                    if item.get("representative_slug")
                    else None
                ),
                "members": group_members[:effective_member_limit],
                "member_overflow_count": max(0, len(group_members) - effective_member_limit),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc),
        "storage": {
            "groups_table": "public.market_groups",
            "members_table": "public.market_group_members",
            "markets_table": "public.markets",
        },
        "source_pages": list(_PIPELINE_SCOPE_SOURCE_URLS),
        "filters": {
            "scope": normalized_scope,
            "search": search_text,
            "group_limit": effective_group_limit,
            "member_limit": effective_member_limit,
        },
        "counts": {
            "groups_total": int(totals_row.get("groups_total") or 0),
            "member_markets_total": int(totals_row.get("member_markets_total") or 0),
            "scopes_total": int(totals_row.get("scopes_total") or 0),
            "visible_groups": int(visible_row.get("visible_groups") or 0),
            "visible_markets": int(visible_row.get("visible_markets") or 0),
            "soonest_end_date": totals_row.get("soonest_end_date"),
            "latest_seen_at": totals_row.get("latest_seen_at"),
        },
        "scope_counts": [
            {
                "label": row.get("scope_label") or "Other",
                "groups": int(row.get("groups_count") or 0),
                "markets": int(row.get("markets_count") or 0),
            }
            for row in scope_rows
        ],
        "groups": normalized_groups,
    }


def _fetch_saved_channel_map_snapshot(
    *,
    db_url: str,
    source_file: str | None,
    link_source: str,
    include_unlinked: bool,
) -> dict[str, Any]:
    source_filter = str(source_file or "").strip()
    normalized_link_source = str(link_source or "ai_handpicked_batch_v1").strip()
    link_filter_all = normalized_link_source.lower() in {"", "all", "*"}

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS saved_channels_total,
                  COUNT(*) FILTER (WHERE is_active = TRUE)::INT AS active_channels_total,
                  MAX(last_seen_at) AS latest_channel_seen_at
                FROM telegram_channels;
                """
            )
            channel_totals = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  source_file,
                  COUNT(*)::INT AS total_rows,
                  COUNT(*) FILTER (WHERE match_status = 'matched')::INT AS matched_rows,
                  COUNT(*) FILTER (WHERE match_status = 'low_confidence')::INT AS low_confidence_rows,
                  COUNT(*) FILTER (WHERE match_status = 'unmatched')::INT AS unmatched_rows,
                  MAX(updated_at) AS latest_updated_at
                FROM handpicked_market_targets
                GROUP BY source_file
                ORDER BY latest_updated_at DESC NULLS LAST, source_file ASC;
                """
            )
            source_rows = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT DISTINCT ON (t.representative_market_id)
                  t.target_id,
                  t.source_file,
                  t.source_line_number,
                  t.requested_name,
                  t.requested_bucket,
                  t.matched_group_slug,
                  t.matched_group_title,
                  t.matched_scope_label,
                  t.representative_market_id AS market_id,
                  mg.group_title,
                  mg.scope_label AS group_scope_label,
                  mg.sample_questions,
                  m.slug,
                  m.question,
                  m.description,
                  m.market_context,
                  m.end_date,
                  m.last_seen_at
                FROM handpicked_market_targets t
                JOIN markets m
                  ON m.market_id = t.representative_market_id
                LEFT JOIN market_groups mg
                  ON mg.group_slug = t.matched_group_slug
                WHERE t.match_status = 'matched'
                  AND t.representative_market_id IS NOT NULL
                  AND (%s = '' OR t.source_file = %s)
                ORDER BY t.representative_market_id ASC, t.source_line_number ASC;
                """,
                (source_filter, source_filter),
            )
            approved_rows = [dict(row) for row in cur.fetchall()]

            approved_market_ids = [str(row["market_id"]) for row in approved_rows if row.get("market_id")]

            link_source_rows: list[dict[str, Any]] = []
            edge_rows: list[dict[str, Any]] = []
            if approved_market_ids:
                cur.execute(
                    """
                    SELECT
                      cmm.link_source,
                      COUNT(*)::INT AS active_links,
                      COUNT(DISTINCT cmm.chat_id)::INT AS linked_channels,
                      COUNT(DISTINCT cmm.market_id)::INT AS linked_markets,
                      MAX(cmm.updated_at) AS latest_updated_at
                    FROM channel_market_map cmm
                    WHERE cmm.link_status = 'active'
                      AND cmm.market_id = ANY(%s)
                    GROUP BY cmm.link_source
                    ORDER BY active_links DESC, cmm.link_source ASC;
                    """,
                    (approved_market_ids,),
                )
                link_source_rows = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT
                      cmm.chat_id,
                      cmm.market_id,
                      cmm.link_source,
                      cmm.priority_rank,
                      cmm.notes AS link_notes,
                      cmm.created_at,
                      cmm.updated_at,
                      tc.title,
                      tc.username,
                      tc.description,
                      tc.member_count,
                      tc.language_hint,
                      tc.tags_json,
                      tc.notes AS channel_notes,
                      tc.last_seen_at
                    FROM channel_market_map cmm
                    JOIN telegram_channels tc
                      ON tc.chat_id = cmm.chat_id
                    WHERE cmm.link_status = 'active'
                      AND tc.is_active = TRUE
                      AND cmm.market_id = ANY(%s)
                      AND (%s = TRUE OR cmm.link_source = %s)
                    ORDER BY
                      cmm.market_id ASC,
                      COALESCE(cmm.priority_rank, 999999) ASC,
                      tc.member_count DESC NULLS LAST,
                      tc.title ASC;
                    """,
                    (approved_market_ids, link_filter_all, normalized_link_source),
                )
                edge_rows = [dict(row) for row in cur.fetchall()]

    markets_by_id: dict[str, dict[str, Any]] = {}
    bucket_counts: dict[str, dict[str, Any]] = {}
    for row in approved_rows:
        market_id = str(row.get("market_id") or "").strip()
        if not market_id:
            continue
        bucket = str(
            row.get("requested_bucket")
            or row.get("matched_scope_label")
            or row.get("group_scope_label")
            or "Other"
        ).strip() or "Other"
        market_item = {
            "target_id": int(row.get("target_id") or 0),
            "source_file": row.get("source_file"),
            "source_label": Path(str(row.get("source_file") or "")).name or "unknown",
            "source_line_number": int(row.get("source_line_number") or 0),
            "market_id": market_id,
            "market_label": str(row.get("requested_name") or row.get("matched_group_title") or row.get("question") or market_id),
            "bucket": bucket,
            "group_slug": row.get("matched_group_slug"),
            "group_title": row.get("group_title") or row.get("matched_group_title"),
            "scope_label": row.get("matched_scope_label") or row.get("group_scope_label") or bucket,
            "slug": row.get("slug"),
            "question": row.get("question"),
            "description": row.get("description"),
            "market_context": row.get("market_context"),
            "end_date": row.get("end_date"),
            "last_seen_at": row.get("last_seen_at"),
            "sample_questions": row.get("sample_questions") if isinstance(row.get("sample_questions"), list) else [],
            "public_url": f"https://polymarket.com/event/{row['slug']}" if row.get("slug") else None,
            "link_count": 0,
            "best_confidence": None,
            "avg_confidence": None,
            "linked_channel_ids": [],
        }
        markets_by_id[market_id] = market_item
        bucket_metrics = bucket_counts.setdefault(
            bucket,
            {
                "label": bucket,
                "market_count": 0,
                "linked_markets": 0,
                "links": 0,
            },
        )
        bucket_metrics["market_count"] += 1

    channels_by_id: dict[int, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    confidence_sums: dict[str, float] = {}
    confidence_counts: dict[str, int] = {}
    for row in edge_rows:
        market_id = str(row.get("market_id") or "").strip()
        market = markets_by_id.get(market_id)
        if market is None:
            continue
        chat_id = int(row.get("chat_id") or 0)
        confidence = _extract_saved_link_confidence(row.get("link_notes"))
        reason_short = _extract_saved_link_reason(row.get("link_notes"))

        channel = channels_by_id.setdefault(
            chat_id,
            {
                "chat_id": chat_id,
                "title": str(row.get("title") or chat_id),
                "username": row.get("username"),
                "description": row.get("description"),
                "member_count": int(row.get("member_count") or 0),
                "language_hint": row.get("language_hint") if isinstance(row.get("language_hint"), list) else [],
                "tags_json": row.get("tags_json") if isinstance(row.get("tags_json"), list) else [],
                "notes": row.get("channel_notes") or "",
                "last_seen_at": row.get("last_seen_at"),
                "link_count": 0,
                "best_confidence": None,
                "linked_market_ids": [],
                "public_url": f"https://t.me/{row['username']}" if row.get("username") else None,
            },
        )

        market["link_count"] += 1
        market["linked_channel_ids"].append(chat_id)
        channel["link_count"] += 1
        channel["linked_market_ids"].append(market_id)
        if confidence is not None:
            if market["best_confidence"] is None or float(confidence) > float(market["best_confidence"]):
                market["best_confidence"] = confidence
            if channel["best_confidence"] is None or float(confidence) > float(channel["best_confidence"]):
                channel["best_confidence"] = confidence
            confidence_sums[market_id] = confidence_sums.get(market_id, 0.0) + float(confidence)
            confidence_counts[market_id] = confidence_counts.get(market_id, 0) + 1
        edges.append(
            {
                "chat_id": chat_id,
                "market_id": market_id,
                "link_source": row.get("link_source"),
                "priority_rank": int(row.get("priority_rank") or 0),
                "confidence": confidence,
                "reason_short": reason_short,
                "updated_at": row.get("updated_at"),
                "created_at": row.get("created_at"),
            }
        )

    for market in markets_by_id.values():
        if market["link_count"] > 0:
            bucket_counts[market["bucket"]]["linked_markets"] += 1
            bucket_counts[market["bucket"]]["links"] += int(market["link_count"])
        if confidence_counts.get(str(market["market_id"])):
            market["avg_confidence"] = round(
                confidence_sums[str(market["market_id"])] / confidence_counts[str(market["market_id"])],
                4,
            )

    markets = list(markets_by_id.values())
    if not include_unlinked:
        markets = [item for item in markets if int(item.get("link_count") or 0) > 0]

    markets.sort(
        key=lambda item: (
            -int(item.get("link_count") or 0),
            str(item.get("bucket") or "").lower(),
            int(item.get("source_line_number") or 0),
            str(item.get("market_label") or "").lower(),
        )
    )
    channels = sorted(
        channels_by_id.values(),
        key=lambda item: (
            -int(item.get("link_count") or 0),
            -int(item.get("member_count") or 0),
            str(item.get("title") or "").lower(),
        ),
    )
    edges.sort(
        key=lambda item: (
            str(item.get("market_id") or ""),
            int(item.get("priority_rank") or 0),
            -(float(item.get("confidence")) if item.get("confidence") is not None else -1.0),
            int(item.get("chat_id") or 0),
        )
    )

    approved_markets_total = len(markets_by_id)
    linked_markets_total = sum(1 for item in markets_by_id.values() if int(item.get("link_count") or 0) > 0)
    saved_channels_total = int(channel_totals.get("saved_channels_total") or 0)
    active_channels_total = int(channel_totals.get("active_channels_total") or 0)
    linked_channels_total = len(channels_by_id)

    return {
        "generated_at": datetime.now(timezone.utc),
        "storage": {
            "targets_table": "public.handpicked_market_targets",
            "links_table": "public.channel_market_map",
            "channels_table": "public.telegram_channels",
            "markets_table": "public.markets",
        },
        "filters": {
            "source_file": source_filter,
            "link_source": normalized_link_source or "all",
            "include_unlinked": bool(include_unlinked),
        },
        "counts": {
            "approved_markets_total": approved_markets_total,
            "linked_markets_total": linked_markets_total,
            "unlinked_markets_total": max(0, approved_markets_total - linked_markets_total),
            "saved_channels_total": saved_channels_total,
            "active_channels_total": active_channels_total,
            "linked_channels_total": linked_channels_total,
            "unlinked_saved_channels_total": max(0, active_channels_total - linked_channels_total),
            "links_total": len(edges),
            "latest_channel_seen_at": channel_totals.get("latest_channel_seen_at"),
        },
        "source_files": [
            {
                **row,
                "source_label": Path(str(row.get("source_file") or "")).name or "unknown",
            }
            for row in source_rows
        ],
        "link_source_breakdown": link_source_rows,
        "bucket_counts": sorted(
            bucket_counts.values(),
            key=lambda item: (-int(item.get("market_count") or 0), str(item.get("label") or "").lower()),
        ),
        "markets": markets,
        "channels": channels,
        "edges": edges,
    }


def _fetch_telegram_live_snapshot(
    *,
    db_url: str,
    source_file: str | None,
    link_source: str,
    message_limit: int,
    event_limit: int,
    activation_limit: int,
    agent_name: str,
) -> dict[str, Any]:
    source_filter = str(source_file or "").strip()
    normalized_link_source = str(link_source or "ai_handpicked_batch_v1").strip()
    link_filter_all = normalized_link_source.lower() in {"", "all", "*"}
    effective_message_limit = max(1, min(int(message_limit), 300))
    effective_activation_limit = max(1, min(int(activation_limit), 80))
    runtime = _fetch_agent_runtime_snapshot(
        db_url=db_url,
        agent_name=str(agent_name or "telegram-realtime-listener").strip() or "telegram-realtime-listener",
        event_limit=event_limit,
    )

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH approved_markets AS (
                  SELECT DISTINCT ON (t.representative_market_id)
                    t.representative_market_id AS market_id
                  FROM handpicked_market_targets t
                  WHERE t.match_status = 'matched'
                    AND t.representative_market_id IS NOT NULL
                    AND (%s = '' OR t.source_file = %s)
                  ORDER BY t.representative_market_id ASC, t.source_line_number ASC
                ),
                watched_links AS (
                  SELECT
                    cmm.chat_id,
                    cmm.market_id
                  FROM channel_market_map cmm
                  JOIN telegram_channels tc
                    ON tc.chat_id = cmm.chat_id
                  JOIN markets m
                    ON m.market_id = cmm.market_id
                  JOIN approved_markets am
                    ON am.market_id = cmm.market_id
                  WHERE cmm.link_status = 'active'
                    AND tc.is_active = TRUE
                    AND m.active = TRUE
                    AND m.closed = FALSE
                    AND (%s = TRUE OR cmm.link_source = %s)
                ),
                watched_channels AS (
                  SELECT DISTINCT chat_id FROM watched_links
                ),
                watched_markets AS (
                  SELECT DISTINCT market_id FROM watched_links
                )
                SELECT
                  (SELECT COUNT(*)::INT FROM watched_links) AS links_total,
                  (SELECT COUNT(*)::INT FROM watched_channels) AS watched_channels_total,
                  (SELECT COUNT(*)::INT FROM watched_markets) AS watched_markets_total,
                  (
                    SELECT COUNT(*)::INT
                    FROM telegram_messages tm
                    JOIN watched_channels wc
                      ON wc.chat_id = tm.chat_id
                    WHERE COALESCE(tm.posted_at, tm.ingested_at, NOW()) >= NOW() - INTERVAL '24 hours'
                  ) AS messages_24h,
                  (
                    SELECT COUNT(*)::INT
                    FROM (
                      SELECT DISTINCT mmm.chat_id, mmm.message_id
                      FROM message_market_matches mmm
                      JOIN watched_links wl
                        ON wl.chat_id = mmm.chat_id
                       AND wl.market_id = mmm.market_id
                      JOIN telegram_messages tm
                        ON tm.chat_id = mmm.chat_id
                       AND tm.message_id = mmm.message_id
                      WHERE mmm.is_match = TRUE
                        AND COALESCE(tm.posted_at, tm.ingested_at, NOW()) >= NOW() - INTERVAL '24 hours'
                    ) matched_messages
                  ) AS matched_messages_24h,
                  (
                    SELECT COUNT(*)::INT
                    FROM market_activations ma
                    JOIN watched_markets wm
                      ON wm.market_id = ma.market_id
                    WHERE COALESCE(ma.activation_time, NOW()) >= NOW() - INTERVAL '24 hours'
                  ) AS activations_24h;
                """,
                (source_filter, source_filter, link_filter_all, normalized_link_source),
            )
            counts_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                WITH approved_markets AS (
                  SELECT DISTINCT ON (t.representative_market_id)
                    t.representative_market_id AS market_id,
                    t.source_file,
                    t.requested_name,
                    t.requested_bucket,
                    t.matched_group_slug,
                    t.matched_group_title,
                    t.matched_scope_label
                  FROM handpicked_market_targets t
                  WHERE t.match_status = 'matched'
                    AND t.representative_market_id IS NOT NULL
                    AND (%s = '' OR t.source_file = %s)
                  ORDER BY t.representative_market_id ASC, t.source_line_number ASC
                ),
                watched_links AS (
                  SELECT DISTINCT
                    cmm.market_id
                  FROM channel_market_map cmm
                  JOIN telegram_channels tc
                    ON tc.chat_id = cmm.chat_id
                  JOIN markets m
                    ON m.market_id = cmm.market_id
                  JOIN approved_markets am
                    ON am.market_id = cmm.market_id
                  WHERE cmm.link_status = 'active'
                    AND tc.is_active = TRUE
                    AND m.active = TRUE
                    AND m.closed = FALSE
                    AND (%s = TRUE OR cmm.link_source = %s)
                )
                SELECT
                  wl.market_id,
                  am.source_file,
                  am.requested_name,
                  am.requested_bucket,
                  am.matched_group_slug,
                  am.matched_group_title,
                  am.matched_scope_label,
                  m.slug,
                  m.question,
                  m.market_context
                FROM watched_links wl
                JOIN approved_markets am
                  ON am.market_id = wl.market_id
                JOIN markets m
                  ON m.market_id = wl.market_id
                ORDER BY COALESCE(am.requested_bucket, am.matched_scope_label, 'Other') ASC, am.requested_name ASC;
                """,
                (source_filter, source_filter, link_filter_all, normalized_link_source),
            )
            watched_market_rows = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                WITH approved_markets AS (
                  SELECT DISTINCT ON (t.representative_market_id)
                    t.representative_market_id AS market_id
                  FROM handpicked_market_targets t
                  WHERE t.match_status = 'matched'
                    AND t.representative_market_id IS NOT NULL
                    AND (%s = '' OR t.source_file = %s)
                  ORDER BY t.representative_market_id ASC, t.source_line_number ASC
                ),
                watched_channels AS (
                  SELECT DISTINCT
                    cmm.chat_id
                  FROM channel_market_map cmm
                  JOIN telegram_channels tc
                    ON tc.chat_id = cmm.chat_id
                  JOIN markets m
                    ON m.market_id = cmm.market_id
                  JOIN approved_markets am
                    ON am.market_id = cmm.market_id
                  WHERE cmm.link_status = 'active'
                    AND tc.is_active = TRUE
                    AND m.active = TRUE
                    AND m.closed = FALSE
                    AND (%s = TRUE OR cmm.link_source = %s)
                )
                SELECT
                  tm.chat_id,
                  tm.message_id,
                  tm.posted_at,
                  tm.ingested_at,
                  tm.text,
                  tm.has_media,
                  tm.raw_json,
                  tc.title AS channel_title,
                  tc.username AS channel_username,
                  tc.member_count
                FROM telegram_messages tm
                JOIN watched_channels wc
                  ON wc.chat_id = tm.chat_id
                JOIN telegram_channels tc
                  ON tc.chat_id = tm.chat_id
                ORDER BY COALESCE(tm.posted_at, tm.ingested_at) DESC NULLS LAST, tm.message_id DESC
                LIMIT %s;
                """,
                (source_filter, source_filter, link_filter_all, normalized_link_source, effective_message_limit),
            )
            recent_message_rows = [dict(row) for row in cur.fetchall()]

            chat_ids = sorted({int(row["chat_id"]) for row in recent_message_rows if row.get("chat_id") is not None})
            message_ids = sorted({int(row["message_id"]) for row in recent_message_rows if row.get("message_id") is not None})

            match_rows: list[dict[str, Any]] = []
            activation_rows: list[dict[str, Any]] = []
            if chat_ids and message_ids:
                cur.execute(
                    """
                    WITH approved_markets AS (
                      SELECT DISTINCT ON (t.representative_market_id)
                        t.representative_market_id AS market_id
                      FROM handpicked_market_targets t
                      WHERE t.match_status = 'matched'
                        AND t.representative_market_id IS NOT NULL
                        AND (%s = '' OR t.source_file = %s)
                      ORDER BY t.representative_market_id ASC, t.source_line_number ASC
                    ),
                    watched_links AS (
                      SELECT
                        cmm.chat_id,
                        cmm.market_id
                      FROM channel_market_map cmm
                      JOIN telegram_channels tc
                        ON tc.chat_id = cmm.chat_id
                      JOIN markets m
                        ON m.market_id = cmm.market_id
                      JOIN approved_markets am
                        ON am.market_id = cmm.market_id
                      WHERE cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                        AND m.active = TRUE
                        AND m.closed = FALSE
                        AND (%s = TRUE OR cmm.link_source = %s)
                    )
                    SELECT
                      mmm.chat_id,
                      mmm.message_id,
                      mmm.market_id,
                      mmm.is_match,
                      mmm.match_reason_short,
                      mmm.matcher_version,
                      mmm.raw_json
                    FROM message_market_matches mmm
                    JOIN watched_links wl
                      ON wl.chat_id = mmm.chat_id
                     AND wl.market_id = mmm.market_id
                    WHERE mmm.chat_id = ANY(%s)
                      AND mmm.message_id = ANY(%s);
                    """,
                    (
                        source_filter,
                        source_filter,
                        link_filter_all,
                        normalized_link_source,
                        chat_ids,
                        message_ids,
                    ),
                )
                match_rows = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    WITH approved_markets AS (
                      SELECT DISTINCT ON (t.representative_market_id)
                        t.representative_market_id AS market_id,
                        t.requested_name,
                        t.requested_bucket
                      FROM handpicked_market_targets t
                      WHERE t.match_status = 'matched'
                        AND t.representative_market_id IS NOT NULL
                        AND (%s = '' OR t.source_file = %s)
                      ORDER BY t.representative_market_id ASC, t.source_line_number ASC
                    ),
                    watched_markets AS (
                      SELECT DISTINCT
                        cmm.market_id
                      FROM channel_market_map cmm
                      JOIN telegram_channels tc
                        ON tc.chat_id = cmm.chat_id
                      JOIN markets m
                        ON m.market_id = cmm.market_id
                      JOIN approved_markets am
                        ON am.market_id = cmm.market_id
                      WHERE cmm.link_status = 'active'
                        AND tc.is_active = TRUE
                        AND m.active = TRUE
                        AND m.closed = FALSE
                        AND (%s = TRUE OR cmm.link_source = %s)
                    )
                    SELECT
                      ma.market_id,
                      ma.activation_time,
                      ma.trigger_chat_id AS chat_id,
                      ma.trigger_message_id AS message_id,
                      ma.activation_source,
                      ma.notes,
                      am.requested_name,
                      am.requested_bucket,
                      m.slug,
                      m.question,
                      tc.title AS channel_title,
                      tc.username AS channel_username
                    FROM market_activations ma
                    JOIN watched_markets wm
                      ON wm.market_id = ma.market_id
                    JOIN markets m
                      ON m.market_id = ma.market_id
                    LEFT JOIN approved_markets am
                      ON am.market_id = ma.market_id
                    LEFT JOIN telegram_channels tc
                      ON tc.chat_id = ma.trigger_chat_id
                    WHERE ma.trigger_chat_id = ANY(%s)
                      AND ma.trigger_message_id = ANY(%s)
                    ORDER BY ma.activation_time DESC NULLS LAST
                    LIMIT %s;
                    """,
                    (
                        source_filter,
                        source_filter,
                        link_filter_all,
                        normalized_link_source,
                        chat_ids,
                        message_ids,
                        effective_activation_limit,
                    ),
                )
                activation_rows = [dict(row) for row in cur.fetchall()]

    market_lookup: dict[str, dict[str, Any]] = {}
    bucket_counts: dict[str, int] = {}
    for row in watched_market_rows:
        market_id = str(row.get("market_id") or "").strip()
        if not market_id:
            continue
        label = str(row.get("requested_name") or row.get("matched_group_title") or row.get("question") or market_id)
        bucket = str(row.get("requested_bucket") or row.get("matched_scope_label") or "Other").strip() or "Other"
        market_lookup[market_id] = {
            "market_id": market_id,
            "label": label,
            "bucket": bucket,
            "group_slug": row.get("matched_group_slug"),
            "group_title": row.get("matched_group_title"),
            "question": row.get("question"),
            "slug": row.get("slug"),
            "market_context": row.get("market_context"),
            "source_file": row.get("source_file"),
            "public_url": f"https://polymarket.com/event/{row['slug']}" if row.get("slug") else None,
        }
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    match_by_key: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in match_rows:
        key = (int(row.get("chat_id") or 0), int(row.get("message_id") or 0))
        raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
        market = market_lookup.get(str(row.get("market_id") or "").strip(), {})
        match_by_key.setdefault(key, []).append(
            {
                "market_id": str(row.get("market_id") or ""),
                "market_label": market.get("label") or str(row.get("market_id") or ""),
                "bucket": market.get("bucket") or "Other",
                "is_match": bool(row.get("is_match")),
                "confidence": raw_json.get("confidence"),
                "reason_short": str(row.get("match_reason_short") or ""),
                "matcher_version": str(row.get("matcher_version") or ""),
                "public_url": market.get("public_url"),
            }
        )

    activations_by_key: dict[tuple[int, int], list[dict[str, Any]]] = {}
    formatted_activations: list[dict[str, Any]] = []
    for row in activation_rows:
        key = (int(row.get("chat_id") or 0), int(row.get("message_id") or 0))
        item = {
            "market_id": str(row.get("market_id") or ""),
            "market_label": str(row.get("requested_name") or row.get("question") or row.get("market_id") or ""),
            "bucket": str(row.get("requested_bucket") or "Other"),
            "activation_time": row.get("activation_time"),
            "activation_source": row.get("activation_source"),
            "notes": str(row.get("notes") or ""),
            "slug": row.get("slug"),
            "public_url": f"https://polymarket.com/event/{row['slug']}" if row.get("slug") else None,
            "channel_title": row.get("channel_title"),
            "channel_username": row.get("channel_username"),
            "chat_id": int(row.get("chat_id") or 0),
            "message_id": int(row.get("message_id") or 0),
        }
        activations_by_key.setdefault(key, []).append(item)
        formatted_activations.append(item)

    messages: list[dict[str, Any]] = []
    for row in recent_message_rows:
        key = (int(row.get("chat_id") or 0), int(row.get("message_id") or 0))
        raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
        matches = match_by_key.get(key, [])
        positive_matches = sorted(
            [item for item in matches if bool(item.get("is_match"))],
            key=lambda item: (
                -(float(item.get("confidence")) if item.get("confidence") is not None else -1.0),
                str(item.get("market_label") or "").lower(),
            ),
        )
        activations = activations_by_key.get(key, [])
        username = str(row.get("channel_username") or "").strip()
        messages.append(
            {
                "chat_id": int(row.get("chat_id") or 0),
                "message_id": int(row.get("message_id") or 0),
                "posted_at": row.get("posted_at"),
                "ingested_at": row.get("ingested_at"),
                "channel_title": str(row.get("channel_title") or row.get("chat_id") or ""),
                "channel_username": username or None,
                "member_count": int(row.get("member_count") or 0),
                "text": str(row.get("text") or ""),
                "has_media": bool(row.get("has_media")),
                "content_type": raw_json.get("content_type"),
                "public_url": raw_json.get("public_url") or (f"https://t.me/{username}/{int(row.get('message_id') or 0)}" if username else None),
                "evaluated_market_count": len(matches),
                "matched_market_count": len(positive_matches),
                "unmatched_market_count": max(0, len(matches) - len(positive_matches)),
                "has_activation": bool(activations),
                "matched_markets": positive_matches,
                "activations": activations,
            }
        )

    now_utc = datetime.now(timezone.utc)
    return {
        "generated_at": now_utc,
        "filters": {
            "source_file": source_filter,
            "source_label": Path(source_filter).name if source_filter else None,
            "link_source": normalized_link_source or "all",
            "agent_name": runtime.get("agent_name"),
        },
        "counts": {
            "watched_channels_total": int(counts_row.get("watched_channels_total") or 0),
            "watched_markets_total": int(counts_row.get("watched_markets_total") or 0),
            "links_total": int(counts_row.get("links_total") or 0),
            "messages_24h": int(counts_row.get("messages_24h") or 0),
            "matched_messages_24h": int(counts_row.get("matched_messages_24h") or 0),
            "activations_24h": int(counts_row.get("activations_24h") or 0),
            "loaded_messages": len(messages),
            "loaded_activations": len(formatted_activations),
        },
        "runtime": runtime,
        "bucket_counts": [
            {"label": label, "market_count": count}
            for label, count in sorted(bucket_counts.items(), key=lambda item: (-item[1], item[0].lower()))
        ],
        "watched_markets": sorted(
            market_lookup.values(),
            key=lambda item: (str(item.get("bucket") or "").lower(), str(item.get("label") or "").lower()),
        ),
        "messages": messages,
        "recent_activations": formatted_activations,
    }


def _normalize_handpicked_filter_status(value: str | None) -> str:
    normalized = str(value or "review").strip().lower() or "review"
    if normalized not in {"all", "review", "matched", "low_confidence", "unmatched"}:
        raise ValueError(f"Unsupported handpicked review status: {value}")
    return normalized


def _normalize_handpicked_update_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value or "").strip().lower()
    if normalized in {"", "none"}:
        return None
    if normalized not in {"matched", "low_confidence", "unmatched"}:
        raise ValueError("match_status must be one of: matched, low_confidence, unmatched")
    return normalized


def _fetch_market_group_lookup(
    conn: psycopg.Connection[Any],
    *,
    group_slugs: list[str],
) -> dict[str, dict[str, Any]]:
    unique_group_slugs = sorted({str(item or "").strip() for item in group_slugs if str(item or "").strip()})
    if not unique_group_slugs:
        return {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
              mg.group_slug,
              mg.group_title,
              mg.scope_label,
              mg.market_count,
              mg.tradable_market_count,
              mg.sample_questions,
              mg.source_urls,
              mg.representative_market_id,
              rm.slug AS representative_slug,
              rm.question AS representative_question,
              rm.description AS representative_description,
              rm.market_context AS representative_context,
              rm.end_date AS representative_end_date
            FROM market_groups mg
            LEFT JOIN markets rm
              ON rm.market_id = mg.representative_market_id
            WHERE mg.group_slug = ANY(%s);
            """,
            (unique_group_slugs,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return {
        str(row.get("group_slug") or ""): {
            **row,
            "sample_questions": row.get("sample_questions") if isinstance(row.get("sample_questions"), list) else [],
            "source_urls": row.get("source_urls") if isinstance(row.get("source_urls"), list) else [],
            "public_url": (
                f"https://polymarket.com/event/{row['representative_slug']}"
                if row.get("representative_slug")
                else None
            ),
        }
        for row in rows
    }


def _build_handpicked_resolved_group(item: dict[str, Any]) -> dict[str, Any] | None:
    if not item.get("representative_market_id"):
        return None
    representative_slug = item.get("resolved_market_slug")
    return {
        "group_slug": item.get("matched_group_slug"),
        "group_title": item.get("matched_group_title") or item.get("resolved_group_title") or item.get("resolved_market_question"),
        "scope_label": item.get("matched_scope_label") or item.get("resolved_scope_label") or "Manual Raw Market",
        "market_count": int(item.get("matched_market_count") or item.get("resolved_group_market_count") or 1),
        "representative_market_id": item.get("representative_market_id"),
        "representative_slug": representative_slug,
        "representative_question": item.get("resolved_market_question"),
        "representative_description": item.get("resolved_market_description"),
        "representative_context": item.get("resolved_market_context"),
        "representative_end_date": item.get("resolved_market_end_date"),
        "sample_questions": item.get("resolved_sample_questions") if isinstance(item.get("resolved_sample_questions"), list) else [],
        "source_urls": item.get("resolved_source_urls") if isinstance(item.get("resolved_source_urls"), list) else [],
        "public_url": f"https://polymarket.com/event/{representative_slug}" if representative_slug else None,
        "resolution_kind": "group" if item.get("matched_group_slug") else "raw_market",
    }


def _fetch_handpicked_review_snapshot(
    *,
    db_url: str,
    status: str,
    limit: int,
    search: str | None,
    source_file: str | None,
) -> dict[str, Any]:
    normalized_status = _normalize_handpicked_filter_status(status)
    effective_limit = max(1, min(int(limit), 500))
    search_text = str(search or "").strip()
    search_pattern = f"%{search_text}%"
    source_filter = str(source_file or "").strip()

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS total_targets,
                  COUNT(*) FILTER (WHERE match_status = 'matched')::INT AS matched_total,
                  COUNT(*) FILTER (WHERE match_status = 'low_confidence')::INT AS low_confidence_total,
                  COUNT(*) FILTER (WHERE match_status = 'unmatched')::INT AS unmatched_total,
                  COUNT(DISTINCT source_file)::INT AS source_files_total,
                  MAX(updated_at) AS latest_review_at
                FROM handpicked_market_targets;
                """
            )
            totals_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  source_file,
                  COUNT(*)::INT AS total_rows,
                  COUNT(*) FILTER (WHERE match_status = 'matched')::INT AS matched_rows,
                  COUNT(*) FILTER (WHERE match_status = 'low_confidence')::INT AS low_confidence_rows,
                  COUNT(*) FILTER (WHERE match_status = 'unmatched')::INT AS unmatched_rows,
                  MAX(updated_at) AS latest_updated_at
                FROM handpicked_market_targets
                GROUP BY source_file
                ORDER BY latest_updated_at DESC NULLS LAST, source_file ASC;
                """
            )
            source_rows = [dict(row) for row in cur.fetchall()]

            filter_params = (
                source_filter,
                source_filter,
                normalized_status,
                normalized_status,
                normalized_status,
                search_text,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
            )

            cur.execute(
                """
                SELECT
                  COUNT(*)::INT AS visible_targets,
                  COUNT(*) FILTER (WHERE t.match_status = 'matched')::INT AS visible_matched,
                  COUNT(*) FILTER (WHERE t.match_status = 'low_confidence')::INT AS visible_low_confidence,
                  COUNT(*) FILTER (WHERE t.match_status = 'unmatched')::INT AS visible_unmatched
                FROM handpicked_market_targets t
                WHERE (%s = '' OR t.source_file = %s)
                  AND (
                    %s = 'all'
                    OR (%s = 'review' AND t.match_status IN ('low_confidence', 'unmatched'))
                    OR t.match_status = %s
                  )
                  AND (
                    %s = ''
                    OR COALESCE(t.requested_name, '') ILIKE %s
                    OR COALESCE(t.raw_line, '') ILIKE %s
                    OR COALESCE(t.matched_group_slug, '') ILIKE %s
                    OR COALESCE(t.matched_group_title, '') ILIKE %s
                    OR COALESCE(t.candidate_payload::text, '') ILIKE %s
                  );
                """,
                filter_params,
            )
            visible_row = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                  t.target_id,
                  t.source_file,
                  t.source_line_number,
                  t.raw_line,
                  t.requested_name,
                  t.requested_bucket,
                  t.requested_locator,
                  t.match_status,
                  t.matched_group_slug,
                  t.matched_group_title,
                  t.matched_scope_label,
                  t.representative_market_id,
                  t.matched_market_count,
                  t.match_score,
                  t.match_method,
                  t.candidate_payload,
                  t.notes,
                  t.imported_at,
                  t.updated_at,
                  mg.group_title AS resolved_group_title,
                  mg.scope_label AS resolved_scope_label,
                  mg.market_count AS resolved_group_market_count,
                  mg.sample_questions AS resolved_sample_questions,
                  mg.source_urls AS resolved_source_urls,
                  rm.slug AS resolved_market_slug,
                  rm.question AS resolved_market_question,
                  rm.description AS resolved_market_description,
                  rm.market_context AS resolved_market_context,
                  rm.end_date AS resolved_market_end_date
                FROM handpicked_market_targets t
                LEFT JOIN market_groups mg
                  ON mg.group_slug = t.matched_group_slug
                LEFT JOIN markets rm
                  ON rm.market_id = t.representative_market_id
                WHERE (%s = '' OR t.source_file = %s)
                  AND (
                    %s = 'all'
                    OR (%s = 'review' AND t.match_status IN ('low_confidence', 'unmatched'))
                    OR t.match_status = %s
                  )
                  AND (
                    %s = ''
                    OR COALESCE(t.requested_name, '') ILIKE %s
                    OR COALESCE(t.raw_line, '') ILIKE %s
                    OR COALESCE(t.matched_group_slug, '') ILIKE %s
                    OR COALESCE(t.matched_group_title, '') ILIKE %s
                    OR COALESCE(t.candidate_payload::text, '') ILIKE %s
                  )
                ORDER BY
                  CASE t.match_status
                    WHEN 'unmatched' THEN 0
                    WHEN 'low_confidence' THEN 1
                    ELSE 2
                  END ASC,
                  COALESCE(t.match_score, 0) DESC,
                  t.source_line_number ASC
                LIMIT %s;
                """,
                (*filter_params, effective_limit),
            )
            target_rows = [dict(row) for row in cur.fetchall()]

        candidate_group_slugs: set[str] = set()
        for row in target_rows:
            payload = row.get("candidate_payload")
            if not isinstance(payload, list):
                continue
            for candidate in payload:
                if isinstance(candidate, dict) and candidate.get("group_slug"):
                    candidate_group_slugs.add(str(candidate["group_slug"]))
        group_lookup = _fetch_market_group_lookup(conn, group_slugs=list(candidate_group_slugs))

    normalized_targets: list[dict[str, Any]] = []
    for row in target_rows:
        raw_candidates = row.get("candidate_payload")
        candidates: list[dict[str, Any]] = []
        if isinstance(raw_candidates, list):
            for candidate in raw_candidates:
                if not isinstance(candidate, dict):
                    continue
                group_slug = str(candidate.get("group_slug") or "")
                lookup = group_lookup.get(group_slug, {})
                representative_slug = lookup.get("representative_slug")
                candidates.append(
                    {
                        **candidate,
                        "group_title": lookup.get("group_title") or candidate.get("group_title"),
                        "scope_label": lookup.get("scope_label") or candidate.get("scope_label"),
                        "market_count": int(lookup.get("market_count") or candidate.get("market_count") or 0),
                        "tradable_market_count": int(lookup.get("tradable_market_count") or 0),
                        "representative_market_id": lookup.get("representative_market_id") or candidate.get("representative_market_id"),
                        "representative_slug": representative_slug,
                        "representative_question": lookup.get("representative_question"),
                        "representative_description": lookup.get("representative_description"),
                        "representative_context": lookup.get("representative_context"),
                        "representative_end_date": lookup.get("representative_end_date"),
                        "sample_questions": lookup.get("sample_questions") or [],
                        "source_urls": lookup.get("source_urls") or [],
                        "public_url": f"https://polymarket.com/event/{representative_slug}" if representative_slug else None,
                    }
                )
        normalized_targets.append(
            {
                **row,
                "candidate_payload": candidates,
                "resolved_group": _build_handpicked_resolved_group(row),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc),
        "storage": {
            "targets_table": "public.handpicked_market_targets",
            "groups_table": "public.market_groups",
            "markets_table": "public.markets",
        },
        "filters": {
            "status": normalized_status,
            "search": search_text,
            "source_file": source_filter,
            "limit": effective_limit,
        },
        "counts": {
            "total_targets": int(totals_row.get("total_targets") or 0),
            "matched_total": int(totals_row.get("matched_total") or 0),
            "low_confidence_total": int(totals_row.get("low_confidence_total") or 0),
            "unmatched_total": int(totals_row.get("unmatched_total") or 0),
            "review_total": int(totals_row.get("low_confidence_total") or 0) + int(totals_row.get("unmatched_total") or 0),
            "visible_targets": int(visible_row.get("visible_targets") or 0),
            "visible_matched": int(visible_row.get("visible_matched") or 0),
            "visible_low_confidence": int(visible_row.get("visible_low_confidence") or 0),
            "visible_unmatched": int(visible_row.get("visible_unmatched") or 0),
            "source_files_total": int(totals_row.get("source_files_total") or 0),
            "latest_review_at": totals_row.get("latest_review_at"),
        },
        "source_files": source_rows,
        "targets": normalized_targets,
    }


def _search_handpicked_resolution_options(
    *,
    db_url: str,
    search: str,
    limit: int,
) -> dict[str, Any]:
    search_text = str(search or "").strip()
    effective_limit = max(1, min(int(limit), 100))
    if not search_text:
        return {
            "generated_at": datetime.now(timezone.utc),
            "search": search_text,
            "options": [],
        }

    search_pattern = f"%{search_text}%"
    search_prefix = f"{search_text}%"
    normalized_search = search_text.lower()

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  mg.group_slug,
                  mg.group_title,
                  mg.scope_label,
                  mg.market_count,
                  mg.tradable_market_count,
                  mg.sample_questions,
                  mg.representative_market_id,
                  rm.slug AS representative_slug,
                  rm.question AS representative_question,
                  rm.end_date AS representative_end_date
                FROM market_groups mg
                LEFT JOIN markets rm
                  ON rm.market_id = mg.representative_market_id
                WHERE COALESCE(mg.group_slug, '') ILIKE %s
                   OR COALESCE(mg.group_title, '') ILIKE %s
                   OR COALESCE(mg.sample_questions::text, '') ILIKE %s
                   OR COALESCE(rm.question, '') ILIKE %s
                ORDER BY
                  CASE
                    WHEN lower(COALESCE(mg.group_slug, '')) = %s THEN 0
                    WHEN lower(COALESCE(mg.group_title, '')) = %s THEN 0
                    WHEN lower(COALESCE(rm.question, '')) = %s THEN 0
                    WHEN lower(COALESCE(mg.group_slug, '')) LIKE lower(%s) THEN 1
                    WHEN lower(COALESCE(mg.group_title, '')) LIKE lower(%s) THEN 1
                    WHEN lower(COALESCE(rm.question, '')) LIKE lower(%s) THEN 1
                    ELSE 2
                  END ASC,
                  mg.tradable_market_count DESC,
                  mg.group_slug ASC
                LIMIT %s;
                """,
                (
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    normalized_search,
                    normalized_search,
                    normalized_search,
                    search_prefix.lower(),
                    search_prefix.lower(),
                    search_prefix.lower(),
                    effective_limit,
                ),
            )
            group_rows = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  m.market_id,
                  m.event_slug,
                  m.slug,
                  m.question,
                  m.end_date,
                  m.last_seen_at,
                  mg.group_slug,
                  mg.group_title,
                  mg.scope_label
                FROM markets m
                LEFT JOIN market_groups mg
                  ON mg.group_slug = m.event_slug
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND COALESCE(m.archived, FALSE) = FALSE
                  AND (
                    COALESCE(m.slug, '') ILIKE %s
                    OR COALESCE(m.event_slug, '') ILIKE %s
                    OR COALESCE(m.question, '') ILIKE %s
                  )
                ORDER BY
                  CASE
                    WHEN lower(COALESCE(m.slug, '')) = %s THEN 0
                    WHEN lower(COALESCE(m.event_slug, '')) = %s THEN 0
                    WHEN lower(COALESCE(m.question, '')) = %s THEN 0
                    WHEN lower(COALESCE(m.slug, '')) LIKE lower(%s) THEN 1
                    WHEN lower(COALESCE(m.event_slug, '')) LIKE lower(%s) THEN 1
                    WHEN lower(COALESCE(m.question, '')) LIKE lower(%s) THEN 1
                    ELSE 2
                  END ASC,
                  m.end_date ASC NULLS LAST,
                  m.last_seen_at DESC NULLS LAST
                LIMIT %s;
                """,
                (
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    normalized_search,
                    normalized_search,
                    normalized_search,
                    search_prefix.lower(),
                    search_prefix.lower(),
                    search_prefix.lower(),
                    effective_limit * 3,
                ),
            )
            raw_rows = [dict(row) for row in cur.fetchall()]

    group_slugs = {str(row.get("group_slug") or "") for row in group_rows if row.get("group_slug")}
    options: list[dict[str, Any]] = []
    for row in group_rows:
        representative_slug = row.get("representative_slug")
        options.append(
            {
                "kind": "group",
                "group_slug": row.get("group_slug"),
                "market_id": row.get("representative_market_id"),
                "title": row.get("group_title"),
                "scope_label": row.get("scope_label"),
                "market_count": int(row.get("market_count") or 0),
                "tradable_market_count": int(row.get("tradable_market_count") or 0),
                "question": row.get("representative_question"),
                "sample_questions": row.get("sample_questions") if isinstance(row.get("sample_questions"), list) else [],
                "public_url": f"https://polymarket.com/event/{representative_slug}" if representative_slug else None,
            }
        )

    for row in raw_rows:
        event_slug = str(row.get("event_slug") or "")
        if event_slug and event_slug in group_slugs:
            continue
        options.append(
            {
                "kind": "raw_market",
                "group_slug": row.get("group_slug"),
                "market_id": row.get("market_id"),
                "title": row.get("question") or row.get("slug") or row.get("event_slug"),
                "scope_label": row.get("scope_label") or "Manual Raw Market",
                "market_count": 1,
                "tradable_market_count": 1,
                "question": row.get("question"),
                "sample_questions": [],
                "public_url": f"https://polymarket.com/event/{row['slug']}" if row.get("slug") else None,
            }
        )
        if len(options) >= effective_limit:
            break

    return {
        "generated_at": datetime.now(timezone.utc),
        "search": search_text,
        "options": options[:effective_limit],
    }


def _apply_handpicked_target_update(
    *,
    db_url: str,
    target_id: int,
    match_status: str | None,
    matched_group_slug: str | None,
    matched_market_id: str | None,
    note: str | None,
) -> dict[str, Any] | None:
    normalized_status = _normalize_handpicked_update_status(match_status)
    normalized_group_slug = str(matched_group_slug or "").strip() or None
    normalized_market_id = str(matched_market_id or "").strip() or None
    if normalized_group_slug and normalized_market_id:
        raise ValueError("Provide either matched_group_slug or matched_market_id, not both.")

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM handpicked_market_targets
                WHERE target_id = %s;
                """,
                (int(target_id),),
            )
            current = dict(cur.fetchone() or {})
            if not current:
                return None

            next_status = normalized_status or str(current.get("match_status") or "unmatched")
            next_group_slug = current.get("matched_group_slug")
            next_group_title = current.get("matched_group_title")
            next_scope_label = current.get("matched_scope_label")
            next_representative_market_id = current.get("representative_market_id")
            next_market_count = current.get("matched_market_count")
            next_match_score = current.get("match_score")
            next_match_method = current.get("match_method")
            next_note = note if note is not None else current.get("notes")

            if normalized_group_slug:
                cur.execute(
                    """
                    SELECT
                      mg.group_slug,
                      mg.group_title,
                      mg.scope_label,
                      mg.market_count,
                      mg.representative_market_id
                    FROM market_groups mg
                    WHERE mg.group_slug = %s;
                    """,
                    (normalized_group_slug,),
                )
                group_row = dict(cur.fetchone() or {})
                if not group_row:
                    raise ValueError(f"Unknown market group slug: {normalized_group_slug}")
                next_status = normalized_status or "matched"
                next_group_slug = group_row.get("group_slug")
                next_group_title = group_row.get("group_title")
                next_scope_label = group_row.get("scope_label")
                next_representative_market_id = group_row.get("representative_market_id")
                next_market_count = int(group_row.get("market_count") or 0)
                next_match_score = 1.0
                next_match_method = "manual_review"
            elif normalized_market_id:
                cur.execute(
                    """
                    SELECT
                      m.market_id,
                      m.event_slug,
                      m.question,
                      mg.group_slug,
                      mg.group_title,
                      mg.scope_label,
                      mg.market_count
                    FROM markets m
                    LEFT JOIN market_groups mg
                      ON mg.group_slug = m.event_slug
                    WHERE m.market_id = %s;
                    """,
                    (normalized_market_id,),
                )
                market_row = dict(cur.fetchone() or {})
                if not market_row:
                    raise ValueError(f"Unknown market_id: {normalized_market_id}")
                next_status = normalized_status or "matched"
                next_group_slug = market_row.get("group_slug")
                next_group_title = market_row.get("group_title") or market_row.get("question")
                next_scope_label = market_row.get("scope_label") or "Manual Raw Market"
                next_representative_market_id = market_row.get("market_id")
                next_market_count = int(market_row.get("market_count") or 1)
                next_match_score = 1.0
                next_match_method = "manual_raw_market"
            elif next_status == "unmatched":
                next_group_slug = None
                next_group_title = None
                next_scope_label = None
                next_representative_market_id = None
                next_market_count = None
                next_match_score = None
                next_match_method = "manual_unmatched"
            elif normalized_status in {"matched", "low_confidence"} and not current.get("representative_market_id"):
                raise ValueError("A resolved market group or market_id is required before setting a resolved status.")

            cur.execute(
                """
                UPDATE handpicked_market_targets
                SET
                  match_status = %s,
                  matched_group_slug = %s,
                  matched_group_title = %s,
                  matched_scope_label = %s,
                  representative_market_id = %s,
                  matched_market_count = %s,
                  match_score = %s,
                  match_method = %s,
                  notes = %s,
                  updated_at = NOW()
                WHERE target_id = %s;
                """,
                (
                    next_status,
                    next_group_slug,
                    next_group_title,
                    next_scope_label,
                    next_representative_market_id,
                    next_market_count,
                    next_match_score,
                    next_match_method,
                    next_note,
                    int(target_id),
                ),
            )
        conn.commit()

    return {
        "target_id": int(target_id),
        "match_status": next_status,
        "matched_group_slug": next_group_slug,
        "representative_market_id": next_representative_market_id,
        "notes": next_note,
        "updated_at": datetime.now(timezone.utc),
    }


def _fetch_agent_runtime_snapshot(
    *,
    db_url: str,
    agent_name: str,
    event_limit: int,
) -> dict[str, Any]:
    normalized_agent = str(agent_name or "").strip() or "telegram-market-agent"
    effective_limit = max(1, min(int(event_limit), 500))

    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runtime_status (
                  agent_name TEXT PRIMARY KEY,
                  heartbeat_at TIMESTAMPTZ,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  status_json JSONB NOT NULL DEFAULT '{}'::jsonb
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runtime_events (
                  event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                  agent_name TEXT NOT NULL,
                  event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  level TEXT NOT NULL DEFAULT 'info',
                  stage TEXT,
                  event_type TEXT NOT NULL DEFAULT 'event',
                  market_id TEXT,
                  message TEXT NOT NULL DEFAULT '',
                  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
                );
                """
            )
            cur.execute(
                """
                SELECT
                  agent_name,
                  heartbeat_at,
                  updated_at,
                  status_json
                FROM agent_runtime_status
                WHERE agent_name = %s
                LIMIT 1;
                """,
                (normalized_agent,),
            )
            status_row = cur.fetchone() or {}
            cur.execute(
                """
                SELECT
                  event_id,
                  event_time,
                  level,
                  stage,
                  event_type,
                  market_id,
                  message,
                  payload_json
                FROM agent_runtime_events
                WHERE agent_name = %s
                ORDER BY event_time DESC
                LIMIT %s;
                """,
                (normalized_agent, effective_limit),
            )
            events = [dict(row) for row in cur.fetchall()]

    now_utc = datetime.now(timezone.utc)
    heartbeat_at = status_row.get("heartbeat_at")
    stale_seconds = None
    if isinstance(heartbeat_at, datetime):
        stale_seconds = max(0.0, (now_utc - heartbeat_at).total_seconds())

    status_json = status_row.get("status_json") if isinstance(status_row.get("status_json"), dict) else {}
    current_market_id = str(status_json.get("current_market_id") or "").strip() or None
    current_market_slug = str(status_json.get("current_market_slug") or "").strip() or None
    current_market_question = str(status_json.get("current_market_question") or "").strip() or None
    current_market_index = status_json.get("current_market_index")
    current_market_total = status_json.get("current_market_total")
    progress_ratio = None
    try:
        idx = float(current_market_index) if current_market_index is not None else None
        total = float(current_market_total) if current_market_total is not None else None
        if idx is not None and total and total > 0:
            progress_ratio = max(0.0, min(1.0, idx / total))
    except Exception:
        progress_ratio = None

    return {
        "generated_at": now_utc,
        "agent_name": normalized_agent,
        "status": {
            "agent_name": status_row.get("agent_name"),
            "heartbeat_at": heartbeat_at,
            "updated_at": status_row.get("updated_at"),
            "stale_seconds": stale_seconds,
            "stage": status_json.get("stage"),
            "state": status_json.get("state"),
            "hostname": status_json.get("hostname"),
            "pid": status_json.get("pid"),
            "last_error": status_json.get("last_error"),
            "discover": {
                "started_at": status_json.get("discover_cycle_started_at"),
                "completed_at": status_json.get("discover_cycle_completed_at"),
                "markets_considered": status_json.get("discover_markets_considered"),
                "markets_updated": status_json.get("discover_markets_updated"),
                "links_written": status_json.get("discover_links_written"),
                "api_errors": status_json.get("discover_api_errors"),
                "elapsed_ms": status_json.get("discover_elapsed_ms"),
            },
            "listener": {
                "started_at": status_json.get("listener_cycle_started_at"),
                "completed_at": status_json.get("listener_cycle_completed_at"),
                "channels_polled": status_json.get("listener_channels_polled"),
                "new_messages": status_json.get("listener_new_messages"),
                "fetch_errors": status_json.get("listener_fetch_errors"),
                "matched_pairs": status_json.get("listener_matched_pairs"),
                "activations_inserted": status_json.get("listener_activations_inserted"),
                "elapsed_ms": status_json.get("listener_elapsed_ms"),
            },
            "current_market": {
                "market_id": current_market_id,
                "slug": current_market_slug,
                "question": current_market_question,
                "index": current_market_index,
                "total": current_market_total,
                "progress_ratio": progress_ratio,
                "detail": status_json.get("current_market_detail"),
            },
            "raw": status_json,
        },
        "events": events,
        "event_count": len(events),
    }


def _fetch_graph_snapshot(
    *,
    db_url: str,
    market_limit: int,
    channel_limit: int,
    edge_limit: int,
    track_now_only: bool,
    min_channel_members: int,
    min_channel_relevance: float,
) -> dict[str, Any]:
    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH latest_analysis AS (
                  SELECT DISTINCT ON (ma.market_id)
                    ma.market_id,
                    ma.classification,
                    ma.reason_json,
                    ma.local_score AS analysis_local_score,
                    ma.analyzed_at
                  FROM market_analysis ma
                  ORDER BY ma.market_id, ma.analyzed_at DESC
                )
                SELECT
                  m.market_id,
                  m.slug,
                  m.question,
                  m.rules_text,
                  m.market_context,
                  m.market_archetype,
                  m.local_score,
                  m.high_competition,
                  m.last_seen_at,
                  COALESCE(latest_analysis.classification, 'unclassified') AS classification,
                  latest_analysis.reason_json AS analysis_reason_json,
                  COALESCE(latest_analysis.analysis_local_score, m.local_score) AS analysis_local_score,
                  COALESCE(
                    (
                      SELECT COUNT(*)::INT
                      FROM channel_market_map cmm
                      WHERE cmm.market_id = m.market_id
                        AND cmm.link_status = 'active'
                    ),
                    0
                  ) AS mapped_channels
                FROM markets m
                LEFT JOIN latest_analysis ON latest_analysis.market_id = m.market_id
                WHERE m.active = TRUE
                  AND m.closed = FALSE
                  AND (
                    %s = FALSE
                    OR COALESCE(latest_analysis.classification, '') = 'track_now'
                  )
                ORDER BY
                  COALESCE(latest_analysis.analysis_local_score, m.local_score) DESC NULLS LAST,
                  m.last_seen_at DESC
                LIMIT %s;
                """,
                (track_now_only, market_limit),
            )
            markets = [dict(row) for row in cur.fetchall()]

            if not markets:
                return {
                    "meta": {
                        "generated_at": datetime.now(timezone.utc),
                        "market_count": 0,
                        "channel_count": 0,
                        "edge_count": 0,
                        "track_now_only": track_now_only,
                        "min_channel_members": int(min_channel_members),
                        "min_channel_relevance": float(min_channel_relevance),
                    },
                    "markets": [],
                    "channels": [],
                    "edges": [],
                }

            market_ids = [str(item["market_id"]) for item in markets]
            market_profiles = {
                str(item["market_id"]): build_market_channel_profile(item)
                for item in markets
            }
            cur.execute(
                """
                SELECT
                  cmm.market_id,
                  cmm.chat_id,
                  cmm.link_source,
                  cmm.priority_rank,
                  cmm.updated_at,
                  tc.title,
                  tc.username,
                  tc.description,
                  tc.trust_weight,
                  tc.member_count,
                  tc.last_seen_at,
                  tc.tags_json,
                  tc.notes
                FROM channel_market_map cmm
                JOIN telegram_channels tc ON tc.chat_id = cmm.chat_id
                WHERE cmm.link_status = 'active'
                  AND tc.is_active = TRUE
                  AND cmm.market_id = ANY(%s)
                ORDER BY cmm.updated_at DESC
                LIMIT %s;
                """,
                (market_ids, edge_limit),
            )
            edge_rows = [dict(row) for row in cur.fetchall()]

            channel_metrics: dict[int, dict[str, Any]] = {}
            filtered_edges: list[dict[str, Any]] = []
            for row in edge_rows:
                member_count = row.get("member_count")
                if member_count is None or int(member_count) < int(min_channel_members):
                    continue

                market_id = str(row["market_id"])
                profile = market_profiles.get(market_id)
                if profile is None:
                    continue
                relevance = evaluate_channel_relevance(
                    row,
                    profile,
                    min_score=min_channel_relevance,
                )
                if not relevance.is_relevant:
                    continue

                chat_id = int(row["chat_id"])
                metrics = channel_metrics.setdefault(
                    chat_id,
                    {
                        "chat_id": chat_id,
                        "title": row["title"],
                        "username": row.get("username"),
                        "description": row.get("description"),
                        "trust_weight": row.get("trust_weight"),
                        "member_count": row.get("member_count"),
                        "last_seen_at": row.get("last_seen_at"),
                        "tags_json": row.get("tags_json") or [],
                        "notes": row.get("notes") or "",
                        "mapped_markets": 0,
                        "best_relevance_score": 0.0,
                    },
                )
                metrics["mapped_markets"] += 1
                metrics["best_relevance_score"] = max(
                    float(metrics.get("best_relevance_score") or 0.0),
                    float(relevance.score),
                )
                filtered_edges.append(
                    {
                        "market_id": market_id,
                        "chat_id": chat_id,
                        "link_source": row.get("link_source"),
                        "priority_rank": row.get("priority_rank"),
                        "updated_at": row.get("updated_at"),
                        "relevance_score": relevance.score,
                        "relevance_label": relevance.label,
                        "relevance_reason": relevance.reason,
                    }
                )

            ranked_channel_ids = [
                chat_id
                for chat_id, _ in sorted(
                    channel_metrics.items(),
                    key=lambda pair: (
                        -int(pair[1]["mapped_markets"]),
                        -float(pair[1]["best_relevance_score"] or 0.0),
                        -(pair[1]["member_count"] or 0),
                        str(pair[1]["title"]).lower(),
                    ),
                )
            ]
            selected_channel_ids = set(ranked_channel_ids[:channel_limit])

            channels = [
                channel_metrics[chat_id]
                for chat_id in ranked_channel_ids
                if chat_id in selected_channel_ids
            ]

            filtered_edges = [
                edge
                for edge in filtered_edges
                if int(edge["chat_id"]) in selected_channel_ids
            ]

            if selected_channel_ids:
                cur.execute(
                    """
                    SELECT DISTINCT ON (tm.chat_id)
                      tm.chat_id,
                      tm.message_id,
                      tm.posted_at,
                      tm.text
                    FROM telegram_messages tm
                    WHERE tm.chat_id = ANY(%s)
                    ORDER BY tm.chat_id, tm.posted_at DESC NULLS LAST, tm.message_id DESC;
                    """,
                    (list(selected_channel_ids),),
                )
                latest_message_rows = [dict(row) for row in cur.fetchall()]
            else:
                latest_message_rows = []

            message_by_chat = {
                int(row["chat_id"]): {
                    "message_id": int(row["message_id"]),
                    "posted_at": row.get("posted_at"),
                    "text": row.get("text") or "",
                }
                for row in latest_message_rows
            }
            for channel in channels:
                channel["last_message"] = message_by_chat.get(int(channel["chat_id"]))

    return {
                "meta": {
                    "generated_at": datetime.now(timezone.utc),
                    "market_count": len(markets),
                    "channel_count": len(channels),
                    "edge_count": len(filtered_edges),
                    "track_now_only": track_now_only,
                    "min_channel_members": int(min_channel_members),
                    "min_channel_relevance": float(min_channel_relevance),
                },
                "markets": markets,
                "channels": channels,
                "edges": filtered_edges,
            }
