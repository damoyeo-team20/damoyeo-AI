import asyncio

import pytest

from app.core.errors import AIServiceError
from app.graph.fairness import CandidateFairnessScore
from app.graph.nodes import n_candidate_ranker
from app.schemas.candidates import MeetingInput, ParticipantInput, ParticipantPreference
from app.schemas.preference import Sentiment, Strength


def _place(place_id: str, **overrides):
    place = {
        "search_plan_label": "저녁 식사",
        "search_plan_source": "MEETING_PURPOSE",
        "search_plan_rationale": "조용한 저녁 식사 목적에 맞는 계획",
        "kakao_place_id": place_id,
        "name": f"장소 {place_id}",
        "address": "서울 광진구 예시로 1",
        "category": "한식",
        "place_url": f"https://place.map.kakao.com/{place_id}",
        "latitude": 37.5401,
        "longitude": 127.0692,
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
        "participants": participants if participants is not None else _participants(),
        "place_candidates": places,
    }


def _evaluation(
    place_id: str,
    relation: str = "DIRECT",
    context_relation: str = "DIRECT",
    **overrides,
):
    value = {
        "kakao_place_id": place_id,
        "context_relation": context_relation,
        "preference_relations": [
            {
                "user_id": 1,
                "vocabulary_code": "SPICY_FOOD",
                "relation": relation,
            }
        ],
        "reasons": ["모임 목적에 맞는 장소예요."],
        "tags": [],
    }
    value.update(overrides)
    return value


def _run(monkeypatch, places, evaluations, participants=None):
    result = n_candidate_ranker._EvaluationResult.model_validate(
        {"evaluations": evaluations}
    )

    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return {"raw": None, "parsed": result, "parsing_error": None}

    class _LLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            return _StructuredLLM()

    monkeypatch.setattr(n_candidate_ranker, "get_llm", lambda: _LLM())

    return asyncio.run(
        n_candidate_ranker.rank_and_explain(
            _state(places, participants=participants)
        )
    )["ranked_candidates"]


def test_pre_ranker_uses_fairness_instead_of_model_output_order(monkeypatch):
    ranked = _run(
        monkeypatch,
        [_place("1"), _place("2")],
        [
            _evaluation("1", relation="NONE"),
            _evaluation("2", relation="DIRECT"),
        ],
    )

    assert [candidate["place"]["kakao_place_id"] for candidate in ranked] == [
        "2",
        "1",
    ]
    assert ranked[0]["fairness_score"] > ranked[1]["fairness_score"]


def test_context_none_is_removed_even_with_high_preference_fit(monkeypatch):
    ranked = _run(
        monkeypatch,
        [_place("1"), _place("2")],
        [
            _evaluation("1", relation="DIRECT", context_relation="NONE"),
            _evaluation("2", relation="NONE", context_relation="PARTIAL"),
        ],
    )

    assert [candidate["place"]["kakao_place_id"] for candidate in ranked] == ["2"]


def test_context_relation_is_only_a_tie_break_after_fairness(monkeypatch):
    ranked = _run(
        monkeypatch,
        [_place("1"), _place("2")],
        [
            _evaluation("2", relation="DIRECT", context_relation="PARTIAL"),
            _evaluation("1", relation="DIRECT", context_relation="DIRECT"),
        ],
    )

    assert [candidate["place"]["kakao_place_id"] for candidate in ranked] == [
        "1",
        "2",
    ]


def test_model_output_order_does_not_break_kakao_tie_break(monkeypatch):
    ranked = _run(
        monkeypatch,
        [_place("1"), _place("2")],
        [_evaluation("2"), _evaluation("1")],
    )

    assert [candidate["place"]["kakao_place_id"] for candidate in ranked] == [
        "1",
        "2",
    ]


def test_hallucinated_place_id_is_rejected(monkeypatch):
    with pytest.raises(AIServiceError) as exc_info:
        _run(monkeypatch, [_place("1")], [_evaluation("does-not-exist")])

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"


def test_missing_candidate_evaluation_is_rejected(monkeypatch):
    with pytest.raises(AIServiceError) as exc_info:
        _run(
            monkeypatch,
            [_place("1"), _place("2")],
            [_evaluation("1")],
        )

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"


