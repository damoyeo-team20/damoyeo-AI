"""Candidate Context/Fairness Pre-Ranker & Explainer.

Kakao에서 넓게 모은 모든 후보에 대해 LLM은 모임 목적 적합도와 참여자별 선호의 의미 관계,
후보별 설명만 구조화해 반환한다. LLM이 후보 순서나 공정성 숫자를 정하지 않는다.

서버는 모임 목적과 관련 없는 후보와 알레르기 충돌 후보를 먼저 제외하고, 개인 만족도 ``u_i(c)``,
평균 ``S(c)``, 최저 ``F(c)``, ``100 * (0.7*S + 0.3*F)``를 계산해 영업 검증 순서를 고정한다.
"""

import asyncio
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import AIServiceError
from app.core.llm import get_llm
from app.graph.fairness import (
    CandidateFairnessScore,
    PreferenceRelation,
    calculate_candidate_fairness,
)
from app.graph.candidates_state import CandidatesState, PlaceCandidate, RankedCandidate
from app.prompts.n_candidate_ranker import SYSTEM_PROMPT
from app.schemas.candidates import CandidateTag, ParticipantInput

_EVALUATION_BATCH_SIZE = 5


class ContextRelation(str, Enum):
    """후보가 이번 모임의 명시적 목적에 얼마나 부합하는지 나타내는 제한된 판정."""

    DIRECT = "DIRECT"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


_CONTEXT_TIE_BREAK: dict[ContextRelation, int] = {
    ContextRelation.DIRECT: 0,
    ContextRelation.PARTIAL: 1,
    ContextRelation.NONE: 2,
}

# AVAILABLE_AT_MEETING_TIME은 영업 검증 결과에서 파생되는 사실이므로 LLM 선택지에서 제외한다.
_LLM_SELECTABLE_TAGS = [
    tag for tag in CandidateTag if tag is not CandidateTag.AVAILABLE_AT_MEETING_TIME
]
_LLMCandidateTag = Literal[tuple(tag.value for tag in _LLM_SELECTABLE_TAGS)]  # type: ignore[valid-type]


class _PreferenceEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    vocabulary_code: str
    relation: PreferenceRelation


class _CandidateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kakao_place_id: str
    context_relation: ContextRelation
    preference_relations: list[_PreferenceEvaluation] = Field(default_factory=list)
    reasons: list[str] = Field(min_length=1, max_length=3)
    # AVAILABLE_AT_MEETING_TIME은 여기에 없다. 영업 검증 PASS일 때 서버가 붙인다.
    tags: list[_LLMCandidateTag] = Field(default_factory=list)


class _EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[_CandidateEvaluation] = Field(default_factory=list)


def _ranking_key(
    fairness: CandidateFairnessScore,
    context_relation: ContextRelation,
    original_index: int,
) -> tuple[float, float, float, int, int]:
    """높은 Score → F → S → 컨텍스트 직접성 → 원래 Kakao 순서를 우선한다."""

    return (
        -fairness.score,
        -fairness.minimum_satisfaction,
        -fairness.group_satisfaction,
        _CONTEXT_TIE_BREAK[context_relation],
        original_index,
    )


def _invalid_model_result(message: str) -> AIServiceError:
    return AIServiceError(
        code="MODEL_RESPONSE_INVALID",
        message=message,
        status_code=502,
        retryable=True,
    )


def _validate_evaluations(
    result: _EvaluationResult,
    places: list[PlaceCandidate],
    participants: list[ParticipantInput],
) -> dict[str, tuple[_CandidateEvaluation, dict[tuple[int, str], PreferenceRelation]]]:
    """모델이 입력 후보·참여자·선호를 빠짐없이 그대로 참조했는지 검증한다."""

    expected_place_ids = {place["kakao_place_id"] for place in places}
    expected_relation_keys = {
        (participant.user_id, preference.vocabulary_code)
        for participant in participants
        for preference in participant.preferences
    }

    validated: dict[
        str, tuple[_CandidateEvaluation, dict[tuple[int, str], PreferenceRelation]]
    ] = {}
    for evaluation in result.evaluations:
        place_id = evaluation.kakao_place_id
        if place_id not in expected_place_ids or place_id in validated:
            raise _invalid_model_result("모델이 입력에 없거나 중복된 장소 ID를 반환했습니다.")

        relations: dict[tuple[int, str], PreferenceRelation] = {}
        for item in evaluation.preference_relations:
            key = (item.user_id, item.vocabulary_code)
            if key not in expected_relation_keys or key in relations:
                raise _invalid_model_result(
                    "모델이 입력에 없거나 중복된 참여자 선호를 반환했습니다."
                )
            relations[key] = item.relation

        if set(relations) != expected_relation_keys:
            raise _invalid_model_result("모델이 일부 참여자 선호 평가를 누락했습니다.")
        validated[place_id] = (evaluation, relations)

    if set(validated) != expected_place_ids:
        raise _invalid_model_result("모델이 일부 장소 후보 평가를 누락했습니다.")
    return validated


