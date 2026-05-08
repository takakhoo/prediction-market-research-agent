from __future__ import annotations

from typing import Any

from .config import PolymarketConfig
from .http import HttpJsonClient


class ClobPublicClient:
    """Public/read-only CLOB endpoints (no auth required)."""

    def __init__(self, config: PolymarketConfig, http_client: HttpJsonClient | None = None):
        self.config = config
        self.http = http_client or HttpJsonClient(timeout_seconds=config.timeout_seconds)

    def health(self) -> dict[str, Any]:
        payload = self.http.get_json(self.config.clob_base_url, "/ok", params=None)
        if isinstance(payload, dict):
            return payload
        return {"ok": bool(payload)}

    def get_orderbook(self, token_id: str) -> dict[str, Any]:
        payload = self.http.get_json(self.config.clob_base_url, "/book", params={"token_id": token_id})
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("Unexpected CLOB /book response format")

    def get_price(self, token_id: str, side: str = "buy") -> dict[str, Any]:
        payload = self.http.get_json(
            self.config.clob_base_url,
            "/price",
            params={"token_id": token_id, "side": side},
        )
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("Unexpected CLOB /price response format")
