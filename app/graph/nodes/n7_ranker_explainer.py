"""N7 Ranker & Explainer.

검증을 통과한(또는 UNKNOWN인) 후보 중 최대 3개를 골라 순위와 추천 사유를 작성하고, 최종
`Suggestion` 목록을 만든다. FAIL 판정된 후보는 여기서 제외된다 (폐점·휴무인 곳은 반환하지 않는다).

사실 판정에 해당하는 값은 LLM이 아니라 코드가 붙인다:
  - AVAILABLE_AT_MEETING_TIME 태그와 openAtMeetingTime : N6 검증 결과에서 파생
  - matchedPreferenceDomains : LLM이 고른 코드를 Vocabulary로 domain 변환
  - proposedStartAt/EndAt : l3_slot_builder가 계산한 값
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.errors import AIServiceError
from app.core.llm import get_llm
from app.graph.state import CandidatesState, VerifiedPlace
from app.prompts.n7_ranker_explainer import SYSTEM_PROMPT
from app.schemas.candidates import (
    CandidateTag,
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
# enum에 태그가 추가되면 자동으로 선택지에 포함되도록 여기서 파생시킨다.
_LLM_SELECTABLE_TAGS = [t for t in CandidateTag if t is not CandidateTag.AVAILABLE_AT_MEETING_TIME]
_LLMCandidateTag = Literal[tuple(t.value for t in _LLM_SELECTABLE_TAGS)]  # type: ignore[valid-type]


class _RankedItem(BaseModel):
    kakao_place_id: str
    reasons: list[str] = Field(default_factory=list)
    # 요청에 실제로 있는 코드만 유효하다. 스키마로 제약하지 않고 서버가 대조해서 걸러낸다 —
    # 선호가 하나도 없는 요청에서는 Literal을 만들 수 없기 때문.
    matched_preference_codes: list[str] = Field(default_factory=list)
    # 확실히 해당하는 것만. 근거가 없으면 빈 배열이 정상이다.
    # AVAILABLE_AT_MEETING_TIME은 여기 없다 — 사실 판정이라 검증 결과에서 코드로 붙인다.
    tags: list[_LLMCandidateTag] = Field(default_factory=list)


class _RankingResult(BaseModel):
    ranked: list[_RankedItem] = Field(default_factory=list)


def _eligible(places: list[VerifiedPlace]) -> list[VerifiedPlace]:
    return [p for p in places if p["verification_status"] != _FAIL]


async def _domains_by_code(codes: set[str]) -> dict[str, str]:
    """Vocabulary 조회 실패로 후보 생성 전체를 실패시키지 않는다 — domain만 비워서 진행한다."""
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

    # N4가 활동 유형별로 남긴 집단 수준 사유를 참고 맥락으로 함께 전달한다.
    activity_rationales = {a["activity"]: a["rationale_group"] for a in state.get("activities", [])}
    preferences = state.get("participant_preferences", [])

    llm = get_llm().with_structured_output(_RankingResult)
    system = SYSTEM_PROMPT.format(
        purpose=state["meeting"].purpose,
        participant_preferences=[p.model_dump(by_alias=True) for p in preferences],
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
    result: _RankingResult = await llm.ainvoke(
        [{"role": "system", "content": system}, {"role": "user", "content": "최대 3개를 골라줘."}]
    )

    requested_codes = {p.vocabulary_code for p in preferences}
    domain_by_code = await _domains_by_code(requested_codes)

    by_id = {p["kakao_place_id"]: p for p in eligible}
    confirmed_slot = state["confirmed_slot"]
    start_at = confirmed_slot.confirmed_start_at
    end_at = confirmed_slot.confirmed_end_at

    suggestions: list[Suggestion] = []
    for ranked in result.ranked:
        if len(suggestions) >= _MAX_SUGGESTIONS:
            break
        place = by_id.get(ranked.kakao_place_id)
        if place is None:
            continue

        verified = place["verification_status"] == _PASS
        tag_codes = [CandidateTag(t) for t in dict.fromkeys(ranked.tags)]
        # 영업 검증을 통과한 경우에만 붙인다. UNKNOWN은 확인되지 않은 것이므로 붙이지 않는다.
        if verified:
            tag_codes.append(CandidateTag.AVAILABLE_AT_MEETING_TIME)

        # 모델이 지어낸 코드는 버리고 요청에 실제로 있던 코드만 domain으로 바꾼다.
        domains = [
            domain_by_code[code]
            for code in dict.fromkeys(ranked.matched_preference_codes)
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
                reasons=ranked.reasons,
                tags=[to_candidate_tag(t) for t in tag_codes],
                source_urls=source_urls,
                checked_at=place["checked_at"],
            )
        )

    return {"suggestions": suggestions}
