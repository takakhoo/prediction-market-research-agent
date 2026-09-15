from __future__ import annotations

from src.polymarket.config import PolymarketConfig
from src.polymarket.market_ingest import MarketIngestService
from src.polymarket.market_intel_repository import MarketBundle


class FakeGamma:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list_markets(self, **kwargs):
        self.calls.append(kwargs)
        offset = int(kwargs.get("offset", 0))
        return list(self.pages.get(offset, []))

    def parse_outcomes(self, market):
        return list(market.get("_labels", [])), list(market.get("_prices", []))


class FakeRepo:
    def __init__(self):
        self.last_bundles: list[MarketBundle] = []

    def upsert_market_bundles(
        self,
        bundles,
        *,
        store_outcomes=True,
        store_snapshots=True,
    ):
        self.last_bundles = list(bundles)
        return len(self.last_bundles)


def test_market_ingest_filters_open_markets_and_sets_flags():
    pages = {
        0: [
            {
                "id": "m1",
                "conditionId": "c1",
                "question": "Will X happen?",
                "active": True,
                "closed": False,
                "archived": False,
                "volumeNum": 6_100_000,
                "liquidityNum": 1000,
                "_labels": ["Yes", "No"],
                "_prices": [0.82, 0.18],
                "clobTokenIds": '["t1","t2"]',
            },
            {
                "id": "m2",
                "conditionId": "c2",
                "question": "Will Y happen on Mar 12?",
                "active": True,
                "closed": False,
                "archived": False,
                "groupItemTitle": "Mar 12",
                "volumeNum": 1200,
                "_labels": ["Yes", "No"],
                "_prices": [0.35, 0.65],
                "clobTokenIds": '["t3","t4"]',
            },
            {
                "id": "m3",
                "conditionId": "c3",
                "question": "Closed market",
                "active": True,
                "closed": True,
                "archived": False,
                "_labels": ["Yes", "No"],
                "_prices": [0.1, 0.9],
            },
        ]
    }
    config = PolymarketConfig(
        ingest_page_limit=50,
        ingest_max_pages=5,
        likely_probability_threshold=0.75,
        unlikely_probability_threshold=0.25,
        high_competition_volume_usd=5_000_000,
    )
    gamma = FakeGamma(pages)
    repo = FakeRepo()
    service = MarketIngestService(config=config, gamma=gamma, repository=repo)

    stats = service.ingest_once()

    assert stats.fetched_markets == 2
    assert stats.upserted_markets == 2
    assert stats.total_outcomes == 4
    assert stats.high_competition_markets == 1
    assert len(repo.last_bundles) == 2

    first = repo.last_bundles[0]
    assert first.market["market_id"] == "m1"
    assert first.market["high_competition"] is True
    assert first.market["market_archetype"] == "binary_oneoff"
    assert first.outcomes[0]["is_likely"] is True
    assert first.outcomes[1]["is_unlikely"] is True

    second = repo.last_bundles[1]
    assert second.market["market_id"] == "m2"
    assert second.market["high_competition"] is False
    assert second.market["market_archetype"] == "binary_recurring"
    assert second.outcomes[0]["is_likely"] is False
    assert second.outcomes[0]["is_unlikely"] is False


def test_market_ingest_classifies_categorical():
    pages = {
        0: [
            {
                "id": "c1",
                "question": "Who wins?",
                "active": True,
                "closed": False,
                "_labels": ["A", "B", "Other"],
                "_prices": [0.4, 0.3, 0.3],
                "clobTokenIds": '["a","b","o"]',
            }
        ]
    }
    config = PolymarketConfig(ingest_page_limit=50, ingest_max_pages=3)
    repo = FakeRepo()
    service = MarketIngestService(config=config, gamma=FakeGamma(pages), repository=repo)
    stats = service.ingest_once()
    assert stats.fetched_markets == 1
    assert repo.last_bundles[0].market["market_archetype"] == "categorical_group"
