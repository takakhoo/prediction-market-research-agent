from __future__ import annotations

from src.polymarket.channel_relevance import build_market_channel_profile, evaluate_channel_relevance


def test_channel_relevance_accepts_entity_alias_match():
    market = {
        "market_id": "m1",
        "slug": "will-israel-strike-gaza",
        "question": "Will Israel strike Gaza by March 31?",
        "rules_text": "Resolves yes if Israel launches a missile or drone strike in Gaza.",
        "market_context": "",
        "analysis_reason_json": {"priority_regions": ["middle_east"], "priority_languages": ["en", "ar"]},
    }
    profile = build_market_channel_profile(market)

    decision = evaluate_channel_relevance(
        {
            "title": "IDF Official",
            "username": "idfofficial",
            "description": "Operational updates from the southern command.",
        },
        profile,
        min_score=0.18,
    )

    assert decision.is_relevant is True
    assert "idf" in decision.matched_entity_terms


def test_channel_relevance_rejects_generic_channel():
    market = {
        "market_id": "m2",
        "slug": "will-israel-strike-gaza",
        "question": "Will Israel strike Gaza by March 31?",
        "rules_text": "Resolves yes if Israel launches a missile or drone strike in Gaza.",
        "market_context": "",
        "analysis_reason_json": {"priority_regions": ["middle_east"], "priority_languages": ["en", "ar"]},
    }
    profile = build_market_channel_profile(market)

    decision = evaluate_channel_relevance(
        {
            "title": "Global Weather and Travel Desk",
            "username": "weatherdesk",
            "description": "Traffic, weather and culture updates.",
        },
        profile,
        min_score=0.18,
    )

    assert decision.is_relevant is False
    assert decision.label == "weak"
