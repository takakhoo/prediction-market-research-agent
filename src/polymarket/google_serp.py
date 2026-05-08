from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import Request as UrlRequest, urlopen

from .config import PolymarketConfig


class GoogleSerpError(RuntimeError):
    """Base error for SERP provider failures."""


class GoogleSerpUnavailableError(GoogleSerpError):
    """Raised when no supported SERP API key is configured."""


@dataclass(frozen=True)
class GoogleSerpResult:
    provider: str
    query: str
    links: list[str]
    handles: list[str]
    raw_count: int


class GoogleSerpClient:
    def __init__(
        self,
        *,
        serper_api_key: str = "",
        serpapi_api_key: str = "",
        timeout_seconds: int = 15,
        default_results_per_query: int = 8,
    ) -> None:
        self.serper_api_key = str(serper_api_key or "").strip()
        self.serpapi_api_key = str(serpapi_api_key or "").strip()
        self.timeout_seconds = max(5, min(int(timeout_seconds), 120))
        self.default_results_per_query = max(1, min(int(default_results_per_query), 20))

    @classmethod
    def from_config(cls, config: PolymarketConfig) -> "GoogleSerpClient":
        return cls(
            serper_api_key=config.serper_api_key,
            serpapi_api_key=config.serpapi_api_key,
            timeout_seconds=config.serp_timeout_seconds,
            default_results_per_query=config.serp_results_per_query,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.serper_api_key or self.serpapi_api_key)

    @property
    def provider(self) -> str:
        if self.serper_api_key:
            return "serper"
        if self.serpapi_api_key:
            return "serpapi"
        return "none"

    def search_tme(self, query: str, *, max_results: int | None = None) -> GoogleSerpResult:
        if not self.enabled:
            raise GoogleSerpUnavailableError(
                "No SERP API key configured. Set SERPER_API_KEY or SERPAPI_API_KEY."
            )

        normalized_query = " ".join(str(query or "").split()).strip()
        if not normalized_query:
            return GoogleSerpResult(
                provider=self.provider,
                query="",
                links=[],
                handles=[],
                raw_count=0,
            )

        limit = (
            self.default_results_per_query
            if max_results is None
            else max(1, min(int(max_results), 20))
        )

        if self.serper_api_key:
            payload = self._search_serper(normalized_query, num=limit)
            links = _extract_serper_links(payload)
            provider = "serper"
        elif self.serpapi_api_key:
            payload = self._search_serpapi(normalized_query, num=limit)
            links = _extract_serpapi_links(payload)
            provider = "serpapi"
        else:
            raise GoogleSerpUnavailableError(
                "No SERP API key configured. Set SERPER_API_KEY or SERPAPI_API_KEY."
            )

        tme_links = [link for link in links if _is_tme_link(link)]
        handles = _dedupe_keep_order(
            [
                handle
                for handle in (_extract_tme_handle(link) for link in tme_links)
                if handle
            ]
        )

        return GoogleSerpResult(
            provider=provider,
            query=normalized_query,
            links=tme_links,
            handles=handles,
            raw_count=len(links),
        )

    def _search_serper(self, query: str, *, num: int) -> dict[str, Any]:
        url = "https://google.serper.dev/search"
        body = json.dumps({"q": query, "num": max(1, min(int(num), 20))}).encode("utf-8")
        request = UrlRequest(
            url,
            data=body,
            headers={
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return _read_json_response(request, timeout_seconds=self.timeout_seconds)

    def _search_serpapi(self, query: str, *, num: int) -> dict[str, Any]:
        encoded_query = quote_plus(query)
        url = (
            "https://serpapi.com/search.json"
            f"?engine=google&q={encoded_query}&num={max(1, min(int(num), 20))}&api_key={self.serpapi_api_key}"
        )
        request = UrlRequest(url, headers={"Accept": "application/json"})
        return _read_json_response(request, timeout_seconds=self.timeout_seconds)


def _read_json_response(request: UrlRequest, *, timeout_seconds: int) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=max(5, int(timeout_seconds))) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - network dependent
        raise GoogleSerpError(f"SERP request failed: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GoogleSerpError(f"SERP returned non-JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise GoogleSerpError("SERP payload must be a JSON object.")
    return payload


def _extract_serper_links(payload: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for item in list(payload.get("organic") or []):
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        if link:
            links.append(link)
    return _dedupe_keep_order(links)


def _extract_serpapi_links(payload: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for item in list(payload.get("organic_results") or []):
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        if link:
            links.append(link)
    return _dedupe_keep_order(links)


def _is_tme_link(url: str) -> bool:
    try:
        parsed = urlparse(str(url))
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    return host in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}


def _extract_tme_handle(url: str) -> str | None:
    try:
        parsed = urlparse(str(url))
    except Exception:
        return None
    host = (parsed.netloc or "").lower()
    if host not in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
        return None
    segments = [segment for segment in (parsed.path or "").split("/") if segment]
    if not segments:
        return None

    if segments[0] == "s" and len(segments) > 1:
        candidate = segments[1]
    else:
        candidate = segments[0]

    lowered = candidate.lower()
    if lowered in {"joinchat", "share"}:
        return None
    if candidate.startswith("+"):
        return None
    if not candidate:
        return None
    return candidate.lstrip("@")


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered

