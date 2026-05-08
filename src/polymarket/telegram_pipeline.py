from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Callable

from src.discovery.errors import TDLibRequestError
from src.discovery.tdlib_client import TDLibDiscoveryClient

from .channel_relevance import build_market_channel_profile, evaluate_channel_relevance
from .config import PolymarketConfig
from .google_serp import GoogleSerpClient, GoogleSerpError
from .llm_runtime import JSONReasoningClient, OpenAIJSONReasoningClient, resolve_reasoning_client
from .market_intel_repository import MarketIntelRepository
from .prompt_store import load_prompt_template, render_prompt_template

_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "market",
    "no",
    "not",
    "of",
    "on",
    "or",
    "question",
    "resolve",
    "resolves",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "who",
    "will",
    "with",
    "yes",
}

_PHRASE_TERMS = (
    "air strike",
    "drone strike",
    "missile strike",
    "ground offensive",
    "forces enter",
    "ceasefire",
    "rocket fire",
    "ballistic missile",
)

_REGION_HINT_QUERIES = {
    "middle_east": ("israel", "gaza", "lebanon", "iran"),
    "eastern_europe": ("ukraine", "russia"),
    "latin_america": ("venezuela", "colombia", "argentina"),
}

_ACTOR_SEEDS = {
    "israel": {
        "label": "Israel",
        "aliases": ("israel", "israeli", "idf", "jerusalem", "ישראל", "צהל", "צה\"ל", "צה״ל"),
        "local_languages": ("he", "ar"),
        "bridge_languages": ("en",),
        "keywords": {
            "en": ("israel", "idf", "israel military", "israel alerts"),
            "he": ("ישראל", "צה״ל", "פיקוד העורף", "חדשות ישראל"),
            "ar": ("إسرائيل", "الجيش الإسرائيلي", "اخبار اسرائيل"),
        },
        "official_targets": (
            {
                "label": "IDF Official",
                "type": "official_military",
                "handles": ("@idfofficial", "@idf_telegram"),
                "queries": ("idfofficial", "idf_telegram", "idf official"),
            },
        ),
    },
    "iran": {
        "label": "Iran",
        "aliases": ("iran", "iranian", "tehran", "irgc", "ایران", "تهران", "سپاه", "ارتش"),
        "local_languages": ("fa",),
        "bridge_languages": ("en", "ar"),
        "keywords": {
            "en": ("iran", "irgc", "tehran", "iran military"),
            "fa": ("ایران", "سپاه", "ارتش ایران", "تهران"),
            "ar": ("إيران", "الحرس الثوري", "طهران"),
        },
        "official_targets": (
            {
                "label": "Iran military / IRGC official channels",
                "type": "official_military",
                "handles": (),
                "queries": ("سپاه", "ارتش ایران", "irgc", "iran military"),
            },
        ),
    },
    "gaza": {
        "label": "Gaza",
        "aliases": ("gaza", "gazan", "غزة"),
        "local_languages": ("ar",),
        "bridge_languages": ("en", "he"),
        "keywords": {
            "en": ("gaza", "gaza alerts", "gaza updates"),
            "ar": ("غزة", "اخبار غزة", "قصف غزة"),
            "he": ("עזה", "חדשות עזה"),
        },
        "official_targets": (),
    },
    "lebanon": {
        "label": "Lebanon",
        "aliases": ("lebanon", "lebanese", "beirut", "hezbollah", "لبنان", "بيروت"),
        "local_languages": ("ar",),
        "bridge_languages": ("en", "fr"),
        "keywords": {
            "en": ("lebanon", "beirut", "lebanon military", "south lebanon"),
            "ar": ("لبنان", "بيروت", "جنوب لبنان"),
            "fr": ("liban", "beyrouth"),
        },
        "official_targets": (),
    },
    "ukraine": {
        "label": "Ukraine",
        "aliases": ("ukraine", "ukrainian", "kyiv", "kiev", "україна", "київ"),
        "local_languages": ("uk",),
        "bridge_languages": ("en", "ru"),
        "keywords": {
            "en": ("ukraine", "kyiv", "ukraine war"),
            "uk": ("Україна", "Київ", "війна"),
            "ru": ("Украина", "Киев"),
        },
        "official_targets": (),
    },
    "russia": {
        "label": "Russia",
        "aliases": ("russia", "russian", "moscow", "kremlin", "россия", "москва"),
        "local_languages": ("ru",),
        "bridge_languages": ("en",),
        "keywords": {
            "en": ("russia", "moscow", "kremlin"),
            "ru": ("Россия", "Москва", "Кремль"),
        },
        "official_targets": (),
    },
    "venezuela": {
        "label": "Venezuela",
        "aliases": ("venezuela", "venezuelan", "caracas", "maduro", "machado"),
        "local_languages": ("es",),
        "bridge_languages": ("en",),
        "keywords": {
            "en": ("venezuela", "caracas", "maduro", "machado"),
            "es": ("venezuela", "caracas", "maduro", "machado"),
        },
        "official_targets": (),
    },
}


@dataclass(frozen=True)
class ChannelDiscoveryStats:
    markets_considered: int
    markets_updated: int
    queries_sent: int
    links_written: int
    channels_written: int
    unique_channels_seen: int
    api_errors: int


@dataclass(frozen=True)
class MessageListenerStats:
    channels_polled: int
    fetch_errors: int
    new_messages: int
    evaluated_pairs: int
    matched_pairs: int
    activations_inserted: int


@dataclass(frozen=True)
class _MatcherProfile:
    market_id: str
    market_archetype: str
    question: str
    rules_text: str
    market_context: str
    terms: set[str]
    phrases: tuple[str, ...]
    min_overlap: int


@dataclass(frozen=True)
class MatchDecision:
    is_match: bool
    reason_short: str
    matched_terms: list[str]
    matched_phrases: list[str]


