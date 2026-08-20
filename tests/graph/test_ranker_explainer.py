import asyncio
from datetime import UTC, datetime

import pytest

from app.core.errors import AIServiceError
from app.graph.fairness import CandidateFairnessScore
from app.graph.nodes import n_candidate_ranker
from app.schemas.candidates import (
    ConfirmedSlot,
    MeetingInput,
    ParticipantInput,
    ParticipantPreference,
)
from app.schemas.preference import Sentiment, Strength
from app.services.vocabulary_client import VocabularyEntry

_START = datetime(2026, 8, 30, 18, 0, tzinfo=UTC)
_END = datetime(2026, 8, 30, 20, 0, tzinfo=UTC)


def _place(place_id: str, status: str, **overrides):
    place = {
        "activity": "저녁 식사",
        "kakao_place_id": place_id,
        "name": f"장소 {place_id}",
        "address": "서울 광진구 예시로 1",
        "category": "한식",
        "place_url": f"https://place.map.kakao.com/{place_id}",
        "latitude": 37.5401,
        "longitude": 127.0692,
        "verification_status": status,
        "business_hours": "매일 11:30~22:00",
        "verification_source": "https://example.com/hours",
        "checked_at": datetime(2026, 8, 20, 3, 11, tzinfo=UTC),
    }
    place.update(overrides)
    return place


def _participants():
    return [
        ParticipantInput(
            user_id=1,
            preferences=[
                ParticipantPreference(
                    vocabulary_code="SPICY_FOOD",
                    sentiment=Sentiment.POSITIVE,
                    strength=Strength.MODERATE,
                    raw_value="매운 음식",
                )
            ],
        )
    ]


def _state(places, participants=None):
    return {
        "meeting": MeetingInput.model_validate(
            {
                "id": 20,
                "purpose": "조용한 저녁 식사",
                "region": "건대",
            }
        ),
        "confirmed_slot": ConfirmedSlot(confirmed_start_at=_START, confirmed_end_at=_END),
        "participants": participants if participants is not None else _participants(),
        "activities": [
            {"activity": "저녁 식사", "search_queries": ["한식"], "rationale_group": "대화 중심"}
        ],
        "verified_places": places,
    }


def _evaluation(place_id: str, relation: str = "DIRECT", **overrides):
    value = {
        "kakao_place_id": place_id,
        "preference_relations": [
            {
                "user_id": 1,
                "vocabulary_code": "SPICY_FOOD",
                "relation": relation,
            }
        ],
        "reasons": ["대화하기 좋아요."],
        "tags": [],
    }
    value.update(overrides)
    return value


def _run(monkeypatch, places, evaluations, participants=None):
    result = n_candidate_ranker._EvaluationResult.model_validate({"evaluations": evaluations})

    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return {"raw": None, "parsed": result, "parsing_error": None}

    class _LLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            return _StructuredLLM()

    async def fake_fetch_vocabulary():
        return [
            VocabularyEntry(
                code="SPICY_FOOD",
                domain="FOOD",
                display_name="매운 음식",
                parent_code=None,
            )
        ]

    monkeypatch.setattr(n_candidate_ranker, "get_llm", lambda: _LLM())
    monkeypatch.setattr(n_candidate_ranker, "fetch_vocabulary", fake_fetch_vocabulary)

    return asyncio.run(
        n_candidate_ranker.rank_and_explain(_state(places, participants=participants))
    )["suggestions"]


def test_pass_place_gets_availability_tag_and_open_flag(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "PASS")],
        [_evaluation("1", tags=["MATCHES_ACTIVITY"])],
    )

    assert len(suggestions) == 1
    codes = [t.code for t in suggestions[0].tags]
    assert "MATCHES_ACTIVITY" in codes
    assert "AVAILABLE_AT_MEETING_TIME" in codes
    assert suggestions[0].open_at_meeting_time is True
    assert suggestions[0].business_hours_verified is True


def test_unknown_place_is_kept_but_not_claimed_open(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "UNKNOWN")],
        [_evaluation("1", relation="NONE", reasons=["분위기가 조용해요."])],
    )

    assert len(suggestions) == 1
    assert [t.code for t in suggestions[0].tags] == []
    assert suggestions[0].open_at_meeting_time is None
    assert suggestions[0].business_hours_verified is False


def test_failed_place_is_dropped_before_llm(monkeypatch):
    suggestions = _run(monkeypatch, [_place("1", "FAIL")], [])

    assert suggestions == []


def test_model_cannot_choose_final_order(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "PASS"), _place("2", "PASS")],
        [
            _evaluation("1", relation="NONE", reasons=["첫 입력 후보"]),
            _evaluation("2", relation="DIRECT", reasons=["선호 직접 일치"]),
        ],
    )

    assert [suggestion.external_place_id for suggestion in suggestions] == ["2", "1"]


def test_hallucinated_place_id_is_rejected(monkeypatch):
    with pytest.raises(AIServiceError) as exc_info:
        _run(
            monkeypatch,
            [_place("1", "PASS")],
            [_evaluation("does-not-exist")],
        )

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"


def test_missing_candidate_evaluation_is_rejected(monkeypatch):
    with pytest.raises(AIServiceError) as exc_info:
        _run(
            monkeypatch,
            [_place("1", "PASS"), _place("2", "PASS")],
            [_evaluation("1")],
        )

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"


