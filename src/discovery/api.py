from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import DiscoverySettings
from .errors import TDLibAuthRequiredError, TDLibRequestError, WatchlistError
from .models import (
    ErrorResponse,
    ExpandSimilarRequest,
    ExpandSimilarResponse,
    HealthResponse,
    MessageResult,
    SearchRequest,
    SearchResponse,
    WatchlistCreateRequest,
    WatchlistItem,
    WatchlistPatchRequest,
)
from .repository import DiscoveryRepository
from .service import DiscoveryService
from .tdlib_client import TDLibDiscoveryClient

DOCS_HINT = (
    "Run scripts/telegram_session_bootstrap.py first. "
    "See docs/telegram/DISCOVERY_DASHBOARD_MVP.md"
)


def create_app(
    settings: Optional[DiscoverySettings] = None,
    repository: Optional[DiscoveryRepository] = None,
    tdlib_client: Optional[TDLibDiscoveryClient] = None,
) -> FastAPI:
    resolved_settings = settings or DiscoverySettings()
    resolved_repository = repository or DiscoveryRepository(resolved_settings.db_path)
    resolved_tdlib = tdlib_client or TDLibDiscoveryClient(resolved_settings)
    service = DiscoveryService(resolved_settings, resolved_repository, resolved_tdlib)

    template_dir = Path(__file__).resolve().parent.parent / "discovery_dashboard" / "templates"
    templates = Jinja2Templates(directory=str(template_dir))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await resolved_repository.init()
        yield
        await resolved_tdlib.close()

    app = FastAPI(title="Telegram Discovery Dashboard MVP", lifespan=lifespan)
    app.state.service = service
    app.state.templates = templates

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "default_search_limit": resolved_settings.discovery_search_limit,
                "default_message_limit": resolved_settings.discovery_message_preview_limit,
                "default_depth": resolved_settings.discovery_similar_depth,
                "default_per_node": resolved_settings.discovery_similar_per_node,
                "default_max_nodes": resolved_settings.discovery_similar_max_nodes,
            },
        )

    @app.get("/api/health", response_model=HealthResponse)
    async def api_health() -> HealthResponse:
        return HealthResponse(**(await service.health()))

    @app.get("/ui/health", response_class=HTMLResponse)
    async def ui_health(request: Request):
        health = await service.health()
        return templates.TemplateResponse(
            "partials/health_panel.html",
            {"request": request, "health": health},
        )

    @app.post("/api/search", response_model=SearchResponse)
    async def api_search(payload: SearchRequest) -> SearchResponse:
        try:
            return await service.search_channels(payload.query, payload.limit)
        except TDLibAuthRequiredError as exc:
            raise _http_auth_error(exc)
        except TDLibRequestError as exc:
            raise _http_tdlib_error(exc)

    @app.get("/api/channels/{chat_id}/messages", response_model=List[MessageResult])
    async def api_messages(chat_id: int, limit: Optional[int] = None) -> List[MessageResult]:
        try:
            return await service.channel_messages(chat_id, limit)
        except TDLibAuthRequiredError as exc:
            raise _http_auth_error(exc)
        except TDLibRequestError as exc:
            raise _http_tdlib_error(exc)

    @app.post("/api/channels/{chat_id}/expand-similar", response_model=ExpandSimilarResponse)
    async def api_expand_similar(chat_id: int, payload: ExpandSimilarRequest) -> ExpandSimilarResponse:
        try:
            return await service.expand_similar(chat_id, payload)
        except TDLibAuthRequiredError as exc:
            raise _http_auth_error(exc)
        except TDLibRequestError as exc:
            raise _http_tdlib_error(exc)
        except WatchlistError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.get("/api/watchlist", response_model=List[WatchlistItem])
    async def api_get_watchlist() -> List[WatchlistItem]:
        return await service.get_watchlist()

    @app.post("/api/watchlist", response_model=WatchlistItem)
    async def api_create_watchlist(payload: WatchlistCreateRequest) -> WatchlistItem:
        try:
            return await service.add_watchlist(payload)
        except TDLibAuthRequiredError as exc:
            raise _http_auth_error(exc)
        except TDLibRequestError as exc:
            raise _http_tdlib_error(exc)
        except WatchlistError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.patch("/api/watchlist/{chat_id}", response_model=WatchlistItem)
    async def api_patch_watchlist(chat_id: int, payload: WatchlistPatchRequest) -> WatchlistItem:
        try:
            return await service.patch_watchlist(chat_id, payload)
        except WatchlistError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    @app.post("/ui/search", response_class=HTMLResponse)
    async def ui_search(request: Request, query: str = Form(...), limit: int = Form(50)):
        try:
            response = await service.search_channels(query, limit)
            return templates.TemplateResponse(
                "partials/search_results.html",
                {"request": request, "search": response},
            )
        except (TDLibAuthRequiredError, TDLibRequestError) as exc:
            return _ui_error(request, templates, str(exc))

    @app.get("/ui/probe", response_class=HTMLResponse)
    async def ui_probe(
        request: Request,
        query: str,
        limit: int = 5,
        messages_limit: int = 5,
        similar_limit: int = 10,
    ):
        cleaned_query = query.strip()
        if not cleaned_query:
            return _ui_error(request, templates, "Probe query must not be empty")

        try:
            search = await service.search_channels(cleaned_query, limit)
            selected = search.channels[0] if search.channels else None

            messages: List[MessageResult] = []
            similar_channels = []

            if selected is not None:
                messages = await service.channel_messages(selected.chat_id, messages_limit)
                similar_response = await service.expand_similar(
                    selected.chat_id,
                    ExpandSimilarRequest(
                        depth=1,
                        per_node=max(1, min(similar_limit, 50)),
                        max_nodes=max(2, min(similar_limit + 1, 500)),
                    ),
                )
                similar_channels = [
                    item for item in similar_response.channels if item.chat_id != selected.chat_id
                ][: max(1, min(similar_limit, 50))]

            payload = {
                "query": cleaned_query,
                "search_count": len(search.channels),
                "selected_channel": selected.model_dump() if selected else None,
                "messages_count": len(messages),
                "messages": [item.model_dump() for item in messages],
                "similar_count": len(similar_channels),
                "similar_channels": [item.model_dump() for item in similar_channels],
            }

            return templates.TemplateResponse(
                "partials/probe_panel.html",
                {
                    "request": request,
                    "payload": payload,
                    "search": search,
                    "selected": selected,
                    "messages": messages,
                    "similar_channels": similar_channels,
                },
            )
        except (TDLibAuthRequiredError, TDLibRequestError, WatchlistError, ValueError) as exc:
            return _ui_error(request, templates, str(exc))

    @app.get("/ui/channels/{chat_id}/messages", response_class=HTMLResponse)
    async def ui_messages(request: Request, chat_id: int, limit: Optional[int] = None):
        try:
            messages = await service.channel_messages(chat_id, limit)
            channel = await resolved_repository.get_channel(chat_id)
            return templates.TemplateResponse(
                "partials/messages_panel.html",
                {
                    "request": request,
                    "chat_id": chat_id,
                    "channel": channel,
                    "messages": messages,
                },
            )
        except (TDLibAuthRequiredError, TDLibRequestError) as exc:
            return _ui_error(request, templates, str(exc))

    @app.post("/ui/channels/{chat_id}/expand-similar", response_class=HTMLResponse)
    async def ui_expand_similar(
        request: Request,
        chat_id: int,
        depth: int = Form(2),
        per_node: int = Form(20),
        max_nodes: int = Form(120),
    ):
        try:
            payload = ExpandSimilarRequest(depth=depth, per_node=per_node, max_nodes=max_nodes)
            response = await service.expand_similar(chat_id, payload)
            return templates.TemplateResponse(
                "partials/similar_panel.html",
                {"request": request, "similar": response},
            )
        except (TDLibAuthRequiredError, TDLibRequestError, WatchlistError) as exc:
            return _ui_error(request, templates, str(exc))

    @app.get("/ui/channels/{chat_id}/watchlist-form", response_class=HTMLResponse)
    async def ui_watchlist_form(request: Request, chat_id: int):
        channel = await resolved_repository.get_channel(chat_id)
        if channel is None:
            try:
                resolved = await resolved_tdlib.get_channel(chat_id)
            except (TDLibAuthRequiredError, TDLibRequestError) as exc:
                return _ui_error(request, templates, str(exc))
            if resolved is None:
                return _ui_error(request, templates, f"Chat {chat_id} is not a public channel")
            await resolved_repository.upsert_channels([resolved], source="ui")
            channel = await resolved_repository.get_channel(chat_id)

        return templates.TemplateResponse(
            "partials/watchlist_form.html",
            {
                "request": request,
                "channel": channel,
                "default_weight": 0.5,
            },
        )

    @app.get("/ui/watchlist", response_class=HTMLResponse)
    async def ui_watchlist(request: Request):
        items = await service.get_watchlist()
        return templates.TemplateResponse(
            "partials/watchlist_panel.html",
            {"request": request, "items": items},
        )

    @app.post("/ui/watchlist", response_class=HTMLResponse)
    async def ui_watchlist_create(
        request: Request,
        chat_id: int = Form(...),
        trust_weight: float = Form(...),
        tags: str = Form(""),
        notes: str = Form(""),
    ):
        payload = WatchlistCreateRequest(
            chat_id=chat_id,
            trust_weight=trust_weight,
            tags=_parse_tags(tags),
            notes=notes,
        )
        try:
            await service.add_watchlist(payload)
            items = await service.get_watchlist()
            return templates.TemplateResponse(
                "partials/watchlist_panel.html",
                {"request": request, "items": items},
            )
        except (TDLibAuthRequiredError, TDLibRequestError, WatchlistError, ValueError) as exc:
            return _ui_error(request, templates, str(exc))

    @app.patch("/ui/watchlist/{chat_id}", response_class=HTMLResponse)
    async def ui_watchlist_patch(
        request: Request,
        chat_id: int,
        trust_weight: Optional[float] = Form(None),
        tags: Optional[str] = Form(None),
        notes: Optional[str] = Form(None),
    ):
        payload = WatchlistPatchRequest(
            trust_weight=trust_weight,
            tags=None if tags is None else _parse_tags(tags),
            notes=notes,
        )
        try:
            await service.patch_watchlist(chat_id, payload)
            items = await service.get_watchlist()
            return templates.TemplateResponse(
                "partials/watchlist_panel.html",
                {"request": request, "items": items},
            )
        except (WatchlistError, ValueError) as exc:
            return _ui_error(request, templates, str(exc))

    return app



def _parse_tags(raw: str) -> List[str]:
    tokens = [part.strip() for part in raw.split(",")]
    return [token for token in tokens if token]



def _http_auth_error(exc: Exception) -> HTTPException:
    response = ErrorResponse(detail=str(exc), docs_hint=DOCS_HINT)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=response.model_dump(),
    )



def _http_tdlib_error(exc: Exception) -> HTTPException:
    response = ErrorResponse(detail=str(exc), docs_hint=DOCS_HINT)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=response.model_dump(),
    )



def _ui_error(request: Request, templates: Jinja2Templates, message: str):
    return templates.TemplateResponse(
        "partials/error_panel.html",
        {
            "request": request,
            "message": message,
            "docs_hint": DOCS_HINT,
        },
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


app = create_app()
