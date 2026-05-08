from __future__ import annotations

import asyncio

from src.polymarket.telegram_pipeline import (
    MarketMessageMatcher,
    MarketSearchPlanner,
    MarketTelegramDiscoveryService,
    MarketTelegramListenerService,
)
from src.discovery.errors import TDLibRequestError


class FakeDiscoveryRepo:
    def __init__(self):
        self.channels_rows = []
        self.link_rows = []

    def get_track_now_markets(self, *, limit: int = 100):
        return [
            {
                "market_id": "m1",
                "slug": "will-israel-strike-gaza",
                "question": "Will Israel strike Gaza by March 31?",
                "rules_text": "Resolves yes if Israel launches a missile or drone strike in Gaza.",
                "market_context": "",
                "market_archetype": "binary_oneoff",
                "mapped_channels": 0,
                "analysis_reason_json": {"priority_regions": ["middle_east"], "priority_languages": ["en", "ar"]},
            }
        ][:limit]

    def upsert_telegram_channels(self, channels, *, source: str):
        self.channels_rows = list(channels)
        return len(self.channels_rows)

    def upsert_channel_market_links(self, links):
        self.link_rows = list(links)
        return len(self.link_rows)


class FakeDiscoveryTdlib:
    async def search_public_chats(self, query: str, limit: int):
        if "israel" in query.lower():
            return [
                {"chat_id": 1001, "title": "IDF Official", "username": "idfofficial", "description": "Operational updates.", "member_count": 10000},
                {"chat_id": 1002, "title": "Gaza Strike Monitor", "username": "gazamonitor", "description": "Local updates from Gaza.", "member_count": 7000},
            ][:limit]
        return []

    async def search_public_chat(self, username: str):
        return None

    async def get_chat_similar_chats(self, chat_id: int):
        return [
            {"chat_id": 1003, "title": "Tehran Local Wire", "username": "tehranwire", "description": "Iran regional updates.", "member_count": 5000},
        ]


def test_discovery_service_links_channels_for_track_now_market():
    repo = FakeDiscoveryRepo()
    service = MarketTelegramDiscoveryService(
        repository=repo,
        tdlib_client=FakeDiscoveryTdlib(),
    )

    stats = asyncio.run(
        service.discover_once(
            market_limit=10,
            target_channels_per_market=2,
            global_max_channels=100,
            query_results_limit=10,
            max_queries_per_market=3,
            similar_per_seed=1,
            similar_seed_channels=1,
        )
    )

    assert stats.markets_considered == 1
    assert stats.markets_updated == 1
    assert stats.links_written == 2
    assert stats.channels_written == 2
    assert {row["market_id"] for row in repo.link_rows} == {"m1"}
    assert len({row["chat_id"] for row in repo.link_rows}) == 2


class FakeFilteredDiscoveryTdlib:
    async def search_public_chats(self, query: str, limit: int):
        if "israel" in query.lower():
            return [
                {
                    "chat_id": 2001,
                    "title": "Global Weather Desk",
                    "username": "weatherdesk",
                    "description": "Weather and traffic reports.",
                    "member_count": 50000,
                },
                {
                    "chat_id": 2002,
                    "title": "Israel Security Desk",
                    "username": "israelsecdesk",
                    "description": "Military updates from Israel.",
                    "member_count": 800,
                },
                {
                    "chat_id": 2003,
                    "title": "Gaza Strike Monitor",
                    "username": "gazamonitor",
                    "description": "Drone and missile alerts in Gaza.",
                    "member_count": 12000,
                },
            ][:limit]
        return []

    async def search_public_chat(self, username: str):
        return None

    async def get_chat_similar_chats(self, chat_id: int):
        return []


class FakeHandleDiscoveryTdlib:
    async def search_public_chats(self, query: str, limit: int):
        return []

    async def search_public_chat(self, username: str):
        handle = username.strip().lstrip("@").lower()
        if handle == "idfofficial":
            return {
                "chat_id": 3001,
                "title": "IDF Official",
                "username": "idfofficial",
                "description": "Official operational updates from the IDF.",
                "member_count": 250000,
            }
        return None

    async def get_chat_similar_chats(self, chat_id: int):
        return []


