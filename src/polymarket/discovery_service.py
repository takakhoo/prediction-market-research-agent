from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .gamma_client import GammaMarketsClient


@dataclass(frozen=True)
class MarketRandomSelection:
    seed: int | None
    pool_count: int
    sample_count: int
    markets: list[dict[str, Any]]


class PolymarketDiscoveryService:
    """Service helpers for market discovery and randomized sampling."""

    def __init__(self, gamma: GammaMarketsClient):
        self.gamma = gamma

    def list_markets(
        self,
        *,
        limit: int,
        offset: int,
        active: bool | None,
        closed: bool | None,
        archived: bool | None,
        search: str | None,
        tag_id: int | None,
    ) -> list[dict[str, Any]]:
        return self.gamma.list_markets(
            limit=limit,
            offset=offset,
            active=active,
            closed=closed,
            archived=archived,
            search=search,
            tag_id=tag_id,
        )

    def random_markets(
        self,
        *,
        sample_size: int,
        pool_size: int,
        offset: int,
        active: bool | None,
        closed: bool | None,
        archived: bool | None,
        search: str | None,
        tag_id: int | None,
        seed: int | None = None,
    ) -> MarketRandomSelection:
        markets = self.gamma.list_markets(
            limit=max(1, min(pool_size, 500)),
            offset=max(0, offset),
            active=active,
            closed=closed,
            archived=archived,
            search=search,
            tag_id=tag_id,
        )
        if not markets:
            return MarketRandomSelection(
                seed=seed,
                pool_count=0,
                sample_count=0,
                markets=[],
            )

        effective_sample = max(1, min(sample_size, len(markets), 100))
        if seed is None:
            sampled = random.sample(markets, k=effective_sample)
        else:
            rng = random.Random(seed)
            sampled = rng.sample(markets, k=effective_sample)

        return MarketRandomSelection(
            seed=seed,
            pool_count=len(markets),
            sample_count=effective_sample,
            markets=sampled,
        )