class MarketSearchPlanner:
    planner_version = "ai_query_planner_v1"
    prompt_version = "telegram-query-planner-v3-ai"

    def __init__(
        self,
        *,
        reasoning_client: JSONReasoningClient | None = None,
        model: str | None = None,
        config: PolymarketConfig | None = None,
    ):
        self.config = config or PolymarketConfig.from_env()
        self.reasoning_client = reasoning_client or resolve_reasoning_client(self.config, required=False)
        self.model = model or self.config.ai_telegram_query_planner_model
        self.runtime_mode = "ai" if self.reasoning_client is not None else "heuristic_legacy"
        self.planner_version = (
            "ai_query_planner_v1" if self.runtime_mode == "ai" else "heuristic_v2_multilingual"
        )
        self.prompt_version = (
            "telegram-query-planner-v3-ai"
            if self.runtime_mode == "ai"
            else "telegram-query-planner-v2-multilingual"
        )

    def build_query_plan(
        self,
        market: dict[str, Any],
        *,
        max_queries: int,
        include_debug: bool = False,
        system_prompt_override: str | None = None,
        user_prompt_override: str | None = None,
    ) -> dict[str, Any]:
        if self.reasoning_client is not None:
            return self._build_query_plan_with_ai(
                market,
                max_queries=max_queries,
                include_debug=include_debug,
                system_prompt_override=system_prompt_override,
                user_prompt_override=user_prompt_override,
            )
        return self._build_query_plan_with_heuristic(
            market,
            max_queries=max_queries,
            include_debug=include_debug,
        )

    def _default_system_prompt(self) -> str:
        fallback = (
            "You are generating Telegram discovery queries for a speed-sensitive geopolitical intelligence system. "
            "Analyze the market, identify the key actors, the countries involved, the official entities, "
            "and the local plus bridge languages that matter. "
            "Produce a compact Telegram search plan with exact official handles when useful, "
            "multilingual keyword groups, and final executable queries. "
            "Return strict JSON only."
        )
        return load_prompt_template("telegram_query_planner/system.txt", fallback)

    def _default_user_prompt(self, market: dict[str, Any], *, max_queries: int) -> str:
        fallback_template = (
            "Generate a Telegram discovery plan for this market.\n\n"
            "Requirements:\n"
            "- Prefer English plus local languages for each country involved.\n"
            "- If Israel is involved, include English, Hebrew, and Arabic.\n"
            "- If Iran is involved, include English and Persian/Farsi, and Arabic when useful as a bridge language.\n"
            "- Prioritize official military/government/spokesperson channels first when relevant.\n"
            "- Then generate journalist, local alert, and community reporting discovery terms.\n"
            "- Include exact official handles when strongly supported.\n"
            "- Generate at most {{MAX_QUERIES}} final queries.\n\n"
            "MARKET_JSON:\n{{MARKET_JSON}}"
        )
        template = load_prompt_template("telegram_query_planner/user.txt", fallback_template)
        return render_prompt_template(
            template,
            {
                "MAX_QUERIES": str(int(max_queries)),
                "MARKET_JSON": json.dumps(self._planner_market_payload(market), ensure_ascii=False, indent=2),
            },
        )

    def _build_query_plan_with_ai(
        self,
        market: dict[str, Any],
        *,
        max_queries: int,
        include_debug: bool,
        system_prompt_override: str | None,
        user_prompt_override: str | None,
    ) -> dict[str, Any]:
        system_prompt = (
            str(system_prompt_override).strip()
            if system_prompt_override and str(system_prompt_override).strip()
            else self._default_system_prompt()
        )
        user_prompt = (
            str(user_prompt_override).strip()
            if user_prompt_override and str(user_prompt_override).strip()
            else self._default_user_prompt(market, max_queries=max_queries)
        )
        payload = self.reasoning_client.generate_json(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name="telegram_query_planner",
            schema=_telegram_query_planner_schema(),
        )
        raw_queries = [
            " ".join(str(query).split()).strip()
            for query in list(payload.get("queries") or [])
            if str(query).strip()
        ]
        raw_candidate_queries = [
            " ".join(str(query).split()).strip()
            for query in list(payload.get("query_candidates") or [])
            if str(query).strip()
        ]
        detected_entities = [self._normalize_detected_entity(item) for item in list(payload.get("detected_entities") or [])]
        official_targets = [self._normalize_official_target(item) for item in list(payload.get("official_targets") or [])]
        keyword_groups = [self._normalize_keyword_group(item) for item in list(payload.get("keyword_groups") or [])]
        candidate_queries = _dedupe_keep_order(
            [
                normalized
                for normalized in (_normalize_search_query_text(query) for query in raw_candidate_queries)
                if normalized and _is_useful_search_query(normalized)
            ]
        )[:48]
        queries = _finalize_ai_planner_queries(
            raw_queries=raw_queries,
            candidate_queries=candidate_queries,
            official_targets=official_targets,
            keyword_groups=keyword_groups,
            max_queries=max(1, int(max_queries)),
        )
        google_queries = _build_google_discovery_queries(
            queries=queries,
            candidate_queries=candidate_queries,
            official_targets=official_targets,
            keyword_groups=keyword_groups,
            max_queries=max(6, int(max_queries) * 4),
        )
        priority_languages = _dedupe_keep_order(
            [str(item).strip().lower() for item in list(payload.get("priority_languages") or []) if str(item).strip()]
        )
        region_hints = _dedupe_keep_order(
            [str(item).strip().lower() for item in list(payload.get("region_hints") or []) if str(item).strip()]
        )
        metrics = {
            "entity_count": len(detected_entities),
            "priority_language_count": len(priority_languages),
            "official_target_count": len(official_targets),
            "keyword_group_count": len(keyword_groups),
            "candidate_query_count": len(candidate_queries),
            "selected_query_count": len(queries),
            "google_query_count": len(google_queries),
        }
        result = {
            "planner_version": self.planner_version,
            "prompt_version": self.prompt_version,
            "query_intent": str(payload.get("query_intent") or "").strip(),
            "question_seed": str(market.get("question") or "")[:90].strip(),
            "rules_excerpt": str(market.get("rules_text") or "")[:240],
            "slug_terms": str(market.get("slug") or "").strip().replace("-", " "),
            "tokens": _dedupe_keep_order(
                [
                    token
                    for token in _tokenize(
                        " ".join(
                            [
                                str(market.get("question") or ""),
                                str(market.get("rules_text") or ""),
                                str(market.get("slug") or "").replace("-", " "),
                            ]
                        )
                    )
                    if token not in _STOPWORDS
                ]
            )[:18],
            "region_hints": region_hints,
            "detected_entities": detected_entities,
            "priority_languages": priority_languages,
            "official_targets": official_targets,
            "keyword_groups": keyword_groups,
            "query_candidates": candidate_queries,
            "queries": queries,
            "google_queries": google_queries,
            "max_queries": int(max_queries),
            "metrics": metrics,
        }
        if include_debug:
            result["prompt_debug"] = {
                "runtime_mode": self.runtime_mode,
                "editable": True,
                "model": self.model,
                "schema_name": "telegram_query_planner",
                "input_materials": self._planner_market_payload(market),
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "output_json": payload,
                "override_applied": bool(
                    (system_prompt_override and str(system_prompt_override).strip())
                    or (user_prompt_override and str(user_prompt_override).strip())
                ),
                "note": "",
            }
        return result

    def _build_query_plan_with_heuristic(
        self,
        market: dict[str, Any],
        *,
        max_queries: int,
        include_debug: bool,
    ) -> dict[str, Any]:
        question = str(market.get("question") or "").strip()
        rules_text = str(market.get("rules_text") or "").strip()
        slug = str(market.get("slug") or "").strip().replace("-", " ")
        base_text = " ".join(part for part in [question, rules_text, slug] if part)

        tokens = [token for token in _tokenize(base_text) if token not in _STOPWORDS]
        tokens = _dedupe_keep_order(tokens)

        detected_entities = self._detect_entities(base_text)
        query_intent = self._build_query_intent(detected_entities)
        region_hints: list[str] = []
        reason_json = market.get("analysis_reason_json") or {}
        if isinstance(reason_json, dict):
            for region in reason_json.get("priority_regions") or []:
                hints = _REGION_HINT_QUERIES.get(str(region), ())
                region_hints.extend(hints)

        keyword_groups = self._build_keyword_groups(detected_entities)
        official_targets = self._build_official_targets(detected_entities)
        priority_languages = _dedupe_keep_order(
            [
                language
                for entity in detected_entities
                for language in entity["search_languages"]
            ]
        )

        candidate_queries: list[str] = []
        if question:
            candidate_queries.append(question[:90].strip())
        for target in official_targets:
            candidate_queries.extend(list(target.get("handles") or []))
            candidate_queries.extend(list(target.get("queries") or []))
        for group in keyword_groups:
            terms = list(group.get("query_terms") or [])
            if len(terms) >= 2:
                candidate_queries.append(" ".join(terms[:2]))
            candidate_queries.extend(terms[:2])
        if len(tokens) >= 3:
            candidate_queries.append(" ".join(tokens[:3]))
        if len(tokens) >= 2:
            candidate_queries.append(" ".join(tokens[:2]))
        candidate_queries.extend(tokens[:6])
        candidate_queries.extend(region_hints)

        queries: list[str] = []
        seen = set()
        for query in candidate_queries:
            compact = " ".join(str(query).split()).strip()
            if not compact:
                continue
            lowered = compact.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            queries.append(compact)
            if len(queries) >= max_queries:
                break
        google_queries = _build_google_discovery_queries(
            queries=queries,
            candidate_queries=_dedupe_keep_order(
                [" ".join(str(query).split()).strip() for query in candidate_queries if str(query).strip()]
            )[:48],
            official_targets=official_targets,
            keyword_groups=keyword_groups,
            max_queries=max(6, int(max_queries) * 4),
        )

        result = {
            "planner_version": self.planner_version,
            "prompt_version": self.prompt_version,
            "query_intent": query_intent,
            "question_seed": question[:90].strip() if question else "",
            "rules_excerpt": rules_text[:240],
            "slug_terms": slug,
            "tokens": tokens[:18],
            "region_hints": _dedupe_keep_order(region_hints),
            "detected_entities": detected_entities,
            "priority_languages": priority_languages,
            "official_targets": official_targets,
            "keyword_groups": keyword_groups,
            "query_candidates": _dedupe_keep_order(
                [" ".join(str(query).split()).strip() for query in candidate_queries if str(query).strip()]
            )[:48],
            "queries": queries,
            "google_queries": google_queries,
            "max_queries": int(max_queries),
            "metrics": {
                "entity_count": len(detected_entities),
                "priority_language_count": len(priority_languages),
                "official_target_count": len(official_targets),
                "keyword_group_count": len(keyword_groups),
                "candidate_query_count": len(
                    _dedupe_keep_order(
                        [" ".join(str(query).split()).strip() for query in candidate_queries if str(query).strip()]
                    )
                ),
                "selected_query_count": len(queries),
                "google_query_count": len(google_queries),
            },
        }
        if include_debug:
            result["prompt_debug"] = {
                "runtime_mode": self.runtime_mode,
                "editable": False,
                "model": None,
                "schema_name": "telegram_query_planner",
                "input_materials": self._planner_market_payload(market),
                "system_prompt": self._default_system_prompt(),
                "user_prompt": self._default_user_prompt(market, max_queries=max_queries),
                "output_json": None,
                "override_applied": False,
                "note": "AI runtime is not enabled. This planner output was generated by the heuristic fallback. Add OPENAI_API_KEY to edit the prompt and rerun with AI.",
            }
        return result

    def build_queries(self, market: dict[str, Any], *, max_queries: int) -> list[str]:
        return list(self.build_query_plan(market, max_queries=max_queries)["queries"])

    def _planner_market_payload(self, market: dict[str, Any]) -> dict[str, Any]:
        reason_json = market.get("analysis_reason_json") or {}
        return {
            "market_id": str(market.get("market_id") or ""),
            "slug": str(market.get("slug") or ""),
            "question": str(market.get("question") or ""),
            "description": str(market.get("description") or ""),
            "rules_text": str(market.get("rules_text") or ""),
            "market_context": str(market.get("market_context") or ""),
            "market_archetype": str(market.get("market_archetype") or "unknown"),
            "analysis_reason_json": reason_json if isinstance(reason_json, dict) else {},
        }

    def _normalize_detected_entity(self, value: Any) -> dict[str, Any]:
        item = value if isinstance(value, dict) else {}
        return {
            "entity_key": str(item.get("entity_key") or "").strip().lower(),
            "label": str(item.get("label") or item.get("entity_key") or "").strip(),
            "aliases_hit": _dedupe_keep_order(
                [str(alias).strip() for alias in list(item.get("aliases_hit") or []) if str(alias).strip()]
            )[:8],
            "local_languages": _dedupe_keep_order(
                [str(code).strip().lower() for code in list(item.get("local_languages") or []) if str(code).strip()]
            )[:6],
            "bridge_languages": _dedupe_keep_order(
                [str(code).strip().lower() for code in list(item.get("bridge_languages") or []) if str(code).strip()]
            )[:6],
            "search_languages": _dedupe_keep_order(
                [str(code).strip().lower() for code in list(item.get("search_languages") or []) if str(code).strip()]
            )[:8],
        }

    def _normalize_official_target(self, value: Any) -> dict[str, Any]:
        item = value if isinstance(value, dict) else {}
        return {
            "entity_key": str(item.get("entity_key") or "").strip().lower(),
            "entity_label": str(item.get("entity_label") or item.get("entity_key") or "").strip(),
            "label": str(item.get("label") or "").strip(),
            "type": str(item.get("type") or "official").strip(),
            "handles": _dedupe_keep_order(
                [str(handle).strip() for handle in list(item.get("handles") or []) if str(handle).strip()]
            )[:8],
            "queries": _dedupe_keep_order(
                [str(query).strip() for query in list(item.get("queries") or []) if str(query).strip()]
            )[:8],
        }

    def _normalize_keyword_group(self, value: Any) -> dict[str, Any]:
        item = value if isinstance(value, dict) else {}
        return {
            "entity_key": str(item.get("entity_key") or "").strip().lower(),
            "entity_label": str(item.get("entity_label") or item.get("entity_key") or "").strip(),
            "language_code": str(item.get("language_code") or "").strip().lower(),
            "query_terms": _dedupe_keep_order(
                [str(term).strip() for term in list(item.get("query_terms") or []) if str(term).strip()]
            )[:6],
        }

    def _detect_entities(self, text: str) -> list[dict[str, Any]]:
        searchable = str(text or "").lower()
        entities: list[dict[str, Any]] = []
        for key, actor in _ACTOR_SEEDS.items():
            aliases_hit = [
                alias
                for alias in actor["aliases"]
                if str(alias).lower() in searchable
            ]
            if not aliases_hit:
                continue
            local_languages = list(actor.get("local_languages") or ())
            bridge_languages = list(actor.get("bridge_languages") or ())
            search_languages = _dedupe_keep_order(local_languages + bridge_languages)
            entities.append(
                {
                    "entity_key": key,
                    "label": actor["label"],
                    "aliases_hit": _dedupe_keep_order(aliases_hit),
                    "local_languages": local_languages,
                    "bridge_languages": bridge_languages,
                    "search_languages": search_languages,
                }
            )
        return entities

    def _build_query_intent(self, detected_entities: list[dict[str, Any]]) -> str:
        if not detected_entities:
            return "Find public Telegram channels relevant to this market in English and local reporting contexts."
        labels = [item["label"] for item in detected_entities]
        return (
            "Find official, journalist, and local alert Telegram channels covering "
            + ", ".join(labels)
            + " across local and bridge languages."
        )

    def _build_keyword_groups(self, detected_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for entity in detected_entities:
            actor = _ACTOR_SEEDS.get(entity["entity_key"], {})
            keyword_map = actor.get("keywords") or {}
            for language_code in entity["search_languages"]:
                query_terms = list(keyword_map.get(language_code, ()))
                if not query_terms:
                    continue
                groups.append(
                    {
                        "entity_key": entity["entity_key"],
                        "entity_label": entity["label"],
                        "language_code": language_code,
                        "query_terms": query_terms[:4],
                    }
                )
        return groups

    def _build_official_targets(self, detected_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        for entity in detected_entities:
            actor = _ACTOR_SEEDS.get(entity["entity_key"], {})
            for target in actor.get("official_targets") or ():
                targets.append(
                    {
                        "entity_key": entity["entity_key"],
                        "entity_label": entity["label"],
                        "label": target.get("label"),
                        "type": target.get("type", "official"),
                        "handles": list(target.get("handles") or ()),
                        "queries": list(target.get("queries") or ()),
                    }
                )
        return targets


def _telegram_query_planner_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "query_intent",
            "detected_entities",
            "priority_languages",
            "region_hints",
            "official_targets",
            "keyword_groups",
            "query_candidates",
            "queries",
        ],
        "properties": {
            "query_intent": {"type": "string"},
            "detected_entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "entity_key",
                        "label",
                        "aliases_hit",
                        "local_languages",
                        "bridge_languages",
                        "search_languages",
                    ],
                    "properties": {
                        "entity_key": {"type": "string"},
                        "label": {"type": "string"},
                        "aliases_hit": {"type": "array", "items": {"type": "string"}},
                        "local_languages": {"type": "array", "items": {"type": "string"}},
                        "bridge_languages": {"type": "array", "items": {"type": "string"}},
                        "search_languages": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "priority_languages": {"type": "array", "items": {"type": "string"}},
            "region_hints": {"type": "array", "items": {"type": "string"}},
            "official_targets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["entity_key", "entity_label", "label", "type", "handles", "queries"],
                    "properties": {
                        "entity_key": {"type": "string"},
                        "entity_label": {"type": "string"},
                        "label": {"type": "string"},
                        "type": {"type": "string"},
                        "handles": {"type": "array", "items": {"type": "string"}},
                        "queries": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "keyword_groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["entity_key", "entity_label", "language_code", "query_terms"],
                    "properties": {
                        "entity_key": {"type": "string"},
                        "entity_label": {"type": "string"},
                        "language_code": {"type": "string"},
                        "query_terms": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "query_candidates": {"type": "array", "items": {"type": "string"}},
            "queries": {"type": "array", "items": {"type": "string"}},
        },
    }


class BacktestChannelReviewer:
    reviewer_version = "ai_channel_reviewer_v1"
    prompt_version = "telegram-channel-review-v1-ai"

    def __init__(
        self,
        *,
        reasoning_client: JSONReasoningClient | None = None,
        model: str | None = None,
        config: PolymarketConfig | None = None,
    ):
        self.config = config or PolymarketConfig.from_env()
        self.reasoning_client = reasoning_client or resolve_reasoning_client(self.config, required=False)
        self.model = model or self.config.ai_telegram_channel_relevance_model
        self.runtime_mode = "ai" if self.reasoning_client is not None else "heuristic_legacy"
        self.reviewer_version = (
            "ai_channel_reviewer_v1"
            if self.runtime_mode == "ai"
            else "heuristic_channel_reviewer_v1"
        )
        self.prompt_version = (
            "telegram-channel-review-v1-ai"
            if self.runtime_mode == "ai"
            else "telegram-channel-review-v0-heuristic"
        )

    def review(
        self,
        *,
        market: dict[str, Any],
        channel: dict[str, Any],
        source_context: dict[str, Any],
        recent_messages: list[dict[str, Any]],
        system_prompt_override: str | None = None,
        user_prompt_override: str | None = None,
    ) -> dict[str, Any]:
        if self.reasoning_client is None:
            return self._review_with_heuristic(
                market=market,
                channel=channel,
                source_context=source_context,
                recent_messages=recent_messages,
            )
        return self._review_with_ai(
            market=market,
            channel=channel,
            source_context=source_context,
            recent_messages=recent_messages,
            system_prompt_override=system_prompt_override,
            user_prompt_override=user_prompt_override,
        )

    def _review_with_ai(
        self,
        *,
        market: dict[str, Any],
        channel: dict[str, Any],
        source_context: dict[str, Any],
        recent_messages: list[dict[str, Any]],
        system_prompt_override: str | None,
        user_prompt_override: str | None,
    ) -> dict[str, Any]:
        input_payload = self._review_input_payload(
            market=market,
            channel=channel,
            source_context=source_context,
            recent_messages=recent_messages,
        )
        system_prompt = (
            str(system_prompt_override).strip()
            if system_prompt_override and str(system_prompt_override).strip()
            else self._default_system_prompt()
        )
        user_prompt = (
            str(user_prompt_override).strip()
            if user_prompt_override and str(user_prompt_override).strip()
            else self._default_user_prompt(input_payload)
        )
        payload = self.reasoning_client.generate_json(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name="telegram_channel_reviewer",
            schema=_telegram_channel_reviewer_schema(),
        )
        is_relevant = bool(payload.get("is_relevant"))
        decision = str(payload.get("decision") or ("keep" if is_relevant else "drop")).strip().lower()
        if decision not in {"keep", "drop"}:
            decision = "keep" if is_relevant else "drop"
        return {
            "reviewer_version": self.reviewer_version,
            "prompt_version": self.prompt_version,
            "runtime_mode": self.runtime_mode,
            "is_relevant": is_relevant,
            "decision": decision,
            "reason_short": str(payload.get("reason_short") or "").strip(),
            "reason_detailed": [
                str(item).strip()
                for item in list(payload.get("reason_detailed") or [])
                if str(item).strip()
            ][:8],
            "signals": [
                str(item).strip()
                for item in list(payload.get("signals") or [])
                if str(item).strip()
            ][:12],
            "prompt_debug": {
                "runtime_mode": self.runtime_mode,
                "editable": False,
                "model": self.model,
                "schema_name": "telegram_channel_reviewer",
                "input_materials": input_payload,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "output_json": payload,
                "override_applied": bool(
                    (system_prompt_override and str(system_prompt_override).strip())
                    or (user_prompt_override and str(user_prompt_override).strip())
                ),
                "note": "",
            },
        }

    def _review_with_heuristic(
        self,
        *,
        market: dict[str, Any],
        channel: dict[str, Any],
        source_context: dict[str, Any],
        recent_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        market_profile = build_market_channel_profile(market)
        relevance = evaluate_channel_relevance(channel, market_profile, min_score=0.18)
        is_relevant = bool(relevance.is_relevant)
        return {
            "reviewer_version": self.reviewer_version,
            "prompt_version": self.prompt_version,
            "runtime_mode": self.runtime_mode,
            "is_relevant": is_relevant,
            "decision": "keep" if is_relevant else "drop",
            "reason_short": relevance.reason,
            "reason_detailed": [relevance.reason],
            "signals": [
                *list(relevance.matched_entities),
                *list(relevance.matched_phrases),
                *list(relevance.matched_terms),
            ][:12],
            "prompt_debug": {
                "runtime_mode": self.runtime_mode,
                "editable": False,
                "model": None,
                "schema_name": "telegram_channel_reviewer",
                "input_materials": self._review_input_payload(
                    market=market,
                    channel=channel,
                    source_context=source_context,
                    recent_messages=recent_messages,
                ),
                "system_prompt": self._default_system_prompt(),
                "user_prompt": self._default_user_prompt(
                    self._review_input_payload(
                        market=market,
                        channel=channel,
                        source_context=source_context,
                        recent_messages=recent_messages,
                    )
                ),
                "output_json": None,
                "override_applied": False,
                "note": "AI runtime is not enabled. Channel review used heuristic fallback.",
            },
        }

    def _default_system_prompt(self) -> str:
        fallback = (
            "You are reviewing Telegram channel relevance for one Polymarket market. "
            "Decide if this channel is relevant to market rules and context based on metadata and recent messages. "
            "Return strict JSON only."
        )
        return load_prompt_template("telegram_channel_reviewer/system.txt", fallback)

    def _default_user_prompt(self, input_payload: dict[str, Any]) -> str:
        fallback_template = (
            "Review this channel for market relevance.\n\n"
            "Requirements:\n"
            "- Keep or drop this channel for this market.\n"
            "- Return a strict yes/no relevance decision.\n"
            "- Use recent messages as primary evidence, metadata as supporting context.\n"
            "- Mention if channel appears off-topic, generic, spammy, or not aligned with market rules.\n\n"
            "INPUT_JSON:\n{{INPUT_JSON}}"
        )
        template = load_prompt_template("telegram_channel_reviewer/user.txt", fallback_template)
        return render_prompt_template(
            template,
            {
                "INPUT_JSON": json.dumps(input_payload, ensure_ascii=False, indent=2),
            },
        )

    def _review_input_payload(
        self,
        *,
        market: dict[str, Any],
        channel: dict[str, Any],
        source_context: dict[str, Any],
        recent_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        compact_messages = []
        for message in list(recent_messages or [])[:10]:
            compact_messages.append(
                {
                    "message_id": message.get("message_id"),
                    "posted_at": message.get("posted_at"),
                    "text": str(message.get("text") or "")[:600],
                }
            )
        return {
            "market": {
                "market_id": str(market.get("market_id") or ""),
                "slug": str(market.get("slug") or ""),
                "question": str(market.get("question") or ""),
                "rules_text": str(market.get("rules_text") or ""),
                "market_context": str(market.get("market_context") or ""),
                "market_archetype": str(market.get("market_archetype") or "unknown"),
            },
            "channel": {
                "chat_id": int(channel.get("chat_id") or 0),
                "title": str(channel.get("title") or ""),
                "username": str(channel.get("username") or ""),
                "description": str(channel.get("description") or ""),
                "member_count": channel.get("member_count"),
                "is_verified": bool(channel.get("is_verified", False)),
                "is_fake": bool(channel.get("is_fake", False)),
                "is_scam": bool(channel.get("is_scam", False)),
            },
            "source_context": source_context,
            "recent_messages": compact_messages,
        }


def _telegram_channel_reviewer_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "is_relevant",
            "decision",
            "reason_short",
            "reason_detailed",
            "signals",
        ],
        "properties": {
            "is_relevant": {"type": "boolean"},
            "decision": {"type": "string", "enum": ["keep", "drop"]},
            "reason_short": {"type": "string"},
            "reason_detailed": {"type": "array", "items": {"type": "string"}},
            "signals": {"type": "array", "items": {"type": "string"}},
        },
    }


def _telegram_message_matcher_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "is_match",
            "reason_short",
            "matched_terms",
            "matched_phrases",
        ],
        "properties": {
            "is_match": {"type": "boolean"},
            "reason_short": {"type": "string"},
            "matched_terms": {"type": "array", "items": {"type": "string"}},
            "matched_phrases": {"type": "array", "items": {"type": "string"}},
        },
    }