def test_duplicate_candidate_evaluation_is_rejected(monkeypatch):
    with pytest.raises(AIServiceError) as exc_info:
        _run(
            monkeypatch,
            [_place("1", "PASS")],
            [_evaluation("1"), _evaluation("1")],
        )

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"


@pytest.mark.parametrize(
    "relation_override",
    [
        {"user_id": 999, "vocabulary_code": "SPICY_FOOD", "relation": "DIRECT"},
        {"user_id": 1, "vocabulary_code": "NOT_IN_REQUEST", "relation": "DIRECT"},
    ],
)
def test_unknown_participant_or_preference_is_rejected(monkeypatch, relation_override):
    with pytest.raises(AIServiceError) as exc_info:
        _run(
            monkeypatch,
            [_place("1", "PASS")],
            [_evaluation("1", preference_relations=[relation_override])],
        )

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"


def test_missing_or_duplicate_preference_relation_is_rejected(monkeypatch):
    duplicate = {
        "user_id": 1,
        "vocabulary_code": "SPICY_FOOD",
        "relation": "DIRECT",
    }
    with pytest.raises(AIServiceError) as missing_exc:
        _run(
            monkeypatch,
            [_place("1", "PASS")],
            [_evaluation("1", preference_relations=[])],
        )
    with pytest.raises(AIServiceError) as duplicate_exc:
        _run(
            monkeypatch,
            [_place("1", "PASS")],
            [_evaluation("1", preference_relations=[duplicate, duplicate])],
        )

    assert missing_exc.value.code == "MODEL_RESPONSE_INVALID"
    assert duplicate_exc.value.code == "MODEL_RESPONSE_INVALID"


def test_model_output_order_does_not_break_kakao_tie_break(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "PASS"), _place("2", "PASS")],
        [_evaluation("2", relation="NONE"), _evaluation("1", relation="NONE")],
    )

    assert [suggestion.external_place_id for suggestion in suggestions] == ["1", "2"]


def test_ranking_key_uses_score_then_f_then_s_then_kakao_order():
    def score(total, minimum, group):
        return CandidateFairnessScore(
            participant_satisfaction={},
            group_satisfaction=group,
            minimum_satisfaction=minimum,
            score=total,
            vetoed=False,
            matched_preference_codes=(),
        )

    assert n_candidate_ranker._ranking_key(score(80, 0.1, 0.9), 5) < (
        n_candidate_ranker._ranking_key(score(79, 1.0, 1.0), 0)
    )
    assert n_candidate_ranker._ranking_key(score(80, 0.7, 0.5), 5) < (
        n_candidate_ranker._ranking_key(score(80, 0.6, 1.0), 0)
    )
    assert n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), 5) < (
        n_candidate_ranker._ranking_key(score(80, 0.7, 0.7), 0)
    )
    assert n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), 0) < (
        n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), 1)
    )


def test_direct_allergy_conflict_is_removed(monkeypatch):
    participants = [
        ParticipantInput.model_validate(
            {
                "userId": 7,
                "preferences": [
                    {
                        "vocabularyCode": "SHELLFISH_ALLERGY",
                        "sentiment": "NEGATIVE",
                        "strength": "STRONG",
                        "rawValue": "갑각류 알레르기",
                    }
                ],
            }
        )
    ]
    allergy_relation = {
        "user_id": 7,
        "vocabulary_code": "SHELLFISH_ALLERGY",
        "relation": "DIRECT",
    }

    suggestions = _run(
        monkeypatch,
        [_place("1", "PASS")],
        [_evaluation("1", preference_relations=[allergy_relation])],
        participants=participants,
    )

    assert suggestions == []


def test_internal_llm_output_rejects_unknown_fields():
    with pytest.raises(ValueError):
        n_candidate_ranker._EvaluationResult.model_validate(
            {
                "evaluations": [],
                "unexpected": "must not be ignored",
            }
        )


def test_internal_llm_output_rejects_unknown_relation():
    with pytest.raises(ValueError):
        n_candidate_ranker._EvaluationResult.model_validate(
            {
                "evaluations": [
                    _evaluation("1", relation="MAYBE")
                ]
            }
        )


def test_structured_output_parse_error_becomes_model_response_invalid(monkeypatch):
    parsing_error = ValueError("invalid structured output")

    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return {"raw": None, "parsed": None, "parsing_error": parsing_error}

    class _LLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            return _StructuredLLM()

    monkeypatch.setattr(n_candidate_ranker, "get_llm", lambda: _LLM())

    with pytest.raises(AIServiceError) as exc_info:
        asyncio.run(n_candidate_ranker.rank_and_explain(_state([_place("1", "PASS")])))

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"
    assert exc_info.value.status_code == 502


def test_matched_domain_is_derived_from_valid_positive_relation(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "PASS")],
        [_evaluation("1", relation="DIRECT")],
    )

    assert suggestions[0].matched_preference_domains == ["FOOD"]


def test_rank_is_sequential_and_limited_to_three(monkeypatch):
    places = [_place(str(i), "PASS") for i in range(1, 5)]
    evaluations = [_evaluation(str(i), relation="NONE") for i in range(1, 5)]

    suggestions = _run(monkeypatch, places, evaluations)

    assert [suggestion.rank for suggestion in suggestions] == [1, 2, 3]
    assert [suggestion.external_place_id for suggestion in suggestions] == ["1", "2", "3"]