async def _evaluate_candidate_batch(
    *,
    purpose: str,
    participants: list[ParticipantInput],
    places: list[PlaceCandidate],
) -> _EvaluationResult:
    """구조화 출력 크기를 제한하기 위해 후보를 최대 5개씩 독립 평가한다."""

    llm = get_llm().with_structured_output(_EvaluationResult, include_raw=True)
    system = SYSTEM_PROMPT.format(
        purpose=purpose,
        participants=[
            participant.model_dump(by_alias=True) for participant in participants
        ],
        place_candidates=[
            {
                "kakaoPlaceId": place["kakao_place_id"],
                "searchPlan": place["search_plan_label"],
                "searchPlanSource": place["search_plan_source"],
                "searchPlanRationale": place["search_plan_rationale"],
                "name": place["name"],
                "category": place["category"],
            }
            for place in places
        ],
    )
    try:
        structured_result = await llm.ainvoke(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": "이 batch의 모든 후보에 대해 모임 목적 적합도와 참여자별 선호 관계를 평가해줘.",
                },
            ]
        )
    except ValidationError as exc:
        raise _invalid_model_result("모델 구조화 응답 검증에 실패했습니다.") from exc

    if not isinstance(structured_result, dict):
        raise _invalid_model_result("모델 구조화 응답 검증에 실패했습니다.")

    parsing_error = structured_result.get("parsing_error")
    result = structured_result.get("parsed")
    if parsing_error is not None or not isinstance(result, _EvaluationResult):
        error = _invalid_model_result("모델 구조화 응답 검증에 실패했습니다.")
        if isinstance(parsing_error, BaseException):
            raise error from parsing_error
        raise error

    # batch마다 먼저 완전성을 확인해 한 batch의 누락이 전체 merge 뒤에 가려지지 않게 한다.
    _validate_evaluations(result, places, participants)
    return result


async def rank_and_explain(state: CandidatesState) -> dict:
    """모든 Kakao 후보를 평가해 영업 검증 우선순서와 표현 정보를 만든다."""

    places = state.get("place_candidates", [])
    if not places:
        return {"ranked_candidates": []}

    participants = state.get("participants", [])
    if not participants:
        raise _invalid_model_result("공정성 계산에 필요한 참여자 정보가 없습니다.")

    batches = [
        places[index : index + _EVALUATION_BATCH_SIZE]
        for index in range(0, len(places), _EVALUATION_BATCH_SIZE)
    ]
    batch_results = await asyncio.gather(
        *(
            _evaluate_candidate_batch(
                purpose=state["meeting"].purpose,
                participants=participants,
                places=batch,
            )
            for batch in batches
        )
    )
    result = _EvaluationResult(
        evaluations=[
            evaluation
            for batch_result in batch_results
            for evaluation in batch_result.evaluations
        ]
    )

    validated = _validate_evaluations(result, places, participants)

    scored: list[
        tuple[
            CandidateFairnessScore,
            ContextRelation,
            int,
            PlaceCandidate,
            _CandidateEvaluation,
        ]
    ] = []
    for original_index, place in enumerate(places):
        evaluation, relations = validated[place["kakao_place_id"]]
        if evaluation.context_relation is ContextRelation.NONE:
            continue
        fairness = calculate_candidate_fairness(
            participants,
            relations,
            candidate_id=place["kakao_place_id"],
        )
        if fairness.vetoed:
            continue
        scored.append(
            (fairness, evaluation.context_relation, original_index, place, evaluation)
        )

    scored.sort(key=lambda item: _ranking_key(item[0], item[1], item[2]))
    ranked_candidates: list[RankedCandidate] = [
        {
            "place": place,
            "context_relation": context_relation.value,
            "participant_satisfaction": fairness.participant_satisfaction,
            "group_satisfaction": fairness.group_satisfaction,
            "minimum_satisfaction": fairness.minimum_satisfaction,
            "fairness_score": fairness.score,
            "matched_preference_codes": list(fairness.matched_preference_codes),
            "reasons": evaluation.reasons,
            "tags": list(evaluation.tags),
            "original_index": original_index,
        }
        for fairness, context_relation, original_index, place, evaluation in scored
    ]

    return {"ranked_candidates": ranked_candidates}