def test_execute_discovery_query_extracts_handle_from_mixed_query():
    service = MarketTelegramDiscoveryService(
        repository=FakeDiscoveryRepo(),
        tdlib_client=FakeHandleDiscoveryTdlib(),
    )

    payload = asyncio.run(
        service._execute_discovery_query("@idfofficial latest updates from israel", limit=5)
    )

    assert payload["query_type"] == "handle_plus_search"
    assert payload["result_count"] == 1
    assert payload["channels"][0]["chat_id"] == 3001


class FakePlannerReasoningClient:
    provider_name = "fake"

    def generate_json(self, **kwargs):
        return {
            "query_intent": "Find official and local channels for Israel and Iran in local and bridge languages.",
            "detected_entities": [
                {
                    "entity_key": "israel",
                    "label": "Israel",
                    "aliases_hit": ["israel", "idf"],
                    "local_languages": ["he", "ar"],
                    "bridge_languages": ["en"],
                    "search_languages": ["he", "ar", "en"],
                },
                {
                    "entity_key": "iran",
                    "label": "Iran",
                    "aliases_hit": ["iran", "tehran"],
                    "local_languages": ["fa"],
                    "bridge_languages": ["en", "ar"],
                    "search_languages": ["fa", "en", "ar"],
                },
            ],
            "priority_languages": ["en", "he", "ar", "fa"],
            "region_hints": ["middle_east"],
            "official_targets": [
                {
                    "entity_key": "israel",
                    "entity_label": "Israel",
                    "label": "IDF Official",
                    "type": "official_military",
                    "handles": ["@idfofficial", "@idf_telegram"],
                    "queries": ["idf official", "idf spokesperson"],
                }
            ],
            "keyword_groups": [
                {
                    "entity_key": "israel",
                    "entity_label": "Israel",
                    "language_code": "en",
                    "query_terms": ["israel", "idf", "israel military"],
                },
                {
                    "entity_key": "israel",
                    "entity_label": "Israel",
                    "language_code": "he",
                    "query_terms": ["ישראל", "צה״ל", "חדשות ישראל"],
                },
                {
                    "entity_key": "iran",
                    "entity_label": "Iran",
                    "language_code": "fa",
                    "query_terms": ["ایران", "سپاه", "تهران"],
                },
            ],
            "query_candidates": [
                "Will Israel strike Iran by March 31?",
                "@idfofficial",
                "@idf_telegram",
                "צה״ל",
                "سپاه",
            ],
            "queries": ["Will Israel strike Iran by March 31?", "@idfofficial", "צה״ל"],
        }


def test_market_search_planner_builds_multilingual_queries_and_official_targets():
    planner = MarketSearchPlanner(reasoning_client=FakePlannerReasoningClient())

    payload = planner.build_query_plan(
        {
            "market_id": "m1",
            "slug": "will-israel-strike-iran",
            "question": "Will Israel strike Iran by March 31?",
            "rules_text": "Resolves yes if Israel launches a missile or drone strike on Iranian soil.",
            "analysis_reason_json": {"priority_regions": ["middle_east"], "priority_languages": ["en", "ar"]},
        },
        max_queries=8,
    )

    assert planner.runtime_mode == "ai"
    assert payload["planner_version"] == "ai_query_planner_v1"
    assert payload["prompt_version"] == "telegram-query-planner-v3-ai"
    assert {item["entity_key"] for item in payload["detected_entities"]} >= {"israel", "iran"}
    assert set(payload["priority_languages"]) >= {"en", "ar", "he", "fa"}
    official_handles = {
        handle
        for target in payload["official_targets"]
        for handle in target.get("handles", [])
    }
    assert {"@idfofficial", "@idf_telegram"}.issubset(official_handles)
    keyword_languages = {group["language_code"] for group in payload["keyword_groups"]}
    assert {"he", "fa", "en"}.issubset(keyword_languages)
    assert any(query.startswith("@") for query in payload["queries"])