def test_duplicate_candidate_evaluation_is_rejected(monkeypatch):
    with pytest.raises(AIServiceError) as exc_info:
        _run(
            monkeypatch,
            [_place("1")],
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
            [_place("1")],
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
            [_place("1")],
            [_evaluation("1", preference_relations=[])],
        )
    with pytest.raises(AIServiceError) as duplicate_exc:
        _run(
            monkeypatch,
            [_place("1")],
            [_evaluation("1", preference_relations=[duplicate, duplicate])],
        )

    assert missing_exc.value.code == "MODEL_RESPONSE_INVALID"
    assert duplicate_exc.value.code == "MODEL_RESPONSE_INVALID"


def test_ranking_key_uses_score_then_f_then_s_then_context_then_kakao_order():
    def score(total, minimum, group):
        return CandidateFairnessScore(
            participant_satisfaction={},
            group_satisfaction=group,
            minimum_satisfaction=minimum,
            score=total,
            vetoed=False,
            matched_preference_codes=(),
        )

    direct = n_candidate_ranker.ContextRelation.DIRECT
    partial = n_candidate_ranker.ContextRelation.PARTIAL

    assert n_candidate_ranker._ranking_key(score(80, 0.1, 0.9), partial, 5) < (
        n_candidate_ranker._ranking_key(score(79, 1.0, 1.0), direct, 0)
    )
    assert n_candidate_ranker._ranking_key(score(80, 0.7, 0.5), partial, 5) < (
        n_candidate_ranker._ranking_key(score(80, 0.6, 1.0), direct, 0)
    )
    assert n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), partial, 5) < (
        n_candidate_ranker._ranking_key(score(80, 0.7, 0.7), direct, 0)
    )
    assert n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), direct, 5) < (
        n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), partial, 0)
    )
    assert n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), direct, 0) < (
        n_candidate_ranker._ranking_key(score(80, 0.7, 0.8), direct, 1)
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

    ranked = _run(
        monkeypatch,
        [_place("1")],
        [_evaluation("1", preference_relations=[allergy_relation])],
        participants=participants,
    )

    assert ranked == []


def test_internal_llm_output_rejects_unknown_fields():
    with pytest.raises(ValueError):
        n_candidate_ranker._EvaluationResult.model_validate(
            {"evaluations": [], "unexpected": "must not be ignored"}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("context_relation", "MAYBE"), ("relation", "MAYBE")],
)
def test_internal_llm_output_rejects_unknown_enums(field, value):
    evaluation = _evaluation("1")
    if field == "context_relation":
        evaluation[field] = value
    else:
        evaluation["preference_relations"][0][field] = value

    with pytest.raises(ValueError):
        n_candidate_ranker._EvaluationResult.model_validate(
            {"evaluations": [evaluation]}
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
        asyncio.run(
            n_candidate_ranker.rank_and_explain(_state([_place("1")]))
        )

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"
    assert exc_info.value.status_code == 502


def test_empty_place_pool_skips_llm(monkeypatch):
    monkeypatch.setattr(
        n_candidate_ranker,
        "get_llm",
        lambda: pytest.fail("빈 후보 풀에서는 LLM을 호출하면 안 됩니다."),
    )

    assert asyncio.run(n_candidate_ranker.rank_and_explain(_state([]))) == {
        "ranked_candidates": []
    }


def test_large_candidate_pool_is_evaluated_in_batches_of_five(monkeypatch):
    expected_batches = [
        [str(index) for index in range(1, 6)],
        [str(index) for index in range(6, 11)],
        ["11", "12"],
    ]
    created_batches: list[list[str]] = []

    class _StructuredLLM:
        def __init__(self, place_ids):
            self.place_ids = place_ids

        async def ainvoke(self, _messages):
            parsed = n_candidate_ranker._EvaluationResult.model_validate(
                {
                    "evaluations": [
                        _evaluation(place_id, relation="DIRECT")
                        for place_id in self.place_ids
                    ]
                }
            )
            return {"raw": None, "parsed": parsed, "parsing_error": None}

    class _LLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            place_ids = expected_batches[len(created_batches)]
            created_batches.append(place_ids)
            return _StructuredLLM(place_ids)

    monkeypatch.setattr(n_candidate_ranker, "get_llm", lambda: _LLM())

    ranked = asyncio.run(
        n_candidate_ranker.rank_and_explain(
            _state([_place(str(index)) for index in range(1, 13)])
        )
    )["ranked_candidates"]

    assert created_batches == expected_batches
    assert [candidate["place"]["kakao_place_id"] for candidate in ranked] == [
        str(index) for index in range(1, 13)
    ]
