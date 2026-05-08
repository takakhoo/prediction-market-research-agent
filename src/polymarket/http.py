from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HttpJsonError(RuntimeError):
    """Raised when an HTTP/JSON request fails."""


class HttpJsonClient:
    def __init__(self, timeout_seconds: int = 20, user_agent: str = "Mozilla/5.0 (PolymarketNewsAgent/0.1)"):
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def get_json(self, base_url: str, path: str, params: Mapping[str, Any] | None = None) -> Any:
        query = ""
        if params:
            normalized = _normalize_params(params)
            query = urlencode(normalized, doseq=True)

        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"

        request = Request(
            url=url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload)
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            raise HttpJsonError(f"HTTP {exc.code} for {url}: {body or exc.reason}") from exc
        except URLError as exc:
            raise HttpJsonError(f"Network error for {url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise HttpJsonError(f"Invalid JSON response from {url}: {exc}") from exc


def _normalize_params(params: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            normalized[key] = "true" if value else "false"
        else:
            normalized[key] = value
    return normalized
