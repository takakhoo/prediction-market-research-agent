from __future__ import annotations

import pytest

from src.discovery.repository import DiscoveryRepository


@pytest.mark.asyncio
async def test_upsert_channels_idempotent(tmp_path):
    repo = DiscoveryRepository(tmp_path / "discovery.db")
    await repo.init()

    await repo.upsert_channels(
        [
            {
                "chat_id": 100,
                "title": "Channel A",
                "username": "channel_a",
                "description": "alpha",
                "member_count": 1000,
            }
        ],
        source="search",
    )

    await repo.upsert_channels(
        [
            {
                "chat_id": 100,
                "title": "Channel A Updated",
                "username": "channel_a",
                "description": "alpha-2",
                "member_count": 1200,
            }
        ],
        source="similar",
    )

    row = await repo.get_channel(100)
    assert row is not None
    assert row["title"] == "Channel A Updated"
    assert row["description"] == "alpha-2"
    assert row["member_count"] == 1200
    assert row["last_source"] == "similar"


@pytest.mark.asyncio
async def test_watchlist_round_trip(tmp_path):
    repo = DiscoveryRepository(tmp_path / "discovery.db")
    await repo.init()

    await repo.upsert_channels(
        [
            {
                "chat_id": 200,
                "title": "Channel B",
                "username": "channel_b",
                "description": "beta",
                "member_count": 2200,
            }
        ],
        source="search",
    )

    created = await repo.set_watchlist_item(
        chat_id=200,
        trust_weight=0.4,
        tags=["region", "news"],
        notes="first pass",
    )
    assert created["trust_weight"] == 0.4
    assert created["tags"] == ["region", "news"]

    patched = await repo.patch_watchlist_item(
        chat_id=200,
        trust_weight=0.8,
        tags=["region", "official"],
        notes="updated",
    )
    assert patched is not None
    assert patched["trust_weight"] == 0.8
    assert patched["tags"] == ["region", "official"]
    assert patched["notes"] == "updated"

    all_items = await repo.get_watchlist()
    assert len(all_items) == 1
    assert all_items[0]["chat_id"] == 200


@pytest.mark.asyncio
async def test_watchlist_rejects_invalid_trust_weight(tmp_path):
    repo = DiscoveryRepository(tmp_path / "discovery.db")
    await repo.init()

    await repo.upsert_channels(
        [
            {
                "chat_id": 300,
                "title": "Channel C",
                "username": None,
                "description": None,
                "member_count": None,
            }
        ],
        source="search",
    )

    with pytest.raises(ValueError, match="trust_weight"):
        await repo.set_watchlist_item(
            chat_id=300,
            trust_weight=1.2,
            tags=[],
            notes="bad",
        )
