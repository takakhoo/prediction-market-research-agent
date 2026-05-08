from __future__ import annotations

import json
from typing import Any, Protocol

from .config import PolymarketConfig


class JSONReasoningClient(Protocol):
    provider_name: str

    def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...


class LLMRuntimeUnavailable(RuntimeError):
    pass


class OpenAIJSONReasoningClient:
    provider_name = "openai_responses_v1"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "",
        http_referer: str = "",
        app_name: str = "",
        timeout_seconds: int = 30,
    ):
        if not api_key:
            raise LLMRuntimeUnavailable("OPENAI_API_KEY is missing.")

        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - import-path dependent
            raise LLMRuntimeUnavailable(
                "The openai package is not installed. Install dependencies from pyproject.toml."
            ) from exc

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout_seconds,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        headers: dict[str, str] = {}
        if http_referer:
            headers["HTTP-Referer"] = http_referer
        if app_name:
            headers["X-Title"] = app_name
        if headers:
            client_kwargs["default_headers"] = headers
        self._client = OpenAI(**client_kwargs)

    def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        payload = getattr(response, "output_text", "") or ""
        if not payload:
            raise LLMRuntimeUnavailable("OpenAI returned an empty structured response.")
        return json.loads(payload)


def resolve_reasoning_client(
    config: PolymarketConfig | None = None,
    *,
    required: bool = False,
) -> JSONReasoningClient | None:
    effective_config = config or PolymarketConfig.from_env()
    if not effective_config.openai_api_key:
        if required or effective_config.ai_runtime_mode == "ai_only":
            raise LLMRuntimeUnavailable(
                "OPENAI_API_KEY is missing. Add it to .env to enable AI runtime."
            )
        return None
    return OpenAIJSONReasoningClient(
        api_key=effective_config.openai_api_key,
        base_url=effective_config.openai_base_url,
        http_referer=effective_config.openai_http_referer,
        app_name=effective_config.openai_app_name,
        timeout_seconds=effective_config.openai_timeout_seconds,
    )