def test_discovery_service_filters_low_member_and_irrelevant_channels():
    repo = FakeDiscoveryRepo()
    service = MarketTelegramDiscoveryService(
        repository=repo,
        tdlib_client=FakeFilteredDiscoveryTdlib(),
    )

    stats = asyncio.run(
        service.discover_once(
            market_limit=10,
            target_channels_per_market=2,
            global_max_channels=100,
            query_results_limit=10,
            max_queries_per_market=3,
            similar_per_seed=0,
            similar_seed_channels=0,
            min_channel_members=1000,
            min_channel_relevance_score=0.18,
        )
    )

    assert stats.markets_updated == 1
    assert stats.links_written == 1
    assert stats.channels_written == 1
    assert [row["chat_id"] for row in repo.link_rows] == [2003]


def test_backtest_market_exposes_stepwise_search_and_final_selection():
    repo = FakeDiscoveryRepo()
    service = MarketTelegramDiscoveryService(
        repository=repo,
        tdlib_client=FakeFilteredDiscoveryTdlib(),
    )

    payload = asyncio.run(
        service.backtest_market(
            {
                "market_id": "m1",
                "slug": "will-israel-strike-gaza",
                "question": "Will Israel strike Gaza by March 31?",
                "rules_text": "Resolves yes if Israel launches a missile or drone strike in Gaza.",
                "market_context": "",
                "market_archetype": "binary_oneoff",
                "classification": "track_now",
                "mapped_channels": 0,
                "analysis_reason_json": {"priority_regions": ["middle_east"], "priority_languages": ["en", "ar"]},
            },
            target_channels_per_market=2,
            global_max_channels=100,
            query_results_limit=10,
            max_queries_per_market=3,
            similar_per_seed=0,
            similar_seed_channels=0,
            min_channel_members=1000,
            min_channel_relevance_score=0.18,
        )
    )

    assert payload["planner"]["planner_version"] == "heuristic_v2_multilingual"
    assert payload["planner"]["prompt_version"] == "telegram-query-planner-v2-multilingual"
    assert payload["summary"]["selected_channels"] == 1
    assert payload["stages"]["final"]["selected_channels"][0]["chat_id"] == 2003
    first_query = payload["stages"]["search"][0]
    assert first_query["status"] == "ok"
    assert first_query["query_type"] == "public_search"
    decisions = {item["chat_id"]: item for item in first_query["results"]}
    assert decisions[2001]["accepted"] is False
    assert decisions[2001]["decision_code"] == "rejected_low_relevance"
    assert decisions[2002]["accepted"] is False
    assert decisions[2002]["decision_code"] == "rejected_low_members"
    assert decisions[2003]["accepted"] is True


def test_backtest_market_uses_exact_handle_resolution_for_official_targets():
    repo = FakeDiscoveryRepo()
    service = MarketTelegramDiscoveryService(
        repository=repo,
        tdlib_client=FakeHandleDiscoveryTdlib(),
    )

    payload = asyncio.run(
        service.backtest_market(
            {
                "market_id": "m1",
                "slug": "will-israel-strike-iran",
                "question": "Will Israel strike Iran by March 31?",
                "rules_text": "Resolves yes if Israel launches a missile or drone strike on Iranian soil.",
                "market_context": "",
                "market_archetype": "binary_oneoff",
                "classification": "track_now",
                "mapped_channels": 0,
                "analysis_reason_json": {"priority_regions": ["middle_east"], "priority_languages": ["en", "ar"]},
            },
            target_channels_per_market=2,
            global_max_channels=100,
            query_results_limit=10,
            max_queries_per_market=3,
            similar_per_seed=0,
            similar_seed_channels=0,
            min_channel_members=1000,
            min_channel_relevance_score=0.18,
        )
    )

    search_stage = payload["stages"]["search"]
    assert search_stage[1]["query"] == "@idfofficial"
    assert search_stage[1]["query_type"] == "exact_handle"
    assert search_stage[1]["results"][0]["accepted"] is True
    assert payload["stages"]["final"]["selected_channels"][0]["chat_id"] == 3001


