"""Candidate Fairness Ranker & Explainer.

검증을 통과한(또는 UNKNOWN인) 모든 후보에 대해 LLM은 장소와 참여자별 선호의 의미 관계 및
후보별 설명만 구조화해 반환한다. LLM이 후보 순서나 공정성 숫자를 정하지 않는다.

서버 코드는 의미 관계에서 개인 만족도 ``u_i(c)``를 계산하고, 평균 만족도 ``S(c)``와 최저
만족도 ``F(c)``를 ``100 * (0.7*S + 0.3*F)``로 집계해 최대 3개 순서를 고정한다.

사실 판정에 해당하는 값도 코드가 붙인다:
  - AVAILABLE_AT_MEETING_TIME 태그와 openAtMeetingTime: Place Verifier 결과에서 파생
  - matchedPreferenceDomains: 실제로 기여한 입력 Vocabulary code를 domain으로 변환
  - proposedStartAt/EndAt: 요청의 confirmedSlot을 그대로 사용
"""

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.debug import record_debug  # TEMP DEBUG
from app.core.errors import AIServiceError
from app.core.llm import get_llm
from app.graph.fairness import (
    CandidateFairnessScore,
    PreferenceRelation,
    calculate_candidate_fairness,
)
from app.graph.state import CandidatesState, VerifiedPlace
from app.prompts.n_candidate_ranker import SYSTEM_PROMPT
from app.schemas.candidates import (
    CandidateTag,
    ParticipantInput,
    PlaceProvider,
    Suggestion,
    to_candidate_tag,
)
from app.services.vocabulary_client import fetch_vocabulary

logger = logging.getLogger(__name__)

_MAX_SUGGESTIONS = 3

_PASS = "PASS"
_FAIL = "FAIL"

# AVAILABLE_AT_MEETING_TIME은 영업 검증 결과에서 파생되는 사실이므로 LLM 선택지에서 제외한다.
_LLM_SELECTABLE_TAGS = [
    t for t in CandidateTag if t is not CandidateTag.AVAILABLE_AT_MEETING_TIME
]
_LLMCandidateTag = Literal[tuple(t.value for t in _LLM_SELECTABLE_TAGS)]  # type: ignore[valid-type]


class _PreferenceEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    vocabulary_code: str
    relation: PreferenceRelation


class _CandidateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kakao_place_id: str
    preference_relations: list[_PreferenceEvaluation] = Field(default_factory=list)
    reasons: list[str] = Field(min_length=1, max_length=3)
    # AVAILABLE_AT_MEETING_TIME은 여기에 없다. 영업 검증 PASS일 때 서버가 붙인다.
    tags: list[_LLMCandidateTag] = Field(default_factory=list)


class _EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[_CandidateEvaluation] = Field(default_factory=list)


def _eligible(places: list[VerifiedPlace]) -> list[VerifiedPlace]:
    return [p for p in places if p["verification_status"] != _FAIL]


