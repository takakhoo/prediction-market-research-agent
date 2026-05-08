from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


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
    "before",
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
    "markets",
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

_GENERIC_MARKET_TERMS = {
    "air",
    "attack",
    "attacks",
    "ballistic",
    "battle",
    "bomb",
    "bombing",
    "ceasefire",
    "conflict",
    "country",
    "daily",
    "deadline",
    "drone",
    "drones",
    "election",
    "enter",
    "forces",
    "ground",
    "leader",
    "launch",
    "launches",
    "major",
    "march",
    "military",
    "missile",
    "missiles",
    "offensive",
    "operation",
    "operations",
    "outcome",
    "regime",
    "rocket",
    "state",
    "strike",
    "strikes",
    "troops",
    "war",
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
    "middle_east": ("israel", "gaza", "lebanon", "iran", "tehran", "beirut"),
    "eastern_europe": ("ukraine", "russia", "moscow", "kyiv"),
    "latin_america": ("venezuela", "caracas", "maduro", "machado"),
}

_ENTITY_ALIASES = {
    "israel": ("israel", "israeli", "idf", "jerusalem"),
    "gaza": ("gaza", "gazan", "hamas"),
    "lebanon": ("lebanon", "lebanese", "beirut", "hezbollah"),
    "iran": ("iran", "iranian", "tehran", "irgc"),
    "ukraine": ("ukraine", "ukrainian", "kyiv", "kiev"),
    "russia": ("russia", "russian", "moscow", "kremlin"),
    "venezuela": ("venezuela", "venezuelan", "caracas", "maduro", "machado"),
    "us": ("us", "u.s", "usa", "american", "united", "states", "pentagon"),
    "nato": ("nato",),
}


@dataclass(frozen=True)
class MarketChannelProfile:
    market_id: str
    terms: tuple[str, ...]
    entity_terms: tuple[str, ...]
    phrases: tuple[str, ...]
    priority_languages: tuple[str, ...]


@dataclass(frozen=True)
class ChannelRelevanceDecision:
    score: float
    label: str
    is_relevant: bool
    matched_terms: tuple[str, ...]
    matched_entity_terms: tuple[str, ...]
    matched_phrases: tuple[str, ...]
    matched_language_scripts: tuple[str, ...]
    reason: str


def build_market_channel_profile(market: Mapping[str, Any]) -> MarketChannelProfile:
    question = str(market.get("question") or "")
    rules_text = str(market.get("rules_text") or "")
    market_context = str(market.get("market_context") or "")
    slug = str(market.get("slug") or "").replace("-", " ")
    combined = " ".join(part for part in (question, rules_text, market_context, slug) if part).lower()

    raw_tokens = _dedupe_keep_order(_tokenize(combined))
    terms = [
        token
        for token in raw_tokens
        if token not in _STOPWORDS and (len(token) >= 4 or token in _ENTITY_ALIASES)
    ]

    reason_json = market.get("analysis_reason_json") or {}
    priority_languages = ()
    region_terms: list[str] = []
    if isinstance(reason_json, dict):
        priority_languages = tuple(
            str(language).strip().lower()
            for language in (reason_json.get("priority_languages") or [])
            if str(language).strip()
        )
        for region in reason_json.get("priority_regions") or []:
            region_terms.extend(_REGION_HINT_QUERIES.get(str(region).strip().lower(), ()))

    entity_terms = [token for token in terms if token not in _GENERIC_MARKET_TERMS]
    entity_terms.extend(region_terms)

    expanded_entities: list[str] = []
    for token in entity_terms:
        expanded_entities.append(token)
        expanded_entities.extend(_ENTITY_ALIASES.get(token, ()))

    phrases = tuple(phrase for phrase in _PHRASE_TERMS if phrase in combined)
    return MarketChannelProfile(
        market_id=str(market.get("market_id") or ""),
        terms=tuple(_dedupe_keep_order(terms)[:48]),
        entity_terms=tuple(_dedupe_keep_order(expanded_entities)[:40]),
        phrases=phrases,
        priority_languages=priority_languages,
    )


def evaluate_channel_relevance(
    channel: Mapping[str, Any],
    market_or_profile: Mapping[str, Any] | MarketChannelProfile,
    *,
    min_score: float = 0.18,
) -> ChannelRelevanceDecision:
    profile = (
        market_or_profile
        if isinstance(market_or_profile, MarketChannelProfile)
        else build_market_channel_profile(market_or_profile)
    )

    text_parts = [
        str(channel.get("title") or ""),
        str(channel.get("username") or ""),
        str(channel.get("description") or ""),
        str(channel.get("notes") or ""),
    ]
    tags = channel.get("tags_json") or []
    if isinstance(tags, (list, tuple)):
        text_parts.extend(str(tag) for tag in tags if str(tag).strip())
    combined = " ".join(part for part in text_parts if part).lower()
    channel_tokens = set(_tokenize(combined))

    matched_terms = tuple(sorted(channel_tokens.intersection(profile.terms))[:10])
    matched_entity_terms = tuple(sorted(channel_tokens.intersection(profile.entity_terms))[:8])
    matched_phrases = tuple(phrase for phrase in profile.phrases if phrase in combined)
    matched_language_scripts = _detect_language_scripts(combined, profile.priority_languages)

    score = 0.0
    score += min(0.56, 0.24 * len(matched_entity_terms))
    score += min(0.22, 0.05 * len(matched_terms))
    score += min(0.16, 0.12 * len(matched_phrases))
    score += min(0.14, 0.08 * len(matched_language_scripts))

    if not matched_entity_terms and len(matched_terms) <= 1 and not matched_phrases:
        score -= 0.08
    if not combined.strip():
        score = 0.0

    score = round(max(0.0, min(score, 1.0)), 3)
    if score >= 0.5:
        label = "strong"
    elif score >= min_score:
        label = "candidate"
    else:
        label = "weak"

    reason_parts: list[str] = [f"score={score:.2f}"]
    if matched_entity_terms:
        reason_parts.append(f"entities={','.join(matched_entity_terms[:4])}")
    if matched_terms:
        reason_parts.append(f"terms={','.join(matched_terms[:4])}")
    if matched_phrases:
        reason_parts.append(f"phrases={','.join(matched_phrases[:2])}")
    if matched_language_scripts:
        reason_parts.append(f"scripts={','.join(matched_language_scripts)}")
    if len(reason_parts) == 1:
        reason_parts.append("generic_or_drift")

    return ChannelRelevanceDecision(
        score=score,
        label=label,
        is_relevant=score >= min_score,
        matched_terms=matched_terms,
        matched_entity_terms=matched_entity_terms,
        matched_phrases=matched_phrases,
        matched_language_scripts=matched_language_scripts,
        reason=" ".join(reason_parts),
    )


def _detect_language_scripts(text: str, priority_languages: tuple[str, ...]) -> tuple[str, ...]:
    hits: list[str] = []
    if any(language in {"ar", "arabic"} for language in priority_languages):
        if re.search(r"[\u0600-\u06FF]", text):
            hits.append("ar")
    if any(language in {"fa", "farsi", "persian"} for language in priority_languages):
        if re.search(r"[\u0600-\u06FF]", text):
            hits.append("fa")
    if any(language in {"he", "hebrew"} for language in priority_languages):
        if re.search(r"[\u0590-\u05FF]", text):
            hits.append("he")
    return tuple(_dedupe_keep_order(hits))


def _tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[^\W\d_][\w'-]{1,}", text or "", flags=re.UNICODE)
    ]


def _dedupe_keep_order(items: list[str] | tuple[str, ...]) -> list[str]:
    seen = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
