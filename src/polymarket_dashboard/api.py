from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.polymarket.config import PolymarketConfig
from src.polymarket.discovery_service import PolymarketDiscoveryService
from src.polymarket.gamma_client import GammaMarketsClient


def create_app(
    config: Optional[PolymarketConfig] = None,
    service: Optional[PolymarketDiscoveryService] = None,
) -> FastAPI:
    resolved_config = config or PolymarketConfig.from_env()
    resolved_service = service or PolymarketDiscoveryService(GammaMarketsClient(resolved_config))

    template_dir = Path(__file__).resolve().parent / "templates"
    templates = Jinja2Templates(directory=str(template_dir))

    app = FastAPI(title="Polymarket Discovery Dashboard")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "default_limit": 100,
                "default_offset": 0,
                "default_pool_size": 200,
                "default_sample_size": 10,
                "gamma_base_url": resolved_config.gamma_base_url,
            },
        )

    @app.get("/api/health")
    async def api_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "gamma_base_url": resolved_config.gamma_base_url,
        }

    @app.get("/api/markets")
    async def api_markets(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        active: Optional[str] = Query(default=None),
        closed: Optional[str] = Query(default=None),
        archived: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None, max_length=300),
        tag_id: Optional[int] = Query(default=None),
    ) -> dict[str, Any]:
        active_bool = _parse_optional_bool("active", active)
        closed_bool = _parse_optional_bool("closed", closed)
        archived_bool = _parse_optional_bool("archived", archived)

        markets = resolved_service.list_markets(
            limit=limit,
            offset=offset,
            active=active_bool,
            closed=closed_bool,
            archived=archived_bool,
            search=_normalize_optional_text(search),
            tag_id=tag_id,
        )
        return {
            "count": len(markets),
            "limit": limit,
            "offset": offset,
            "markets": markets,
        }

    @app.get("/api/markets/random")
    async def api_markets_random(
        sample_size: int = Query(default=10, ge=1, le=100),
        pool_size: int = Query(default=200, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        seed: Optional[int] = Query(default=None),
        active: Optional[str] = Query(default=None),
        closed: Optional[str] = Query(default=None),
        archived: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None, max_length=300),
        tag_id: Optional[int] = Query(default=None),
    ) -> dict[str, Any]:
        active_bool = _parse_optional_bool("active", active)
        closed_bool = _parse_optional_bool("closed", closed)
        archived_bool = _parse_optional_bool("archived", archived)

        selection = resolved_service.random_markets(
            sample_size=sample_size,
            pool_size=pool_size,
            offset=offset,
            seed=seed,
            active=active_bool,
            closed=closed_bool,
            archived=archived_bool,
            search=_normalize_optional_text(search),
            tag_id=tag_id,
        )
        return {
            "seed": selection.seed,
            "pool_count": selection.pool_count,
            "sample_count": selection.sample_count,
            "markets": selection.markets,
        }

    @app.get("/ui/markets", response_class=HTMLResponse)
    async def ui_markets(
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        active: Optional[str] = Query(default=None),
        closed: Optional[str] = Query(default=None),
        archived: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None, max_length=300),
        tag_id: Optional[int] = Query(default=None),
    ):
        active_bool = _parse_optional_bool("active", active)
        closed_bool = _parse_optional_bool("closed", closed)
        archived_bool = _parse_optional_bool("archived", archived)

        markets = resolved_service.list_markets(
            limit=limit,
            offset=offset,
            active=active_bool,
            closed=closed_bool,
            archived=archived_bool,
            search=_normalize_optional_text(search),
            tag_id=tag_id,
        )
        return templates.TemplateResponse(
            "partials/markets_panel.html",
            {
                "request": request,
                "markets": markets,
                "count": len(markets),
                "limit": limit,
                "offset": offset,
                "json_payload": json.dumps(markets, indent=2, ensure_ascii=True),
            },
        )

    @app.get("/ui/markets/random", response_class=HTMLResponse)
    async def ui_markets_random(
        request: Request,
        sample_size: int = Query(default=10, ge=1, le=100),
        pool_size: int = Query(default=200, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        seed: Optional[int] = Query(default=None),
        active: Optional[str] = Query(default=None),
        closed: Optional[str] = Query(default=None),
        archived: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None, max_length=300),
        tag_id: Optional[int] = Query(default=None),
    ):
        active_bool = _parse_optional_bool("active", active)
        closed_bool = _parse_optional_bool("closed", closed)
        archived_bool = _parse_optional_bool("archived", archived)

        selection = resolved_service.random_markets(
            sample_size=sample_size,
            pool_size=pool_size,
            offset=offset,
            seed=seed,
            active=active_bool,
            closed=closed_bool,
            archived=archived_bool,
            search=_normalize_optional_text(search),
            tag_id=tag_id,
        )
        return templates.TemplateResponse(
            "partials/random_panel.html",
            {
                "request": request,
                "selection": selection,
                "json_payload": json.dumps(selection.markets, indent=2, ensure_ascii=True),
            },
        )

    return app


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _parse_optional_bool(field_name: str, value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    raw = value.strip().lower()
    if raw == "":
        return None
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    raise HTTPException(
        status_code=422,
        detail=[{
            "loc": ["query", field_name],
            "msg": "Input should be a valid boolean string",
            "type": "bool_parsing",
            "input": value,
        }],
    )


app = create_app()
