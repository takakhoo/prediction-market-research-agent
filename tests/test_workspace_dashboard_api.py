from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polymarket.config import PolymarketConfig
from src.workspace_dashboard import api as workspace_api


class _FakeRepository:
    _runs = []

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.last_ref = None

    def get_market_by_ref(self, market_ref: str):
        self.last_ref = market_ref
        if market_ref != "will-israel-strike-gaza-on-339":
            return None
        return {
            "market_id": "mkt-1",
            "slug": "will-israel-strike-gaza-on-339",
            "question": "Will Israel strike Gaza on the listed date?",
            "rules_text": "Rules text",
            "market_context": "Context",
            "market_archetype": "binary_daily",
            "classification": "track_now",
            "analysis_local_score": 0.82,
            "mapped_channels": 4,
            "analysis_reason_json": {"priority_regions": ["middle_east"], "priority_languages": ["en", "ar"]},
        }

    def save_telegram_backtest_run(self, *, market_ref: str, payload: dict, params_json=None, summary_json=None):
        run_id = len(self.__class__._runs) + 1
        row = {
            "run_id": run_id,
            "created_at": "2026-03-08T00:00:00Z",
            "market_ref": market_ref,
            "market_id": (payload.get("market") or {}).get("market_id"),
            "market_slug": (payload.get("market") or {}).get("slug"),
            "params_json": params_json or {},
            "summary_json": summary_json or {},
            "payload_json": payload,
        }
        self.__class__._runs.append(row)
        return run_id

    def list_telegram_backtest_runs(self, *, limit: int = 20, market_ref: str | None = None):
        rows = list(self.__class__._runs)
        if market_ref:
            rows = [
                row
                for row in rows
                if market_ref in {
                    str(row.get("market_ref") or ""),
                    str(row.get("market_slug") or ""),
                    str(row.get("market_id") or ""),
                }
            ]
        rows = sorted(rows, key=lambda row: int(row["run_id"]), reverse=True)
        return [
            {
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "market_ref": row["market_ref"],
                "market_id": row["market_id"],
                "market_slug": row["market_slug"],
                "params_json": row["params_json"],
                "summary_json": row["summary_json"],
            }
            for row in rows[:limit]
        ]

    def get_telegram_backtest_run(self, run_id: int):
        for row in self.__class__._runs:
            if int(row["run_id"]) == int(run_id):
                return row
        return None


class _FakeEmptyRepository(_FakeRepository):
    def get_market_by_ref(self, market_ref: str):
        self.last_ref = market_ref
        return None


class _FakeTDLibClient:
    def __init__(self, settings):
        self.settings = settings
        self.closed = False

    async def close(self):
        self.closed = True


class _FakeDiscoveryService:
    def __init__(self, repository, tdlib_client, planner, channel_reviewer=None):
        self.repository = repository
        self.tdlib_client = tdlib_client
        self.planner = planner
        self.channel_reviewer = channel_reviewer
        self.last_kwargs = None

    async def backtest_market(self, market, **kwargs):
        self.last_kwargs = kwargs
        return {
            "market": {
                "market_id": market["market_id"],
                "slug": market["slug"],
                "question": market["question"],
            },
            "planner": {
                "planner_version": "heuristic_v1",
                "queries": ["israel gaza"],
                "prompt_debug": {
                    "runtime_mode": getattr(self.planner, "runtime_mode", "heuristic_legacy"),
                    "editable": getattr(self.planner, "runtime_mode", "") == "ai",
                    "model": getattr(self.planner, "model", None),
                    "system_prompt": "system",
                    "user_prompt": "user",
                    "input_materials": {"question": market["question"]},
                    "output_json": {"queries": ["israel gaza"]},
                    "override_applied": bool(kwargs.get("planner_system_prompt_override") or kwargs.get("planner_user_prompt_override")),
                    "note": "",
                },
            },
            "stages": {
                "search": [],
                "similar": [],
                "final": {"selected_channels": [], "accepted_candidates": 0, "target_channels": kwargs["target_channels_per_market"]},
            },
            "summary": {
                "target_channels": kwargs["target_channels_per_market"],
                "accepted_candidates": 0,
                "selected_channels": 0,
                "rejected_counts": {"low_members": 0, "low_relevance": 0, "duplicate": 0, "global_cap": 0},
                "api_errors": [],
            },
        }


class _FakePlanner:
    def __init__(self):
        self.runtime_mode = "ai"
        self.planner_version = "ai_query_planner_v1"
        self.prompt_version = "telegram-query-planner-v3-ai"
        self.model = "gpt-4o-mini"