def test_matcher_returns_yes_no_without_confidence():
    matcher = MarketMessageMatcher()
    profile = matcher.profile_for_market(
        {
            "market_id": "m2",
            "question": "Will Israel launch a missile strike on Gaza?",
            "rules_text": "Resolves yes if a missile or drone strike impacts Gaza territory.",
            "market_context": "",
            "market_archetype": "binary_oneoff",
        }
    )

    yes_decision = matcher.evaluate("Reports of missile strike in Gaza now", profile)
    no_decision = matcher.evaluate("Weather update and traffic report", profile)

    assert yes_decision.is_match is True
    assert no_decision.is_match is False


class FakeListenerRepo:
    def __init__(self):
        self.saved_messages = []
        self.saved_matches = []
        self.saved_activations = []

    def get_active_channel_market_bindings(self, *, channel_limit: int = 500, markets_per_channel: int = 25):
        return [
            {
                "chat_id": 2001,
                "channel_title": "Source 1",
                "channel_username": "source_1",
                "trust_weight": 0.6,
                "market_id": "m3",
                "link_source": "auto_search",
                "priority_rank": 1,
                "question": "Will Israel strike Gaza?",
                "rules_text": "Drone or missile strike in Gaza",
                "market_context": "",
                "market_archetype": "binary_oneoff",
                "local_score": 0.8,
                "market_rank": 1,
            }
        ]

    def get_channel_last_message_ids(self, chat_ids):
        return {2001: 100}

    def upsert_telegram_messages(self, rows):
        self.saved_messages = list(rows)
        return len(self.saved_messages)

    def upsert_message_market_matches(self, rows):
        self.saved_matches = list(rows)
        return len(self.saved_matches)

    def insert_market_activations_if_absent(self, rows):
        self.saved_activations = list(rows)
        return len(self.saved_activations)


class FakeListenerTdlib:
    async def get_chat_history(self, chat_id: int, limit: int):
        return {
            "channel": {"chat_id": chat_id, "title": "Source 1", "username": "source_1"},
            "messages": [
                {
                    "chat_id": chat_id,
                    "message_id": 101,
                    "posted_at": "2026-03-06T12:00:00+00:00",
                    "text": "Local reports confirm missile strike in Gaza",
                    "url": "https://t.me/source_1/101",
                }
            ][:limit],
        }


class FakeListenerErrorRepo(FakeListenerRepo):
    def __init__(self):
        super().__init__()
        self.deactivated_chat_ids = []
        self.deactivate_reason = ""

    def mark_channels_inactive(self, chat_ids, *, reason: str):
        self.deactivated_chat_ids = sorted(int(item) for item in chat_ids)
        self.deactivate_reason = str(reason)
        return len(self.deactivated_chat_ids)


class FakeListenerErrorTdlib:
    async def get_chat_history(self, chat_id: int, limit: int):
        raise TDLibRequestError("get_chat failed: Chat not found")


def test_listener_service_persists_messages_and_matches():
    repo = FakeListenerRepo()
    service = MarketTelegramListenerService(
        repository=repo,
        tdlib_client=FakeListenerTdlib(),
    )

    stats = asyncio.run(
        service.listen_once(
            channel_limit=50,
            markets_per_channel=10,
            history_limit=5,
            concurrency=2,
            max_new_messages=100,
        )
    )

    assert stats.channels_polled == 1
    assert stats.fetch_errors == 0
    assert stats.new_messages == 1
    assert stats.evaluated_pairs == 1
    assert stats.matched_pairs == 1
    assert stats.activations_inserted == 1
    assert len(repo.saved_messages) == 1
    assert repo.saved_matches[0]["is_match"] is True


def test_listener_auto_inactivates_channels_on_chat_not_found():
    repo = FakeListenerErrorRepo()
    service = MarketTelegramListenerService(
        repository=repo,
        tdlib_client=FakeListenerErrorTdlib(),
    )

    stats = asyncio.run(
        service.listen_once(
            channel_limit=50,
            markets_per_channel=10,
            history_limit=5,
            concurrency=2,
            max_new_messages=100,
        )
    )

    assert stats.channels_polled == 1
    assert stats.fetch_errors == 1
    assert repo.deactivated_chat_ids == [2001]
    assert repo.deactivate_reason == "tdlib_chat_not_found"
