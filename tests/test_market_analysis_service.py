from __future__ import annotations

from src.polymarket.market_analysis import LocalMarketRuleClassifier, MarketAnalysisService


class FakeReasoningClient:
    provider_name = "fake"

    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, **kwargs):
        return self.payload


class FakeRepo:
    def __init__(self, pending_rows):
        self.pending_rows = list(pending_rows)
        self.requested_limit: int | None = None
        self.saved_rows = []

    def get_pending_market_analysis_rows(self, *, limit: int = 100):
        self.requested_limit = limit
        return list(self.pending_rows[:limit])

    def save_market_analysis_results(self, rows):
        self.saved_rows = list(rows)
        return len(self.saved_rows)


def _market(
    *,
    market_id: str,
    question: str,
    rules_text: str,
    outcomes: list[dict],
    market_archetype: str = "binary_oneoff",
    high_competition: bool = False,
    active: bool = True,
    closed: bool = False,
) -> dict:
    return {
        "market_id": market_id,
        "question": question,
        "description": "",
        "rules_text": rules_text,
        "market_context": "",
        "rules_hash": f"hash-{market_id}",
        "market_archetype": market_archetype,
        "high_competition": high_competition,
        "active": active,
        "closed": closed,
        "outcomes": outcomes,
    }


def test_local_classifier_tracks_geopolitical_binary_market():
    classifier = LocalMarketRuleClassifier()
    result = classifier.classify(
        _market(
            market_id="m1",
            question="Will Israel strike Gaza by March 31?",
            rules_text="Resolves Yes if Israeli military launches a missile or drone strike on Gaza.",
            outcomes=[
                {"outcome_index": 0, "outcome_label": "Yes", "probability": 0.81},
                {"outcome_index": 1, "outcome_label": "No", "probability": 0.19},
            ],
        )
    )

    assert result.classification == "track_now"
    assert result.is_local is True
    assert result.local_score >= 0.55
    assert "middle_east" in result.reason_json["priority_regions"]
    assert set(result.reason_json["priority_languages"]) >= {"en", "ar", "he", "fa"}
    flags = result.reason_json["price_flags"]
    assert flags[0]["flag"] == "likely"
    assert flags[1]["flag"] == "unlikely"


def test_local_classifier_ignores_closed_markets():
    classifier = LocalMarketRuleClassifier()
    result = classifier.classify(
        _market(
            market_id="m2",
            question="Will IDF strike X?",
            rules_text="Military strike condition",
            outcomes=[{"outcome_index": 0, "outcome_label": "Yes", "probability": 0.9}],
            active=False,
            closed=True,
        )
    )

    assert result.classification == "ignore"
    assert result.is_local is False
    assert result.local_score == 0.0


def test_market_analysis_service_analyzes_and_persists_rows():
    pending_rows = [
        _market(
            market_id="m3",
            question="Will Israel launch offensive in Lebanon?",
            rules_text="Ground offensive by Israel into Lebanon territory",
            outcomes=[
                {"outcome_index": 0, "outcome_label": "Yes", "probability": 0.78},
                {"outcome_index": 1, "outcome_label": "No", "probability": 0.22},
            ],
        ),
        _market(
            market_id="m4",
            question="Will Lakers win NBA finals?",
            rules_text="Sports market",
            outcomes=[
                {"outcome_index": 0, "outcome_label": "Yes", "probability": 0.55},
                {"outcome_index": 1, "outcome_label": "No", "probability": 0.45},
            ],
            high_competition=True,
        ),
    ]
    repo = FakeRepo(pending_rows)
    service = MarketAnalysisService(repository=repo, classifier=LocalMarketRuleClassifier())

    stats = service.analyze_pending(limit=25)

    assert repo.requested_limit == 25
    assert stats.pending_markets == 2
    assert stats.analyzed_markets == 2
    assert stats.track_now == 1
    assert stats.track_later == 1
    assert stats.ignored == 0
    assert stats.local_candidates == 1
    assert len(repo.saved_rows) == 2
    assert {row["market_id"] for row in repo.saved_rows} == {"m3", "m4"}


def test_local_classifier_uses_ai_reasoning_payload_when_client_is_present():
    classifier = LocalMarketRuleClassifier(
        reasoning_client=FakeReasoningClient(
            {
                "is_local": True,
                "local_score": 0.91,
                "classification": "track_now",
                "reason_json": {
                    "track_decision": "track_now",
                    "edge_hypothesis": "Strong local edge due to military and local-language reporting.",
                    "priority_languages": ["en", "he", "ar", "fa"],
                    "priority_regions": ["middle_east"],
                    "channel_profiles_needed": ["official_military", "local_journalists", "community_alerts"],
                    "competition_flag": {"high_competition": False, "reason": "volume_below_threshold"},
                    "price_flags": [
                        {"outcome_index": 0, "label": "Yes", "probability": 0.81, "flag": "likely"},
                        {"outcome_index": 1, "label": "No", "probability": 0.19, "flag": "unlikely"},
                    ],
                    "reason_short": "ai_track_now",
                    "reason_detailed": [
                        "Israel and Iran are both local-reporting-driven actors.",
                        "Official military and journalist channels are likely to matter.",
                    ],
                },
            }
        )
    )

    result = classifier.classify(
        _market(
            market_id="m5",
            question="Will Israel strike Iran by March 31?",
            rules_text="Resolves Yes if Israel launches a missile or drone strike on Iranian soil.",
            outcomes=[
                {"outcome_index": 0, "outcome_label": "Yes", "probability": 0.81},
                {"outcome_index": 1, "outcome_label": "No", "probability": 0.19},
            ],
        )
    )

    assert classifier.runtime_mode == "ai"
    assert result.classification == "track_now"
    assert result.local_score == 0.91
    assert result.reason_json["priority_regions"] == ["middle_east"]