class _FakeGammaClient:
    def __init__(self, config):
        self.config = config

    def get_event_by_slug(self, slug: str):
        if slug != "will-israel-strike-gaza-on-339":
            return None
        return {
            "id": "230495",
            "slug": slug,
            "title": "Will Israel strike Gaza on...?",
            "description": "Event-level rules",
            "resolutionSource": "Consensus of credible reporting",
            "markets": [
                {
                    "id": "1437333",
                    "slug": "will-israel-strike-gaza-on-march-5-2026",
                    "question": "Will Israel strike Gaza on March 5, 2026?",
                    "description": "Child rules",
                    "active": True,
                    "closed": False,
                }
            ],
        }

    def get_market_by_slug(self, slug: str):
        if slug != "direct-market-slug":
            return None
        return {
            "id": "mkt-9",
            "slug": slug,
            "question": "Direct market question?",
            "description": "Direct market rules",
            "outcomes": '["Yes","No"]',
            "active": True,
            "closed": False,
        }

    def get_market_by_id(self, market_id: str):
        return None


def test_telegram_backtest_endpoint_accepts_market_url(monkeypatch):
    _FakeRepository._runs = []
    monkeypatch.setattr(
        workspace_api.PolymarketConfig,
        "from_env",
        classmethod(
            lambda cls: PolymarketConfig(
                database_url="postgresql://example",
                direct_url="postgresql://example",
                telegram_min_channel_members=1000,
                telegram_min_channel_relevance_score=0.18,
            )
        ),
    )
    monkeypatch.setattr(workspace_api, "MarketIntelRepository", _FakeRepository)
    monkeypatch.setattr(workspace_api, "DiscoverySettings", lambda: object())
    monkeypatch.setattr(workspace_api, "TDLibDiscoveryClient", _FakeTDLibClient)
    monkeypatch.setattr(workspace_api, "MarketTelegramDiscoveryService", _FakeDiscoveryService)
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.get(
        "/api/intel/telegram-backtest",
        params={
            "market_ref": "https://polymarket.com/event/will-israel-strike-gaza-on-339?tid=1",
            "target_channels": 12,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["market"]["slug"] == "will-israel-strike-gaza-on-339"
    assert payload["meta"]["market_ref"] == "will-israel-strike-gaza-on-339"
    assert payload["meta"]["target_channels"] == 12
    assert payload["meta"]["backtest_saved"] is True
    assert payload["meta"]["backtest_run_id"] is not None
    assert payload["planner"]["planner_version"] == "heuristic_v1"


def test_telegram_backtest_post_accepts_prompt_override(monkeypatch):
    _FakeRepository._runs = []
    monkeypatch.setattr(
        workspace_api.PolymarketConfig,
        "from_env",
        classmethod(
            lambda cls: PolymarketConfig(
                database_url="postgresql://example",
                direct_url="postgresql://example",
                telegram_min_channel_members=1000,
                telegram_min_channel_relevance_score=0.18,
            )
        ),
    )
    monkeypatch.setattr(workspace_api, "MarketIntelRepository", _FakeRepository)
    monkeypatch.setattr(workspace_api, "DiscoverySettings", lambda: object())
    monkeypatch.setattr(workspace_api, "TDLibDiscoveryClient", _FakeTDLibClient)
    monkeypatch.setattr(workspace_api, "MarketTelegramDiscoveryService", _FakeDiscoveryService)
    monkeypatch.setattr(workspace_api, "MarketSearchPlanner", _FakePlanner)
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.post(
        "/api/intel/telegram-backtest",
        json={
            "market_ref": "will-israel-strike-gaza-on-339",
            "use_prompt_override": True,
            "planner_system_prompt": "edited system",
            "planner_user_prompt": "edited user",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["use_prompt_override"] is True
    assert payload["meta"]["planner_prompt_editable"] is True
    assert payload["planner"]["prompt_debug"]["override_applied"] is True


def test_telegram_backtest_runs_endpoints(monkeypatch):
    _FakeRepository._runs = []
    monkeypatch.setattr(
        workspace_api.PolymarketConfig,
        "from_env",
        classmethod(
            lambda cls: PolymarketConfig(
                database_url="postgresql://example",
                direct_url="postgresql://example",
                telegram_min_channel_members=1000,
                telegram_min_channel_relevance_score=0.18,
            )
        ),
    )
    monkeypatch.setattr(workspace_api, "MarketIntelRepository", _FakeRepository)
    monkeypatch.setattr(workspace_api, "DiscoverySettings", lambda: object())
    monkeypatch.setattr(workspace_api, "TDLibDiscoveryClient", _FakeTDLibClient)
    monkeypatch.setattr(workspace_api, "MarketTelegramDiscoveryService", _FakeDiscoveryService)
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    created = client.get(
        "/api/intel/telegram-backtest",
        params={"market_ref": "will-israel-strike-gaza-on-339"},
    )
    assert created.status_code == 200
    run_id = created.json()["meta"]["backtest_run_id"]

    runs = client.get("/api/intel/telegram-backtest/runs")
    assert runs.status_code == 200
    runs_payload = runs.json()
    assert runs_payload["count"] >= 1
    assert runs_payload["items"][0]["run_id"] == run_id

    detail = client.get(f"/api/intel/telegram-backtest/runs/{run_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["run_record"]["run_id"] == run_id


def test_telegram_backtest_endpoint_falls_back_to_gamma_event(monkeypatch):
    monkeypatch.setattr(
        workspace_api.PolymarketConfig,
        "from_env",
        classmethod(
            lambda cls: PolymarketConfig(
                database_url="postgresql://example",
                direct_url="postgresql://example",
                telegram_min_channel_members=1000,
                telegram_min_channel_relevance_score=0.18,
            )
        ),
    )
    monkeypatch.setattr(workspace_api, "MarketIntelRepository", _FakeEmptyRepository)
    monkeypatch.setattr(workspace_api, "GammaMarketsClient", _FakeGammaClient)
    monkeypatch.setattr(workspace_api, "DiscoverySettings", lambda: object())
    monkeypatch.setattr(workspace_api, "TDLibDiscoveryClient", _FakeTDLibClient)
    monkeypatch.setattr(workspace_api, "MarketTelegramDiscoveryService", _FakeDiscoveryService)
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.get(
        "/api/intel/telegram-backtest",
        params={"market_ref": "https://polymarket.com/event/will-israel-strike-gaza-on-339"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["market"]["market_id"] == "1437333"
    assert payload["market"]["slug"] == "will-israel-strike-gaza-on-march-5-2026"
    assert payload["market"]["question"] == "Will Israel strike Gaza on March 5, 2026?"


def test_telegram_backtest_endpoint_falls_back_to_gamma_market_slug(monkeypatch):
    monkeypatch.setattr(
        workspace_api.PolymarketConfig,
        "from_env",
        classmethod(
            lambda cls: PolymarketConfig(
                database_url="postgresql://example",
                direct_url="postgresql://example",
                telegram_min_channel_members=1000,
                telegram_min_channel_relevance_score=0.18,
            )
        ),
    )
    monkeypatch.setattr(workspace_api, "MarketIntelRepository", _FakeEmptyRepository)
    monkeypatch.setattr(workspace_api, "GammaMarketsClient", _FakeGammaClient)
    monkeypatch.setattr(workspace_api, "DiscoverySettings", lambda: object())
    monkeypatch.setattr(workspace_api, "TDLibDiscoveryClient", _FakeTDLibClient)
    monkeypatch.setattr(workspace_api, "MarketTelegramDiscoveryService", _FakeDiscoveryService)
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.get(
        "/api/intel/telegram-backtest",
        params={"market_ref": "direct-market-slug"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["market"]["market_id"] == "mkt-9"
    assert payload["market"]["slug"] == "direct-market-slug"


def test_telegram_backtest_endpoint_returns_404_for_unknown_market(monkeypatch):
    monkeypatch.setattr(
        workspace_api.PolymarketConfig,
        "from_env",
        classmethod(
            lambda cls: PolymarketConfig(
                database_url="postgresql://example",
                direct_url="postgresql://example",
            )
        ),
    )
    monkeypatch.setattr(workspace_api, "MarketIntelRepository", _FakeRepository)
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.get(
        "/api/intel/telegram-backtest",
        params={"market_ref": "unknown-market"},
    )

    assert response.status_code == 404


def test_prompt_registry_endpoint_lists_prompt_components(monkeypatch):
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.get("/api/intel/prompts")

    assert response.status_code == 200
    payload = response.json()
    ids = {item["id"] for item in payload["items"]}
    assert "market-local-classifier" in ids
    assert "telegram-query-planner" in ids
    assert "telegram-channel-relevance" in ids
    assert "telegram-message-matcher" in ids


def test_prompt_lab_page_renders(monkeypatch):
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.get("/prompt-lab")

    assert response.status_code == 200
    assert "Prompt Lab" in response.text


def test_backtest_page_renders(monkeypatch):
    monkeypatch.setattr(workspace_api, "create_telegram_app", lambda: FastAPI())
    monkeypatch.setattr(workspace_api, "create_polymarket_app", lambda: FastAPI())

    client = TestClient(workspace_api.create_app())
    response = client.get("/backtest")

    assert response.status_code == 200
    assert "Telegram Discovery Backtest" in response.text