class MarketMessageMatcher:
    def __init__(
        self,
        *,
        matcher_version: str = "v1",
        config: PolymarketConfig | None = None,
        reasoning_client: JSONReasoningClient | None = None,
        model: str | None = None,
    ):
        self.config = config or PolymarketConfig.from_env()
        if reasoning_client is not None:
            self.reasoning_client = reasoning_client
        elif bool(self.config.ai_enable_message_matcher):
            if self.config.ai_message_matcher_api_key:
                self.reasoning_client = OpenAIJSONReasoningClient(
                    api_key=self.config.ai_message_matcher_api_key,
                    base_url=self.config.ai_message_matcher_base_url or self.config.openai_base_url,
                    http_referer=(
                        self.config.ai_message_matcher_http_referer
                        or self.config.openai_http_referer
                    ),
                    app_name=(
                        self.config.ai_message_matcher_app_name
                        or self.config.openai_app_name
                    ),
                    timeout_seconds=self.config.openai_timeout_seconds,
                )
            else:
                self.reasoning_client = resolve_reasoning_client(self.config, required=False)
        else:
            self.reasoning_client = None
        self.model = model or self.config.ai_telegram_message_matcher_model
        self.runtime_mode = "ai" if self.reasoning_client is not None else "heuristic_legacy"
        self.prompt_version = (
            "telegram-message-matcher-v1-ai"
            if self.runtime_mode == "ai"
            else "telegram-message-matcher-v0-heuristic"
        )
        self.matcher_version = (
            f"ai_message_matcher_v1:{self.model}"
            if self.runtime_mode == "ai"
            else matcher_version
        )
        self._profile_cache: dict[str, _MatcherProfile] = {}

    def profile_for_market(self, market: dict[str, Any]) -> _MatcherProfile:
        market_id = str(market["market_id"])
        cached = self._profile_cache.get(market_id)
        if cached is not None:
            return cached

        text_parts = [
            str(market.get("question") or ""),
            str(market.get("rules_text") or ""),
            str(market.get("market_context") or ""),
        ]
        combined = " ".join(text_parts).lower()
        terms = {
            token
            for token in _tokenize(combined)
            if token not in _STOPWORDS and len(token) >= 4
        }
        phrases = tuple(phrase for phrase in _PHRASE_TERMS if phrase in combined)
        profile = _MatcherProfile(
            market_id=market_id,
            market_archetype=str(market.get("market_archetype") or "unknown"),
            question=str(market.get("question") or ""),
            rules_text=str(market.get("rules_text") or ""),
            market_context=str(market.get("market_context") or ""),
            terms=set(sorted(terms)[:40]),
            phrases=phrases,
            min_overlap=2,
        )
        self._profile_cache[market_id] = profile
        return profile

    def evaluate(self, text: str, profile: _MatcherProfile) -> MatchDecision:
        if self.reasoning_client is not None:
            try:
                return self._evaluate_with_ai(text, profile)
            except Exception:
                # Keep listener resilient: if AI provider is unavailable, fall back to deterministic matching.
                pass

        return self._evaluate_with_heuristic(text, profile)

    def _evaluate_with_heuristic(self, text: str, profile: _MatcherProfile) -> MatchDecision:
        normalized = (text or "").strip().lower()
        if not normalized:
            return MatchDecision(
                is_match=False,
                reason_short="empty_message",
                matched_terms=[],
                matched_phrases=[],
            )

        message_tokens = set(_tokenize(normalized))
        matched_terms = sorted(message_tokens.intersection(profile.terms))
        matched_phrases = [phrase for phrase in profile.phrases if phrase in normalized]

        is_match = len(matched_terms) >= profile.min_overlap or len(matched_phrases) > 0
        reason = (
            f"overlap={len(matched_terms)} phrase_hits={len(matched_phrases)}"
            if is_match
            else f"no_match overlap={len(matched_terms)}"
        )
        return MatchDecision(
            is_match=is_match,
            reason_short=reason,
            matched_terms=matched_terms[:8],
            matched_phrases=matched_phrases[:4],
        )

    def _default_system_prompt(self) -> str:
        fallback = (
            "You classify whether one Telegram message is relevant to one Polymarket market. "
            "Return strict JSON only. Be conservative: mark is_match=true only if the message likely helps resolve "
            "or materially updates the market outcome."
        )
        return load_prompt_template("telegram_message_matcher/system.txt", fallback)

    def _default_user_prompt(self, text: str, profile: _MatcherProfile) -> str:
        fallback_template = (
            "Determine if this Telegram message is relevant for the market.\n\n"
            "MARKET:\n"
            "- market_id: {{MARKET_ID}}\n"
            "- archetype: {{MARKET_ARCHETYPE}}\n"
            "- question: {{QUESTION}}\n"
            "- rules_text: {{RULES_TEXT}}\n"
            "- market_context: {{MARKET_CONTEXT}}\n\n"
            "MESSAGE:\n{{MESSAGE_TEXT}}\n"
        )
        template = load_prompt_template("telegram_message_matcher/user.txt", fallback_template)
        return render_prompt_template(
            template,
            {
                "MARKET_ID": profile.market_id,
                "MARKET_ARCHETYPE": profile.market_archetype,
                "QUESTION": profile.question,
                "RULES_TEXT": profile.rules_text,
                "MARKET_CONTEXT": profile.market_context,
                "MESSAGE_TEXT": text[:3000],
            },
        )

    def _evaluate_with_ai(self, text: str, profile: _MatcherProfile) -> MatchDecision:
        normalized = (text or "").strip()
        if not normalized:
            return MatchDecision(
                is_match=False,
                reason_short="empty_message",
                matched_terms=[],
                matched_phrases=[],
            )

        payload = self.reasoning_client.generate_json(
            model=self.model,
            system_prompt=self._default_system_prompt(),
            user_prompt=self._default_user_prompt(normalized, profile),
            schema_name="telegram_message_matcher",
            schema=_telegram_message_matcher_schema(),
        )

        is_match = bool(payload.get("is_match"))
        reason_short = str(payload.get("reason_short") or "").strip()
        if not reason_short:
            reason_short = "ai_match" if is_match else "ai_no_match"

        matched_terms = [
            str(item).strip()
            for item in list(payload.get("matched_terms") or [])
            if str(item).strip()
        ][:8]
        matched_phrases = [
            str(item).strip()
            for item in list(payload.get("matched_phrases") or [])
            if str(item).strip()
        ][:4]
        return MatchDecision(
            is_match=is_match,
            reason_short=reason_short,
            matched_terms=matched_terms,
            matched_phrases=matched_phrases,
        )