def _ranking_key(
    fairness: CandidateFairnessScore,
    original_index: int,
) -> tuple[float, float, float, int]:
    """높은 Score → F → S, 마지막으로 빠른 Kakao 입력 순서를 우선한다."""

    return (
        -fairness.score,
        -fairness.minimum_satisfaction,
        -fairness.group_satisfaction,
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
    places: list[VerifiedPlace],
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


async def _domains_by_code(codes: set[str]) -> dict[str, str]:
    """Vocabulary 조회 실패로 후보 생성 전체를 실패시키지 않는다. domain만 비워서 진행한다."""

    if not codes:
        return {}
    try:
        vocabulary = await fetch_vocabulary()
    except AIServiceError:
        logger.warning("랭킹 중 Vocabulary 조회 실패 — matchedPreferenceDomains 없이 진행")
        return {}
    return {entry.code: entry.domain for entry in vocabulary if entry.code in codes}


async def rank_and_explain(state: CandidatesState) -> dict:
    eligible = _eligible(state.get("verified_places", []))
    if not eligible:
        return {"suggestions": []}

    participants = state.get("participants", [])
    if not participants:
        raise _invalid_model_result("공정성 계산에 필요한 참여자 정보가 없습니다.")

    # Activity Decider가 활동 유형별로 남긴 집단 수준 사유를 참고 맥락으로 함께 전달한다.
    activity_rationales = {a["activity"]: a["rationale_group"] for a in state.get("activities", [])}

    llm = get_llm().with_structured_output(_EvaluationResult, include_raw=True)
    system = SYSTEM_PROMPT.format(
        purpose=state["meeting"].purpose,
        participants=[p.model_dump(by_alias=True) for p in participants],
        verified_places=[
            {
                "kakaoPlaceId": p["kakao_place_id"],
                "activity": p["activity"],
                "activityRationale": activity_rationales.get(p["activity"]),
                "name": p["name"],
                "category": p["category"],
                "verificationStatus": p["verification_status"],
            }
            for p in eligible
        ],
    )
    try:
        structured_result = await llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "모든 후보와 참여자별 선호 관계를 평가해줘."},
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

    validated = _validate_evaluations(result, eligible, participants)

    scored: list[
        tuple[CandidateFairnessScore, int, VerifiedPlace, _CandidateEvaluation]
    ] = []
    for original_index, place in enumerate(eligible):
        evaluation, relations = validated[place["kakao_place_id"]]
        fairness = calculate_candidate_fairness(participants, relations)
        if not fairness.vetoed:
            scored.append((fairness, original_index, place, evaluation))

    # 같은 최종 점수에서는 최저 만족도, 평균 만족도, Kakao 원래 순서를 차례로 본다.
    scored.sort(key=lambda item: _ranking_key(item[0], item[1]))
    selected = scored[:_MAX_SUGGESTIONS]

    matched_codes = {
        code for fairness, _, _, _ in selected for code in fairness.matched_preference_codes
    }
    domain_by_code = await _domains_by_code(matched_codes)

    record_debug(  # TEMP DEBUG
        "n_candidate_ranker",
        {
            "evaluation": result.model_dump(),
            "scores": [
                {
                    "kakaoPlaceId": place["kakao_place_id"],
                    "participantSatisfaction": fairness.participant_satisfaction,
                    "S": fairness.group_satisfaction,
                    "F": fairness.minimum_satisfaction,
                    "score": fairness.score,
                }
                for fairness, _, place, _ in selected
            ],
        },
    )

    confirmed_slot = state["confirmed_slot"]
    start_at = confirmed_slot.confirmed_start_at
    end_at = confirmed_slot.confirmed_end_at

    suggestions: list[Suggestion] = []
    for fairness, _, place, evaluation in selected:
        verified = place["verification_status"] == _PASS
        tag_codes = [CandidateTag(t) for t in dict.fromkeys(evaluation.tags)]
        if verified:
            tag_codes.append(CandidateTag.AVAILABLE_AT_MEETING_TIME)

        domains = [
            domain_by_code[code]
            for code in fairness.matched_preference_codes
            if code in domain_by_code
        ]
        source_urls = [
            url for url in dict.fromkeys([place["place_url"], place["verification_source"]]) if url
        ]

        suggestions.append(
            Suggestion(
                rank=len(suggestions) + 1,
                category=place["category"],
                place_provider=PlaceProvider.KAKAO,
                external_place_id=place["kakao_place_id"],
                name=place["name"],
                address=place["address"],
                latitude=place["latitude"],
                longitude=place["longitude"],
                external_url=place["place_url"],
                proposed_start_at=start_at,
                proposed_end_at=end_at,
                business_hours=place["business_hours"],
                business_hours_verified=verified,
                open_at_meeting_time=True if verified else None,
                matched_preference_domains=list(dict.fromkeys(domains)),
                reasons=evaluation.reasons,
                tags=[to_candidate_tag(t) for t in tag_codes],
                source_urls=source_urls,
                checked_at=place["checked_at"],
            )
        )

    return {"suggestions": suggestions}
