from __future__ import annotations

from src.polymarket.discovery_service import PolymarketDiscoveryService


class FakeGamma:
    def __init__(self, markets):
        self.markets = markets
        self.calls = []

    def list_markets(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.markets)


def test_random_markets_uses_pool_and_sample_size_bounds():
    markets = [{"id": str(i), "question": f"Q{i}"} for i in range(15)]
    service = PolymarketDiscoveryService(FakeGamma(markets))

    result = service.random_markets(
        sample_size=10,
        pool_size=200,
        offset=0,
        active=None,
        closed=None,
        archived=None,
        search=None,
        tag_id=None,
        seed=123,
    )

    assert result.pool_count == 15
    assert result.sample_count == 10
    assert len(result.markets) == 10
    assert len({item["id"] for item in result.markets}) == 10


def test_random_markets_is_reproducible_with_seed():
    markets = [{"id": str(i), "question": f"Q{i}"} for i in range(50)]
    service = PolymarketDiscoveryService(FakeGamma(markets))

    first = service.random_markets(
        sample_size=8,
        pool_size=50,
        offset=0,
        active=True,
        closed=False,
        archived=None,
        search="inflation",
        tag_id=1,
        seed=77,
    )
    second = service.random_markets(
        sample_size=8,
        pool_size=50,
        offset=0,
        active=True,
        closed=False,
        archived=None,
        search="inflation",
        tag_id=1,
        seed=77,
    )

    assert [item["id"] for item in first.markets] == [item["id"] for item in second.markets]
