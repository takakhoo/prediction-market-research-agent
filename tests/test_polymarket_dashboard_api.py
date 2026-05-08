from __future__ import annotations

from fastapi.testclient import TestClient

from src.polymarket.config import PolymarketConfig
from src.polymarket_dashboard.api import create_app


class FakeDiscoveryService:
    def __init__(self):
        self.last_list_kwargs = None
        self.last_random_kwargs = None

    def list_markets(self, **kwargs):
        self.last_list_kwargs = kwargs
        return [{"id": "1", "question": "Q1", "active": True, "closed": False}]

    def random_markets(self, **kwargs):
        self.last_random_kwargs = kwargs

        class Result:
            seed = kwargs.get("seed")
            pool_count = 1
            sample_count = 1
            markets = [{"id": "1", "question": "Q1"}]

        return Result()


def test_api_markets_accepts_empty_active_as_none():
    fake = FakeDiscoveryService()
    app = create_app(config=PolymarketConfig(), service=fake)
    client = TestClient(app)

    response = client.get("/api/markets", params={"active": "", "limit": 5, "offset": 0})
    assert response.status_code == 200
    assert fake.last_list_kwargs is not None
    assert fake.last_list_kwargs["active"] is None


def test_api_markets_rejects_invalid_active_bool():
    fake = FakeDiscoveryService()
    app = create_app(config=PolymarketConfig(), service=fake)
    client = TestClient(app)

    response = client.get("/api/markets", params={"active": "notabool"})
    assert response.status_code == 422
