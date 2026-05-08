from __future__ import annotations

from src.polymarket.config import PolymarketConfig, evaluate_trading_readiness
from src.polymarket.gamma_client import GammaMarketsClient


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get_json(self, base_url, path, params=None):
        self.calls.append((base_url, path, params))
        normalized = {k: v for k, v in (params or {}).items() if v is not None}
        key = (path, tuple(sorted(normalized.items())))
        return self.payloads[key]


def test_gamma_list_and_summarize():
    config = PolymarketConfig()
    payloads = {
        (
            "/markets",
            tuple(sorted({"limit": 2, "offset": 0}.items())),
        ): [
            {
                "id": "123",
                "conditionId": "abc",
                "slug": "test-market",
                "question": "Will X happen?",
                "active": True,
                "closed": False,
                "endDate": "2026-03-10T00:00:00Z",
                "volume": "1234.5",
                "liquidity": "456.7",
                "outcomes": '["Yes","No"]',
                "outcomePrices": '["0.40","0.60"]',
            }
        ],
    }

    client = GammaMarketsClient(config, http_client=FakeHttp(payloads))
    markets = client.list_markets(limit=2, offset=0)
    assert len(markets) == 1

    summary = client.summarize(markets)[0]
    assert summary.market_id == "123"
    assert summary.active is True
    assert summary.volume == 1234.5

    outcomes, prices = client.parse_outcomes(markets[0])
    assert outcomes == ["Yes", "No"]
    assert prices == [0.4, 0.6]


def test_trading_readiness_requires_key_and_funder():
    config = PolymarketConfig(
        private_key="",
        funder_address="",
    )
    readiness = evaluate_trading_readiness(config)
    assert readiness.ready is False
    assert "POLYMARKET_PRIVATE_KEY" in readiness.missing
    assert "POLYMARKET_FUNDER_ADDRESS" in readiness.missing
