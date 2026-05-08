from __future__ import annotations

from dataclasses import dataclass

from .config import PolymarketConfig, evaluate_trading_readiness


@dataclass(frozen=True)
class ActionPlan:
    can_read_markets: bool
    can_trade: bool
    required_for_trade: list[str]
    notes: list[str]


class PolymarketActionAdvisor:
    def __init__(self, config: PolymarketConfig):
        self.config = config

    def summarize(self) -> ActionPlan:
        readiness = evaluate_trading_readiness(self.config)
        return ActionPlan(
            can_read_markets=True,
            can_trade=readiness.ready,
            required_for_trade=readiness.missing,
            notes=readiness.notes,
        )
