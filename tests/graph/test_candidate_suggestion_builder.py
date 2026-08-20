import asyncio
from datetime import UTC, datetime

from app.core.errors import AIServiceError
from app.graph.nodes import l_candidate_suggestion_builder
from app.schemas.candidates import ConfirmedSlot
from app.services.vocabulary_client import VocabularyEntry

_START = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
_END = datetime(2026, 8, 30, 11, 0, tzinfo=UTC)


def _place(place_id: str):
    return {
        "search_plan_label": "저녁 식사",
        "search_plan_source": "MEETING_PURPOSE",
        "search_plan_rationale": "모임 목적과 참여자 선호에 맞는 식사",
        "kakao_place_id": place_id,
        "name": f"장소 {place_id}",
        "address": "서울 광진구 예시로 1",
        "category": "한식",
        "place_url": f"https://place.map.kakao.com/{place_id}",
        "latitude": 37.5401,
        "longitude": 127.0692,
    }


def _ranked(place_id: str, **overrides):
    candidate = {
        "place": _place(place_id),
        "context_relation": "DIRECT",
        "participant_satisfaction": {1: 1.0},
        "group_satisfaction": 1.0,
        "minimum_satisfaction": 1.0,
        "fairness_score": 100.0,
        "matched_preference_codes": ["SPICY_FOOD"],
        "reasons": [f"장소 {place_id} 추천 이유"],
        "tags": ["MATCHES_ACTIVITY"],
        "original_index": int(place_id) - 1,
    }
    candidate.update(overrides)
    return candidate


def _verified(place_id: str, status: str, **overrides):
    place = {
        **_place(place_id),
        "verification_status": status,
        "business_hours": "매일 11:30~22:00" if status == "PASS" else None,
        "verification_source": "https://example.com/hours",
        "checked_at": datetime(2026, 8, 21, 3, 0, tzinfo=UTC),
    }
    place.update(overrides)
    return place


def _state(ranked_candidates, verified_places):
    return {
        "ranked_candidates": ranked_candidates,
        "verified_places": verified_places,
        "confirmed_slot": ConfirmedSlot(
            confirmed_start_at=_START,
            confirmed_end_at=_END,
        ),
    }


def _run(monkeypatch, ranked_candidates, verified_places):
    async def fake_fetch_vocabulary():
        return [
            VocabularyEntry(
                code="SPICY_FOOD",
                domain="FOOD",
                display_name="매운 음식",
                parent_code=None,
            )
        ]

    monkeypatch.setattr(
        l_candidate_suggestion_builder,
        "fetch_vocabulary",
        fake_fetch_vocabulary,
    )
    return asyncio.run(
        l_candidate_suggestion_builder.build_suggestions(
            _state(ranked_candidates, verified_places)
        )
    )["suggestions"]


def test_builder_uses_prerank_order_drops_fail_and_limits_to_three(monkeypatch):
    ranked = [_ranked(str(index)) for index in range(1, 6)]
    verified = [
        _verified("5", "PASS"),
        _verified("3", "UNKNOWN"),
        _verified("1", "FAIL"),
        _verified("4", "PASS"),
        _verified("2", "PASS"),
    ]

    suggestions = _run(monkeypatch, ranked, verified)

    assert [suggestion.external_place_id for suggestion in suggestions] == ["2", "3", "4"]
    assert [suggestion.rank for suggestion in suggestions] == [1, 2, 3]


def test_pass_adds_availability_fact_but_unknown_does_not(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_ranked("1"), _ranked("2")],
        [_verified("1", "PASS"), _verified("2", "UNKNOWN")],
    )

    passed, unknown = suggestions
    assert passed.business_hours_verified is True
    assert passed.open_at_meeting_time is True
    assert "AVAILABLE_AT_MEETING_TIME" in [tag.code for tag in passed.tags]
    assert passed.proposed_start_at == _START
    assert passed.proposed_end_at == _END

    assert unknown.business_hours_verified is False
    assert unknown.open_at_meeting_time is None
    assert "AVAILABLE_AT_MEETING_TIME" not in [tag.code for tag in unknown.tags]


def test_pass_without_business_hours_is_not_claimed_as_verified(monkeypatch):
    suggestion = _run(
        monkeypatch,
        [_ranked("1")],
        [_verified("1", "PASS", business_hours=None)],
    )[0]

    assert suggestion.business_hours_verified is False
    assert suggestion.open_at_meeting_time is None
    assert "AVAILABLE_AT_MEETING_TIME" not in [tag.code for tag in suggestion.tags]


def test_builder_maps_domains_and_deduplicates_source_urls(monkeypatch):
    ranked = [_ranked("1", matched_preference_codes=["SPICY_FOOD", "SPICY_FOOD"])]
    verified = [
        _verified(
            "1",
            "PASS",
            verification_source="https://place.map.kakao.com/1",
        )
    ]

    suggestion = _run(monkeypatch, ranked, verified)[0]

    assert suggestion.matched_preference_domains == ["FOOD"]
    assert suggestion.source_urls == ["https://place.map.kakao.com/1"]
    assert suggestion.reasons == ["장소 1 추천 이유"]


def test_missing_kakao_url_is_derived_from_trusted_place_id(monkeypatch):
    ranked = [_ranked("1")]
    ranked[0]["place"]["place_url"] = None
    verified = [_verified("1", "UNKNOWN", place_url=None, verification_source=None)]

    suggestion = _run(monkeypatch, ranked, verified)[0]

    assert suggestion.external_url == "https://place.map.kakao.com/1"
    assert suggestion.source_urls == ["https://place.map.kakao.com/1"]


def test_vocabulary_failure_keeps_suggestion_without_domains(monkeypatch):
    async def fail_fetch():
        raise AIServiceError(
            code="VOCABULARY_UNAVAILABLE",
            message="조회 실패",
            status_code=503,
            retryable=True,
        )

    monkeypatch.setattr(l_candidate_suggestion_builder, "fetch_vocabulary", fail_fetch)

    suggestions = asyncio.run(
        l_candidate_suggestion_builder.build_suggestions(
            _state([_ranked("1")], [_verified("1", "UNKNOWN")])
        )
    )["suggestions"]

    assert len(suggestions) == 1
    assert suggestions[0].matched_preference_domains == []


def test_unverified_ranked_candidate_is_not_returned(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_ranked("1"), _ranked("2")],
        [_verified("2", "PASS")],
    )

    assert [suggestion.external_place_id for suggestion in suggestions] == ["2"]


def test_all_failed_returns_empty_without_vocabulary_lookup(monkeypatch):
    async def must_not_fetch():
        raise AssertionError("빈 후보에서는 Vocabulary를 조회하면 안 됩니다.")

    monkeypatch.setattr(l_candidate_suggestion_builder, "fetch_vocabulary", must_not_fetch)

    result = asyncio.run(
        l_candidate_suggestion_builder.build_suggestions(
            _state([_ranked("1")], [_verified("1", "FAIL")])
        )
    )

    assert result == {"suggestions": []}