class MarketTelegramDiscoveryService:
    def __init__(
        self,
        repository: MarketIntelRepository,
        tdlib_client: TDLibDiscoveryClient,
        planner: MarketSearchPlanner | None = None,
        channel_reviewer: BacktestChannelReviewer | None = None,
        serp_client: GoogleSerpClient | None = None,
        log_fn: Callable[[str], None] | None = None,
    ):
        self.repository = repository
        self.tdlib_client = tdlib_client
        self.planner = planner or MarketSearchPlanner()
        self.channel_reviewer = channel_reviewer or BacktestChannelReviewer()
        self.serp_client = serp_client or GoogleSerpClient.from_config(self.planner.config)
        self._log = log_fn or (lambda _: None)

    async def _execute_discovery_query(self, query: str, *, limit: int) -> dict[str, Any]:
        normalized_query = _normalize_search_query_text(query)
        if not normalized_query:
            return {
                "query": "",
                "query_type": "empty",
                "channels": [],
                "result_count": 0,
            }

        primary_handle = _extract_primary_handle(normalized_query)
        errors: list[TDLibRequestError] = []

        if primary_handle:
            channels_by_id: dict[int, dict[str, Any]] = {}
            query_type = (
                "exact_handle"
                if _HANDLE_ONLY_RE.fullmatch(normalized_query)
                else "handle_plus_search"
            )
            try:
                channel = await self.tdlib_client.search_public_chat(primary_handle)
                if channel:
                    channels_by_id[int(channel["chat_id"])] = channel
            except TDLibRequestError as exc:
                errors.append(exc)
                self._log(
                    f"channel_discovery_handle_error handle={primary_handle!r} query={normalized_query!r} error={exc}"
                )

            fallback_query = _strip_handle_tokens(normalized_query)
            if (
                query_type == "handle_plus_search"
                and fallback_query
                and _is_useful_search_query(fallback_query)
            ):
                try:
                    for channel in await self.tdlib_client.search_public_chats(fallback_query, limit):
                        channels_by_id[int(channel["chat_id"])] = channel
                except TDLibRequestError as exc:
                    errors.append(exc)
                    self._log(
                        f"channel_discovery_fallback_search_error query={fallback_query!r} "
                        f"source_query={normalized_query!r} error={exc}"
                    )

            channels = list(channels_by_id.values())[:limit]
            if not channels and errors:
                raise errors[-1]
            return {
                "query": normalized_query,
                "query_type": query_type,
                "channels": channels,
                "result_count": len(channels),
            }

        channels = await self.tdlib_client.search_public_chats(normalized_query, limit)
        return {
            "query": normalized_query,
            "query_type": "public_search",
            "channels": channels,
            "result_count": len(channels),
        }

    async def discover_once(
        self,
        *,
        market_limit: int = 30,
        target_channels_per_market: int = 25,
        global_max_channels: int = 500,
        query_results_limit: int = 20,
        max_queries_per_market: int = 6,
        similar_per_seed: int = 10,
        similar_seed_channels: int = 3,
        min_channel_members: int = 1000,
        min_channel_relevance_score: float = 0.18,
        enable_google_serp: bool = True,
        max_google_queries_per_market: int = 8,
        google_results_per_query: int = 8,
        market_progress_callback: Any = None,
    ) -> ChannelDiscoveryStats:
        markets = self.repository.get_track_now_markets(limit=market_limit)
        links_written = 0
        channels_written = 0
        queries_sent = 0
        api_errors = 0
        markets_updated = 0
        seen_channel_ids: set[int] = set()
        total_markets = len(markets)

        for market_index, market in enumerate(markets, start=1):
            market_id = str(market["market_id"])
            mapped_channels = int(market.get("mapped_channels") or 0)
            await self._emit_market_progress(
                market_progress_callback,
                {
                    "state": "market_start",
                    "market_id": market_id,
                    "market_slug": str(market.get("slug") or ""),
                    "market_question": str(market.get("question") or ""),
                    "market_index": int(market_index),
                    "market_total": int(total_markets),
                    "mapped_channels": int(mapped_channels),
                    "target_channels_per_market": int(target_channels_per_market),
                },
            )
            if mapped_channels >= target_channels_per_market:
                await self._emit_market_progress(
                    market_progress_callback,
                    {
                        "state": "market_skip_already_full",
                        "market_id": market_id,
                        "market_slug": str(market.get("slug") or ""),
                        "market_question": str(market.get("question") or ""),
                        "market_index": int(market_index),
                        "market_total": int(total_markets),
                        "mapped_channels": int(mapped_channels),
                        "target_channels_per_market": int(target_channels_per_market),
                    },
                )
                continue

            needed = max(0, target_channels_per_market - mapped_channels)
            if needed == 0:
                await self._emit_market_progress(
                    market_progress_callback,
                    {
                        "state": "market_skip_no_need",
                        "market_id": market_id,
                        "market_slug": str(market.get("slug") or ""),
                        "market_question": str(market.get("question") or ""),
                        "market_index": int(market_index),
                        "market_total": int(total_markets),
                        "mapped_channels": int(mapped_channels),
                        "target_channels_per_market": int(target_channels_per_market),
                    },
                )
                continue

            plan = self.planner.build_query_plan(market, max_queries=max_queries_per_market)
            queries = list(plan["queries"])
            google_queries = [
                _normalize_search_query_text(item)
                for item in list(plan.get("google_queries") or [])
                if _normalize_search_query_text(item)
            ]
            if not queries:
                await self._emit_market_progress(
                    market_progress_callback,
                    {
                        "state": "market_skip_no_queries",
                        "market_id": market_id,
                        "market_slug": str(market.get("slug") or ""),
                        "market_question": str(market.get("question") or ""),
                        "market_index": int(market_index),
                        "market_total": int(total_markets),
                        "mapped_channels": int(mapped_channels),
                        "target_channels_per_market": int(target_channels_per_market),
                    },
                )
                continue

            market_profile = build_market_channel_profile(market)
            reason_json = market.get("analysis_reason_json") or {}
            language_hint = []
            if isinstance(reason_json, dict):
                raw_languages = reason_json.get("priority_languages") or []
                language_hint = [str(code) for code in raw_languages if str(code)]

            candidates: dict[int, dict[str, Any]] = {}
            candidate_source: dict[int, str] = {}
            rejected_low_members = 0
            rejected_low_relevance = 0

            if (
                enable_google_serp
                and self.serp_client is not None
                and self.serp_client.enabled
                and google_queries
            ):
                for google_query in google_queries[: max(1, int(max_google_queries_per_market))]:
                    if len(seen_channel_ids) >= global_max_channels:
                        break
                    try:
                        serp_result = self.serp_client.search_tme(
                            google_query,
                            max_results=max(1, min(int(google_results_per_query), 20)),
                        )
                    except GoogleSerpError as exc:
                        api_errors += 1
                        self._log(
                            f"channel_discovery_serp_error market_id={market_id} query={google_query!r} error={exc}"
                        )
                        continue

                    queries_sent += 1
                    for handle in serp_result.handles:
                        if len(seen_channel_ids) >= global_max_channels:
                            break
                        try:
                            query_run = await self._execute_discovery_query(
                                f"@{handle}",
                                limit=max(1, min(int(query_results_limit), 50)),
                            )
                            queries_sent += 1
                        except TDLibRequestError as exc:
                            if _is_auth_key_duplicated(exc):
                                raise
                            api_errors += 1
                            self._log(
                                f"channel_discovery_serp_handle_error market_id={market_id} "
                                f"handle={handle!r} source_query={google_query!r} error={exc}"
                            )
                            continue

                        for channel in list(query_run["channels"]):
                            chat_id = int(channel["chat_id"])
                            if chat_id not in seen_channel_ids and len(seen_channel_ids) >= global_max_channels:
                                break
                            if chat_id in candidates:
                                continue
                            member_count = _sort_member_count(channel.get("member_count"))
                            if member_count < int(min_channel_members):
                                rejected_low_members += 1
                                continue
                            relevance = evaluate_channel_relevance(
                                channel,
                                market_profile,
                                min_score=min_channel_relevance_score,
                            )
                            if not relevance.is_relevant:
                                rejected_low_relevance += 1
                                continue
                            seen_channel_ids.add(chat_id)
                            candidates[chat_id] = {
                                **channel,
                                "language_hint": language_hint,
                                "notes": relevance.reason,
                                "discovery_relevance_score": relevance.score,
                                "discovery_relevance_label": relevance.label,
                                "discovery_relevance_reason": relevance.reason,
                                "raw_json": {
                                    **channel,
                                    "discovery_relevance": {
                                        "score": relevance.score,
                                        "label": relevance.label,
                                        "reason": relevance.reason,
                                        "matched_terms": list(relevance.matched_terms),
                                        "matched_entities": list(relevance.matched_entity_terms),
                                        "matched_phrases": list(relevance.matched_phrases),
                                    },
                                    "serp_source_query": google_query,
                                    "serp_provider": serp_result.provider,
                                },
                            }
                            candidate_source[chat_id] = "auto_google_serp"

            for query in queries:
                if len(seen_channel_ids) >= global_max_channels:
                    break
                try:
                    query_run = await self._execute_discovery_query(query, limit=query_results_limit)
                    queries_sent += 1
                except TDLibRequestError as exc:
                    if _is_auth_key_duplicated(exc):
                        raise
                    api_errors += 1
                    self._log(f"channel_discovery_error market_id={market_id} query={query!r} error={exc}")
                    continue

                for channel in list(query_run["channels"]):
                    chat_id = int(channel["chat_id"])
                    if chat_id not in seen_channel_ids and len(seen_channel_ids) >= global_max_channels:
                        break
                    if chat_id in candidates:
                        continue
                    member_count = _sort_member_count(channel.get("member_count"))
                    if member_count < int(min_channel_members):
                        rejected_low_members += 1
                        continue
                    relevance = evaluate_channel_relevance(
                        channel,
                        market_profile,
                        min_score=min_channel_relevance_score,
                    )
                    if not relevance.is_relevant:
                        rejected_low_relevance += 1
                        continue
                    seen_channel_ids.add(chat_id)
                    candidates[chat_id] = {
                        **channel,
                        "language_hint": language_hint,
                        "notes": relevance.reason,
                        "discovery_relevance_score": relevance.score,
                        "discovery_relevance_label": relevance.label,
                        "discovery_relevance_reason": relevance.reason,
                        "raw_json": {
                            **channel,
                            "discovery_relevance": {
                                "score": relevance.score,
                                "label": relevance.label,
                                "reason": relevance.reason,
                                "matched_terms": list(relevance.matched_terms),
                                "matched_entities": list(relevance.matched_entity_terms),
                                "matched_phrases": list(relevance.matched_phrases),
                            },
                        },
                    }
                    candidate_source[chat_id] = "auto_search"

            if similar_per_seed > 0 and candidates:
                ranked_seed_ids = [
                    int(item["chat_id"])
                    for item in sorted(
                        candidates.values(),
                        key=lambda channel: (
                            float(channel.get("discovery_relevance_score") or 0.0),
                            _sort_member_count(channel.get("member_count")),
                        ),
                        reverse=True,
                    )
                ]
                for seed_chat_id in ranked_seed_ids[:similar_seed_channels]:
                    try:
                        similar_channels = await self.tdlib_client.get_chat_similar_chats(seed_chat_id)
                    except TDLibRequestError as exc:
                        if _is_auth_key_duplicated(exc):
                            raise
                        api_errors += 1
                        self._log(
                            f"channel_discovery_similar_error market_id={market_id} "
                            f"seed_chat_id={seed_chat_id} error={exc}"
                        )
                        continue

                    accepted = 0
                    for channel in similar_channels:
                        if accepted >= similar_per_seed:
                            break
                        chat_id = int(channel["chat_id"])
                        if chat_id not in seen_channel_ids and len(seen_channel_ids) >= global_max_channels:
                            break
                        if chat_id in candidates:
                            continue
                        member_count = _sort_member_count(channel.get("member_count"))
                        if member_count < int(min_channel_members):
                            rejected_low_members += 1
                            continue
                        relevance = evaluate_channel_relevance(
                            channel,
                            market_profile,
                            min_score=min_channel_relevance_score,
                        )
                        if not relevance.is_relevant:
                            rejected_low_relevance += 1
                            continue
                        seen_channel_ids.add(chat_id)
                        accepted += 1
                        candidates[chat_id] = {
                            **channel,
                            "language_hint": language_hint,
                            "notes": relevance.reason,
                            "discovery_relevance_score": relevance.score,
                            "discovery_relevance_label": relevance.label,
                            "discovery_relevance_reason": relevance.reason,
                            "raw_json": {
                                **channel,
                                "discovery_relevance": {
                                    "score": relevance.score,
                                    "label": relevance.label,
                                    "reason": relevance.reason,
                                    "matched_terms": list(relevance.matched_terms),
                                    "matched_entities": list(relevance.matched_entity_terms),
                                    "matched_phrases": list(relevance.matched_phrases),
                                },
                            },
                        }
                        candidate_source[chat_id] = "auto_similar"

            ranked_candidates = sorted(
                candidates.values(),
                key=lambda channel: (
                    float(channel.get("discovery_relevance_score") or 0.0),
                    _sort_member_count(channel.get("member_count")),
                ),
                reverse=True,
            )
            selected = ranked_candidates[:needed]
            if not selected:
                await self._emit_market_progress(
                    market_progress_callback,
                    {
                        "state": "market_skip_no_selected",
                        "market_id": market_id,
                        "market_slug": str(market.get("slug") or ""),
                        "market_question": str(market.get("question") or ""),
                        "market_index": int(market_index),
                        "market_total": int(total_markets),
                        "mapped_channels": int(mapped_channels),
                        "target_channels_per_market": int(target_channels_per_market),
                        "rejected_low_members": int(rejected_low_members),
                        "rejected_low_relevance": int(rejected_low_relevance),
                    },
                )
                self._log(
                    f"channel_discovery_market_skipped market_id={market_id} "
                    f"rejected_low_members={rejected_low_members} "
                    f"rejected_low_relevance={rejected_low_relevance}"
                )
                continue

            channels_written += self.repository.upsert_telegram_channels(selected, source="market_discovery")
            link_rows = []
            for index, channel in enumerate(selected, start=1):
                chat_id = int(channel["chat_id"])
                link_rows.append(
                    {
                        "chat_id": chat_id,
                        "market_id": market_id,
                        "link_source": candidate_source.get(chat_id, "auto"),
                        "priority_rank": index,
                        "notes": str(channel.get("discovery_relevance_reason") or ""),
                    }
                )
            links_written += self.repository.upsert_channel_market_links(link_rows)
            markets_updated += 1
            await self._emit_market_progress(
                market_progress_callback,
                {
                    "state": "market_complete",
                    "market_id": market_id,
                    "market_slug": str(market.get("slug") or ""),
                    "market_question": str(market.get("question") or ""),
                    "market_index": int(market_index),
                    "market_total": int(total_markets),
                    "mapped_channels_before": int(mapped_channels),
                    "mapped_channels_after": int(mapped_channels + len(selected)),
                    "selected_channels": int(len(selected)),
                    "rejected_low_members": int(rejected_low_members),
                    "rejected_low_relevance": int(rejected_low_relevance),
                },
            )
            self._log(
                f"channel_discovery_market market_id={market_id} selected={len(selected)} "
                f"rejected_low_members={rejected_low_members} "
                f"rejected_low_relevance={rejected_low_relevance} "
                f"mapped_before={mapped_channels} mapped_after={mapped_channels + len(selected)}"
            )

        return ChannelDiscoveryStats(
            markets_considered=len(markets),
            markets_updated=markets_updated,
            queries_sent=queries_sent,
            links_written=links_written,
            channels_written=channels_written,
            unique_channels_seen=len(seen_channel_ids),
            api_errors=api_errors,
        )

    @staticmethod
    async def _emit_market_progress(callback: Any, payload: dict[str, Any]) -> None:
        if callback is None:
            return
        result = callback(payload)
        if inspect.isawaitable(result):
            await result

    async def backtest_market(
        self,
        market: dict[str, Any],
        *,
        target_channels_per_market: int = 25,
        global_max_channels: int = 500,
        query_results_limit: int = 20,
        max_queries_per_market: int = 6,
        similar_per_seed: int = 10,
        similar_seed_channels: int = 3,
        min_channel_members: int = 1000,
        min_channel_relevance_score: float = 0.18,
        planner_system_prompt_override: str | None = None,
        planner_user_prompt_override: str | None = None,
        reviewer_system_prompt_override: str | None = None,
        reviewer_user_prompt_override: str | None = None,
        include_channel_ai_review: bool = False,
        max_review_channels: int = 20,
        review_message_limit: int = 10,
        use_relevance_scoring: bool = True,
    ) -> dict[str, Any]:
        plan = self.planner.build_query_plan(
            market,
            max_queries=max_queries_per_market,
            include_debug=True,
            system_prompt_override=planner_system_prompt_override,
            user_prompt_override=planner_user_prompt_override,
        )
        market_profile = build_market_channel_profile(market)
        language_hint = self._market_language_hint(market)
        accepted_candidates: dict[int, dict[str, Any]] = {}
        search_hits: list[dict[str, Any]] = []
        similar_hits: list[dict[str, Any]] = []
        api_errors: list[dict[str, Any]] = []
        rejected_counts = {
            "low_members": 0,
            "low_relevance": 0,
            "duplicate": 0,
            "global_cap": 0,
        }
        queries_sent = 0

        for query in list(plan["queries"]):
            try:
                query_run = await self._execute_discovery_query(query, limit=query_results_limit)
                queries_sent += 1
            except TDLibRequestError as exc:
                error_payload = {
                    "stage": "search",
                    "query": query,
                    "error": str(exc),
                }
                api_errors.append(error_payload)
                search_hits.append(
                    {
                        "query": query,
                        "status": "error",
                        "error": str(exc),
                        "results": [],
                    }
                )
                self._log(
                    f"channel_backtest_search_error market_id={market.get('market_id')} "
                    f"query={query!r} error={exc}"
                )
                continue

            stage_results = []
            for rank, channel in enumerate(list(query_run["channels"]), start=1):
                decision = self._build_backtest_channel_decision(
                    channel=channel,
                    source="search",
                    market_profile=market_profile,
                    min_channel_members=min_channel_members,
                    min_channel_relevance_score=min_channel_relevance_score,
                    use_relevance_scoring=use_relevance_scoring,
                    language_hint=language_hint,
                    accepted_candidates=accepted_candidates,
                    global_max_channels=global_max_channels,
                )
                decision["query_rank"] = rank
                stage_results.append(decision)
                self._register_backtest_decision(
                    decision=decision,
                    accepted_candidates=accepted_candidates,
                    rejected_counts=rejected_counts,
                )

            search_hits.append(
                {
                    "query": query_run["query"],
                    "query_type": query_run["query_type"],
                    "status": "ok",
                    "result_count": len(stage_results),
                    "accepted_count": sum(1 for item in stage_results if item["accepted"]),
                    "results": stage_results,
                }
            )

        ranked_seed_ids = [
            int(item["chat_id"])
            for item in self._rank_candidates(accepted_candidates.values())
        ]
        for seed_chat_id in ranked_seed_ids[:similar_seed_channels]:
            seed_channel = accepted_candidates.get(seed_chat_id) or {"chat_id": seed_chat_id}
            try:
                similar_channels = await self.tdlib_client.get_chat_similar_chats(seed_chat_id)
            except TDLibRequestError as exc:
                error_payload = {
                    "stage": "similar",
                    "seed_chat_id": seed_chat_id,
                    "error": str(exc),
                }
                api_errors.append(error_payload)
                similar_hits.append(
                    {
                        "seed_chat_id": seed_chat_id,
                        "seed_title": seed_channel.get("title"),
                        "status": "error",
                        "error": str(exc),
                        "results": [],
                    }
                )
                self._log(
                    f"channel_backtest_similar_error market_id={market.get('market_id')} "
                    f"seed_chat_id={seed_chat_id} error={exc}"
                )
                continue

            stage_results = []
            accepted_for_seed = 0
            for rank, channel in enumerate(similar_channels, start=1):
                decision = self._build_backtest_channel_decision(
                    channel=channel,
                    source="similar",
                    market_profile=market_profile,
                    min_channel_members=min_channel_members,
                    min_channel_relevance_score=min_channel_relevance_score,
                    use_relevance_scoring=use_relevance_scoring,
                    language_hint=language_hint,
                    accepted_candidates=accepted_candidates,
                    global_max_channels=global_max_channels,
                )
                decision["seed_chat_id"] = seed_chat_id
                decision["similar_rank"] = rank
                if decision["accepted"] and accepted_for_seed >= similar_per_seed:
                    decision["accepted"] = False
                    decision["decision_code"] = "rejected_seed_cap"
                    decision["decision_reason"] = f"seed cap {similar_per_seed} reached"
                if decision["accepted"]:
                    accepted_for_seed += 1
                stage_results.append(decision)
                self._register_backtest_decision(
                    decision=decision,
                    accepted_candidates=accepted_candidates,
                    rejected_counts=rejected_counts,
                )

            similar_hits.append(
                {
                    "seed_chat_id": seed_chat_id,
                    "seed_title": seed_channel.get("title"),
                    "status": "ok",
                    "result_count": len(stage_results),
                    "accepted_count": sum(1 for item in stage_results if item["accepted"]),
                    "results": stage_results,
                }
            )

        ranked_candidates = self._rank_candidates(accepted_candidates.values())
        selected_channels = ranked_candidates[:target_channels_per_market]

        channel_reviews: list[dict[str, Any]] = []
        if include_channel_ai_review and max_review_channels > 0:
            review_candidates = self._collect_backtest_review_candidates(
                search_hits=search_hits,
                similar_hits=similar_hits,
                max_review_channels=max_review_channels,
            )
            for index, candidate in enumerate(review_candidates, start=1):
                chat_id = int(candidate.get("chat_id") or 0)
                if chat_id <= 0:
                    continue
                recent_messages: list[dict[str, Any]] = []
                history_error = None
                try:
                    history_payload = await self.tdlib_client.get_chat_history(
                        chat_id,
                        max(1, min(int(review_message_limit), 20)),
                    )
                    recent_messages = list(history_payload.get("messages") or [])
                except TDLibRequestError as exc:
                    history_error = str(exc)
                    api_errors.append(
                        {
                            "stage": "channel_review_history",
                            "chat_id": chat_id,
                            "error": history_error,
                        }
                    )

                source_context = {
                    "source": str(candidate.get("source") or ""),
                    "source_query": str(candidate.get("source_query") or ""),
                    "source_seed_chat_id": candidate.get("source_seed_chat_id"),
                    "source_seed_title": str(candidate.get("source_seed_title") or ""),
                }
                review = self.channel_reviewer.review(
                    market=market,
                    channel=candidate,
                    source_context=source_context,
                    recent_messages=recent_messages,
                    system_prompt_override=reviewer_system_prompt_override,
                    user_prompt_override=reviewer_user_prompt_override,
                )
                channel_reviews.append(
                    {
                        "review_rank": index,
                        "chat_id": chat_id,
                        "title": str(candidate.get("title") or chat_id),
                        "username": candidate.get("username"),
                        "public_link": candidate.get("public_link"),
                        "member_count": candidate.get("member_count"),
                        "is_verified": bool(candidate.get("is_verified", False)),
                        "is_scam": bool(candidate.get("is_scam", False)),
                        "is_fake": bool(candidate.get("is_fake", False)),
                        "description": candidate.get("description"),
                        "source": source_context,
                        "history_error": history_error,
                        "recent_messages": recent_messages,
                        "review": review,
                    }
                )

            keep_reviews = [
                item
                for item in channel_reviews
                if str(item.get("review", {}).get("decision") or "").lower() == "keep"
                and bool(item.get("review", {}).get("is_relevant"))
                and _sort_member_count(item.get("member_count")) >= int(min_channel_members)
            ]
            keep_reviews = sorted(
                keep_reviews,
                key=lambda item: (_sort_member_count(item.get("member_count")), int(item.get("chat_id") or 0)),
                reverse=True,
            )
            selected_channels = [
                {
                    "chat_id": int(item.get("chat_id") or 0),
                    "title": str(item.get("title") or item.get("chat_id") or ""),
                    "username": item.get("username"),
                    "public_link": item.get("public_link"),
                    "member_count": item.get("member_count"),
                    "is_verified": bool(item.get("is_verified", False)),
                    "is_scam": bool(item.get("is_scam", False)),
                    "is_fake": bool(item.get("is_fake", False)),
                    "description": item.get("description"),
                    "discovery_relevance_score": None,
                    "discovery_relevance_label": "ai_decision",
                    "discovery_relevance_reason": str(item.get("review", {}).get("reason_short") or ""),
                    "selection_source": item.get("source"),
                }
                for item in keep_reviews[:target_channels_per_market]
            ]

        return {
            "market": {
                "market_id": str(market.get("market_id") or ""),
                "slug": str(market.get("slug") or ""),
                "question": str(market.get("question") or ""),
                "description": str(market.get("description") or ""),
                "rules_text": str(market.get("rules_text") or ""),
                "market_context": str(market.get("market_context") or ""),
                "market_archetype": str(market.get("market_archetype") or "unknown"),
                "classification": str(market.get("classification") or "unknown"),
                "local_score": market.get("analysis_local_score", market.get("local_score")),
                "mapped_channels": int(market.get("mapped_channels") or 0),
            },
            "planner": plan,
            "stages": {
                "search": search_hits,
                "similar": similar_hits,
                "channel_reviews": channel_reviews,
                "final": {
                    "selected_channels": selected_channels,
                    "accepted_candidates": len(accepted_candidates),
                    "target_channels": int(target_channels_per_market),
                },
            },
            "summary": {
                "target_channels": int(target_channels_per_market),
                "queries_sent": int(queries_sent),
                "raw_search_results": int(
                    sum(len(item["results"]) for item in search_hits if item.get("status") == "ok")
                ),
                "raw_similar_results": int(
                    sum(len(item["results"]) for item in similar_hits if item.get("status") == "ok")
                ),
                "accepted_candidates": int(len(accepted_candidates)),
                "selected_channels": int(len(selected_channels)),
                "reviewed_channels": int(len(channel_reviews)),
                "ai_kept_channels": int(
                    len(
                        [
                            item
                            for item in channel_reviews
                            if str(item.get("review", {}).get("decision") or "").lower() == "keep"
                            and bool(item.get("review", {}).get("is_relevant"))
                        ]
                    )
                ),
                "rejected_counts": rejected_counts,
                "api_errors": api_errors,
                "min_channel_members": int(min_channel_members),
                "min_channel_relevance_score": float(min_channel_relevance_score),
                "relevance_filter_enabled": bool(use_relevance_scoring),
                "global_max_channels": int(global_max_channels),
                "similar_seed_channels": int(similar_seed_channels),
                "similar_per_seed": int(similar_per_seed),
                "max_review_channels": int(max_review_channels),
                "review_message_limit": int(review_message_limit),
                "reviewer_runtime_mode": self.channel_reviewer.runtime_mode,
                "reviewer_prompt_version": self.channel_reviewer.prompt_version,
            },
        }

    def _collect_backtest_review_candidates(
        self,
        *,
        search_hits: list[dict[str, Any]],
        similar_hits: list[dict[str, Any]],
        max_review_channels: int,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen_chat_ids: set[int] = set()

        for search_stage in search_hits:
            query = str(search_stage.get("query") or "")
            for decision in list(search_stage.get("results") or []):
                if not bool(decision.get("accepted")):
                    continue
                channel = decision.get("channel") or {}
                chat_id = int(channel.get("chat_id") or 0)
                if chat_id <= 0 or chat_id in seen_chat_ids:
                    continue
                seen_chat_ids.add(chat_id)
                candidates.append(
                    {
                        **channel,
                        "source": "search",
                        "source_query": query,
                        "source_seed_chat_id": None,
                        "source_seed_title": "",
                    }
                )
                if len(candidates) >= max_review_channels:
                    return candidates

        for similar_stage in similar_hits:
            seed_chat_id = similar_stage.get("seed_chat_id")
            seed_title = str(similar_stage.get("seed_title") or "")
            for decision in list(similar_stage.get("results") or []):
                if not bool(decision.get("accepted")):
                    continue
                channel = decision.get("channel") or {}
                chat_id = int(channel.get("chat_id") or 0)
                if chat_id <= 0 or chat_id in seen_chat_ids:
                    continue
                seen_chat_ids.add(chat_id)
                candidates.append(
                    {
                        **channel,
                        "source": "similar",
                        "source_query": "",
                        "source_seed_chat_id": seed_chat_id,
                        "source_seed_title": seed_title,
                    }
                )
                if len(candidates) >= max_review_channels:
                    return candidates

        return candidates

    def _market_language_hint(self, market: dict[str, Any]) -> list[str]:
        reason_json = market.get("analysis_reason_json") or {}
        if not isinstance(reason_json, dict):
            return []
        raw_languages = reason_json.get("priority_languages") or []
        return [str(code) for code in raw_languages if str(code)]

    def _build_backtest_channel_decision(
        self,
        *,
        channel: dict[str, Any],
        source: str,
        market_profile: Any,
        min_channel_members: int,
        min_channel_relevance_score: float,
        use_relevance_scoring: bool,
        language_hint: list[str],
        accepted_candidates: dict[int, dict[str, Any]],
        global_max_channels: int,
    ) -> dict[str, Any]:
        chat_id = int(channel["chat_id"])
        member_count = _sort_member_count(channel.get("member_count"))
        relevance = None
        if use_relevance_scoring:
            relevance = evaluate_channel_relevance(
                channel,
                market_profile,
                min_score=min_channel_relevance_score,
            )

        decision_code = "accepted"
        decision_reason = "passed_member_and_dedupe_filters"
        accepted = True
        duplicate_of = None
        if chat_id in accepted_candidates:
            accepted = False
            decision_code = "duplicate"
            duplicate_of = chat_id
            decision_reason = "already accepted from earlier stage"
        elif chat_id not in accepted_candidates and len(accepted_candidates) >= global_max_channels:
            accepted = False
            decision_code = "rejected_global_cap"
            decision_reason = f"global cap {global_max_channels} reached"
        elif member_count < int(min_channel_members):
            accepted = False
            decision_code = "rejected_low_members"
            decision_reason = f"members {member_count} < floor {min_channel_members}"
        elif use_relevance_scoring and relevance is not None and not relevance.is_relevant:
            accepted = False
            decision_code = "rejected_low_relevance"
            decision_reason = relevance.reason

        return {
            "chat_id": chat_id,
            "title": str(channel.get("title") or chat_id),
            "username": channel.get("username"),
            "description": channel.get("description"),
            "member_count": channel.get("member_count"),
            "language_hint": list(language_hint),
            "accepted": accepted,
            "decision_code": decision_code,
            "decision_reason": decision_reason,
            "duplicate_of": duplicate_of,
            "source": source,
            "relevance_score": relevance.score if relevance is not None else None,
            "relevance_label": relevance.label if relevance is not None else "disabled",
            "relevance_reason": (
                relevance.reason
                if relevance is not None
                else "relevance_scoring_disabled_for_backtest"
            ),
            "matched_terms": list(relevance.matched_terms) if relevance is not None else [],
            "matched_entities": list(relevance.matched_entity_terms) if relevance is not None else [],
            "matched_phrases": list(relevance.matched_phrases) if relevance is not None else [],
            "matched_language_scripts": (
                list(relevance.matched_language_scripts) if relevance is not None else []
            ),
            "channel": {
                **channel,
                "language_hint": list(language_hint),
                "discovery_relevance_score": relevance.score if relevance is not None else None,
                "discovery_relevance_label": relevance.label if relevance is not None else "disabled",
                "discovery_relevance_reason": (
                    relevance.reason
                    if relevance is not None
                    else "relevance_scoring_disabled_for_backtest"
                ),
                "raw_json": {
                    **channel,
                    "discovery_relevance": {
                        "score": relevance.score if relevance is not None else None,
                        "label": relevance.label if relevance is not None else "disabled",
                        "reason": (
                            relevance.reason
                            if relevance is not None
                            else "relevance_scoring_disabled_for_backtest"
                        ),
                        "matched_terms": list(relevance.matched_terms) if relevance is not None else [],
                        "matched_entities": list(relevance.matched_entity_terms) if relevance is not None else [],
                        "matched_phrases": list(relevance.matched_phrases) if relevance is not None else [],
                    },
                },
            },
        }

    def _register_backtest_decision(
        self,
        *,
        decision: dict[str, Any],
        accepted_candidates: dict[int, dict[str, Any]],
        rejected_counts: dict[str, int],
    ) -> None:
        if decision["accepted"]:
            accepted_candidates[int(decision["chat_id"])] = dict(decision["channel"])
            return

        code = str(decision.get("decision_code") or "")
        if code == "rejected_low_members":
            rejected_counts["low_members"] += 1
        elif code == "rejected_low_relevance":
            rejected_counts["low_relevance"] += 1
        elif code == "duplicate":
            rejected_counts["duplicate"] += 1
        elif code == "rejected_global_cap":
            rejected_counts["global_cap"] += 1

    def _rank_candidates(self, channels: Any) -> list[dict[str, Any]]:
        return sorted(
            list(channels),
            key=lambda channel: (
                float(channel.get("discovery_relevance_score") or 0.0),
                _sort_member_count(channel.get("member_count")),
            ),
            reverse=True,
        )


class MarketTelegramListenerService:
    def __init__(
        self,
        repository: MarketIntelRepository,
        tdlib_client: TDLibDiscoveryClient,
        matcher: MarketMessageMatcher | None = None,
        log_fn: Callable[[str], None] | None = None,
    ):
        self.repository = repository
        self.tdlib_client = tdlib_client
        self.matcher = matcher or MarketMessageMatcher()
        self._log = log_fn or (lambda _: None)

    async def listen_once(
        self,
        *,
        channel_limit: int = 500,
        markets_per_channel: int = 25,
        history_limit: int = 10,
        concurrency: int = 8,
        max_new_messages: int = 3000,
    ) -> MessageListenerStats:
        bindings = self.repository.get_active_channel_market_bindings(
            channel_limit=channel_limit,
            markets_per_channel=markets_per_channel,
        )
        if not bindings:
            return MessageListenerStats(
                channels_polled=0,
                fetch_errors=0,
                new_messages=0,
                evaluated_pairs=0,
                matched_pairs=0,
                activations_inserted=0,
            )

        grouped = _group_channel_bindings(bindings)
        chat_ids = sorted(grouped.keys())
        last_message_ids = self.repository.get_channel_last_message_ids(chat_ids)

        fetch_results, fetch_errors = await self._fetch_histories(
            chat_ids=chat_ids,
            history_limit=history_limit,
            concurrency=concurrency,
        )
        unavailable_markers = (
            "chat not found",
            "not a public channel",
            "supergroup not found",
            "have no access",
            "chat info is inaccessible",
        )
        missing_chat_ids = sorted(
            {
                int(result["chat_id"])
                for result in fetch_results
                if result.get("history") is None
                and any(
                    marker in str(result.get("error") or "").lower()
                    for marker in unavailable_markers
                )
            }
        )
        if missing_chat_ids:
            deactivated = self.repository.mark_channels_inactive(
                missing_chat_ids,
                reason="tdlib_chat_not_found",
            )
            self._log(
                f"listener_auto_inactive missing_chat_ids={len(missing_chat_ids)} "
                f"channels_deactivated={deactivated} "
                f"sample_chat_ids={missing_chat_ids[:5]}"
            )

        message_rows: list[dict[str, Any]] = []
        match_rows: list[dict[str, Any]] = []
        activation_map: dict[str, dict[str, Any]] = {}
        new_messages = 0
        evaluated_pairs = 0
        matched_pairs = 0

        for result in fetch_results:
            chat_id = result["chat_id"]
            history = result["history"]
            if history is None:
                continue

            previous_max = int(last_message_ids.get(chat_id, 0))
            messages = list(history.get("messages") or [])
            messages.sort(key=lambda item: int(item.get("message_id") or 0))
            fresh_messages = [
                item for item in messages if int(item.get("message_id") or 0) > previous_max
            ]
            if not fresh_messages:
                continue

            for message in fresh_messages:
                if new_messages >= max_new_messages:
                    break
                message_text = str(message.get("text") or "").strip()
                # Text-only mode: skip media-only / empty payloads to keep writes lean.
                if not message_text:
                    continue
                new_messages += 1
                message_rows.append(
                    {
                        "chat_id": chat_id,
                        "message_id": int(message["message_id"]),
                        "posted_at": message.get("posted_at"),
                        "text": message_text,
                        "language": None,
                        "has_media": False,
                        "raw_json": message,
                    }
                )

                for market in grouped[chat_id]["markets"]:
                    evaluated_pairs += 1
                    profile = self.matcher.profile_for_market(market)
                    decision = self.matcher.evaluate(message_text, profile)
                    if decision.is_match:
                        matched_pairs += 1
                        activation_map.setdefault(
                            market["market_id"],
                            {
                                "market_id": market["market_id"],
                                "activation_time": message.get("posted_at") or _utc_now_iso(),
                                "trigger_chat_id": chat_id,
                                "trigger_message_id": int(message["message_id"]),
                                "trigger_match_id": None,
                                "activation_source": "telegram_match",
                                "notes": decision.reason_short,
                            },
                        )

                    match_rows.append(
                        {
                            "chat_id": chat_id,
                            "message_id": int(message["message_id"]),
                            "market_id": market["market_id"],
                            "is_match": decision.is_match,
                            "matched_outcome_index": None,
                            "match_reason_short": decision.reason_short,
                            "matcher_version": self.matcher.matcher_version,
                            "raw_json": {
                                "matched_terms": decision.matched_terms,
                                "matched_phrases": decision.matched_phrases,
                                "market_rank": market.get("market_rank"),
                            },
                        }
                    )

        if message_rows:
            self.repository.upsert_telegram_messages(message_rows)
        if match_rows:
            self.repository.upsert_message_market_matches(match_rows)
        activations_inserted = self.repository.insert_market_activations_if_absent(activation_map.values())

        return MessageListenerStats(
            channels_polled=len(chat_ids),
            fetch_errors=fetch_errors,
            new_messages=new_messages,
            evaluated_pairs=evaluated_pairs,
            matched_pairs=matched_pairs,
            activations_inserted=activations_inserted,
        )

    async def _fetch_histories(
        self,
        *,
        chat_ids: list[int],
        history_limit: int,
        concurrency: int,
    ) -> tuple[list[dict[str, Any]], int]:
        sem = asyncio.Semaphore(max(1, min(concurrency, 32)))
        fetch_errors = 0

        async def _fetch(chat_id: int) -> dict[str, Any]:
            nonlocal fetch_errors
            async with sem:
                try:
                    history = await self.tdlib_client.get_chat_history(chat_id, history_limit)
                    return {"chat_id": chat_id, "history": history, "error": ""}
                except TDLibRequestError as exc:
                    if _is_auth_key_duplicated(exc):
                        raise
                    fetch_errors += 1
                    self._log(f"listener_fetch_error chat_id={chat_id} error={exc}")
                    return {"chat_id": chat_id, "history": None, "error": str(exc)}

        results = await asyncio.gather(*[_fetch(chat_id) for chat_id in chat_ids])
        return list(results), fetch_errors


def _group_channel_bindings(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        chat_id = int(row["chat_id"])
        if chat_id not in grouped:
            grouped[chat_id] = {
                "channel_title": row.get("channel_title"),
                "channel_username": row.get("channel_username"),
                "markets": [],
            }
        grouped[chat_id]["markets"].append(
            {
                "market_id": str(row["market_id"]),
                "question": str(row.get("question") or ""),
                "rules_text": str(row.get("rules_text") or ""),
                "market_context": str(row.get("market_context") or ""),
                "market_archetype": str(row.get("market_archetype") or "unknown"),
                "market_rank": int(row.get("market_rank") or 0),
            }
        )
    return grouped


_QUERY_PREFIX_RE = re.compile(
    r"""^\s*(?:what\s+are\s+the\s+latest\s+updates\s+from|latest\s+updates\s+from|check|search\s+for(?:\s+news)?(?:\s+in\s+[^:]+)?\s*:|look\s+for(?:\s+[^:]+)?\s*:|gather\s+keywords\s*:|monitor\s+live\s+twitter\s+feeds\s+for|monitor|find|track)\s+""",
    flags=re.IGNORECASE,
)
_USELESS_QUERY_RE = re.compile(
    r"""^\s*(?:monitor(?:\s+live)?\s+twitter(?:\s+feeds)?(?:\s+for\s+immediate\s+updates)?|latest\s+updates)\s*[\.\?!]*\s*$""",
    flags=re.IGNORECASE,
)
_SITE_OPERATOR_RE = re.compile(r"""\bsite:[^\s]+\b""", flags=re.IGNORECASE)
_BOOLEAN_OPERATOR_RE = re.compile(r"""\b(?:and|or)\b""", flags=re.IGNORECASE)
_HANDLE_TOKEN_RE = re.compile(r"""(?<![\w/])@([A-Za-z0-9_]{5,32})\b""")
_HANDLE_ONLY_RE = re.compile(r"""^@([A-Za-z0-9_]{5,32})$""")


def _normalize_search_query_text(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    text = re.sub(r"""^\s*/search\b\s*""", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"""\b(?:from|to)\s*:\s*@([A-Za-z0-9_]{3,32})\b""",
        r"@\1",
        text,
        flags=re.IGNORECASE,
    )
    quoted = re.findall(r"[\"']([^\"']{3,120})[\"']", text)
    if quoted:
        longest = max((item.strip() for item in quoted if item.strip()), key=len, default="")
        if longest:
            text = longest
    text = _SITE_OPERATOR_RE.sub(" ", text)
    text = _BOOLEAN_OPERATOR_RE.sub(" ", text)
    text = re.sub(r"https?://\S+", " ", text, flags=re.IGNORECASE)
    text = _QUERY_PREFIX_RE.sub("", text)
    text = re.sub(r"^[\s:;,\-]+", "", text)
    text = re.sub(r"[\s\.\?!:;,\-]+$", "", text)
    text = " ".join(text.split()).strip()
    return text


def _is_useful_search_query(value: str) -> bool:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return False
    if len(text) < 3:
        return False
    if _USELESS_QUERY_RE.match(text):
        return False
    if not re.search(r"[@A-Za-z0-9\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u4e00-\u9fff]", text):
        return False
    return True


def _extract_primary_handle(value: str) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    match = _HANDLE_TOKEN_RE.search(text)
    if not match:
        return None
    return f"@{match.group(1)}"


def _strip_handle_tokens(value: str) -> str:
    text = _HANDLE_TOKEN_RE.sub(" ", str(value or ""))
    text = re.sub(r"""[\(\)\[\]\{\}|,:;]+""", " ", text)
    text = " ".join(text.split()).strip()
    return text


def _finalize_ai_planner_queries(
    *,
    raw_queries: list[str],
    candidate_queries: list[str],
    official_targets: list[dict[str, Any]],
    keyword_groups: list[dict[str, Any]],
    max_queries: int,
) -> list[str]:
    normalized_raw = [
        normalized
        for normalized in (_normalize_search_query_text(query) for query in list(raw_queries or []))
        if normalized and _is_useful_search_query(normalized)
    ]
    ordered: list[str] = _dedupe_keep_order(normalized_raw)

    if len(ordered) < max_queries:
        ordered.extend(
            item
            for item in candidate_queries
            if item not in ordered and _is_useful_search_query(item)
        )

    if len(ordered) < max_queries:
        for target in official_targets:
            handles = [str(handle).strip() for handle in list(target.get("handles") or []) if str(handle).strip()]
            label = str(target.get("label") or target.get("entity_label") or "").strip()
            merged = " ".join([*handles[:2], label]).strip()
            normalized = _normalize_search_query_text(merged)
            if normalized and _is_useful_search_query(normalized) and normalized not in ordered:
                ordered.append(normalized)
            if len(ordered) >= max_queries:
                break

    if len(ordered) < max_queries:
        for group in keyword_groups:
            terms = [str(term).strip() for term in list(group.get("query_terms") or []) if str(term).strip()]
            if not terms:
                continue
            merged = " ".join(terms[:3]).strip()
            normalized = _normalize_search_query_text(merged)
            if normalized and _is_useful_search_query(normalized) and normalized not in ordered:
                ordered.append(normalized)
            if len(ordered) >= max_queries:
                break

    return ordered[:max_queries]


def _build_google_discovery_queries(
    *,
    queries: list[str],
    candidate_queries: list[str],
    official_targets: list[dict[str, Any]],
    keyword_groups: list[dict[str, Any]],
    max_queries: int,
) -> list[str]:
    seeds: list[str] = []

    for target in official_targets:
        handles = [str(handle).strip() for handle in list(target.get("handles") or []) if str(handle).strip()]
        for handle in handles[:4]:
            normalized_handle = handle.lstrip("@").strip()
            if normalized_handle:
                seeds.append(f"site:t.me {normalized_handle}")
                seeds.append(f"site:t.me {normalized_handle} telegram")

    for query in list(queries or []):
        normalized = _normalize_search_query_text(query)
        if normalized:
            seeds.append(f"site:t.me {normalized}")

    for query in list(candidate_queries or []):
        normalized = _normalize_search_query_text(query)
        if normalized:
            seeds.append(f"site:t.me {normalized}")

    for group in keyword_groups:
        terms = [str(term).strip() for term in list(group.get("query_terms") or []) if str(term).strip()]
        if terms:
            seeds.append(f"site:t.me {' '.join(terms[:2])}")

    ordered: list[str] = []
    seen_lower: set[str] = set()
    for value in seeds:
        text = " ".join(str(value).split()).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen_lower:
            continue
        seen_lower.add(lowered)
        ordered.append(text)
        if len(ordered) >= max(1, int(max_queries)):
            break
    return ordered


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_'-]{1,}", text or "")]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _is_auth_key_duplicated(exc: Exception) -> bool:
    return "AUTH_KEY_DUPLICATED" in str(exc or "").upper()


def _sort_member_count(value: Any) -> int:
    if value is None:
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
