"""N7 Ranker & Explainer.

검증을 통과한(또는 UNKNOWN인) 후보 중 최대 3개를 골라 추천 사유를 작성한다.
FAIL 판정된 후보는 이 노드에 도달하기 전에 이미 제외된다.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.graph.state import CandidatesState, VerifiedPlace
from app.prompts.n7_ranker_explainer import SYSTEM_PROMPT
from app.schemas.candidates import (
    Candidate,
    CandidateTag,
    Place,
    Verification,
    VerificationStatus,
    to_candidate_tag,
)
from app.schemas.meeting_context import MeetingContext

_MAX_CANDIDATES = 3

# AVAILABLE_AT_MEETING_TIME은 영업 검증 결과에서 파생되는 사실이므로 LLM 선택지에서 제외한다.
# enum에 태그가 추가되면 자동으로 선택지에 포함되도록 여기서 파생시킨다.
_LLM_SELECTABLE_TAGS = [t for t in CandidateTag if t is not CandidateTag.AVAILABLE_AT_MEETING_TIME]
_LLMCandidateTag = Literal[tuple(t.value for t in _LLM_SELECTABLE_TAGS)]  # type: ignore[valid-type]


class _RankedItem(BaseModel):
    kakao_place_id: str
    rationale: str
    # 확실히 해당하는 것만. 근거가 없으면 빈 배열이 정상이다.
    # AVAILABLE_AT_MEETING_TIME은 여기 없다 — 사실 판정이라 검증 결과에서 코드로 붙인다.
    tags: list[_LLMCandidateTag] = Field(default_factory=list)


class _RankingResult(BaseModel):
    ranked: list[_RankedItem] = Field(default_factory=list)


def _eligible(places: list[VerifiedPlace]) -> list[VerifiedPlace]:
    return [p for p in places if p["verification_status"] != VerificationStatus.FAIL.value]


async def rank_and_explain(state: CandidatesState) -> dict:
    eligible = _eligible(state.get("verified_places", []))
    if not eligible:
        return {"final_candidates": []}

    # N4가 활동 유형별로 남긴 집단 수준 사유를 참고 맥락으로 함께 전달한다.
    activity_rationales = {
        a["activity"]: a["rationale_group"] for a in state.get("activities", [])
    }

    meeting_context = state.get("meeting_context") or MeetingContext()

    llm = get_llm().with_structured_output(_RankingResult)
    system = SYSTEM_PROMPT.format(
        meeting_context=meeting_context.model_dump(by_alias=True),
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

    by_id = {p["kakao_place_id"]: p for p in eligible}
    final_candidates: list[Candidate] = []
    for ranked in result.ranked[:_MAX_CANDIDATES]:
        place = by_id.get(ranked.kakao_place_id)
        if place is None:
            continue

        tag_codes = [CandidateTag(t) for t in dict.fromkeys(ranked.tags)]
        # 영업 검증을 통과한 경우에만 붙인다. UNKNOWN은 확인되지 않은 것이므로 붙이지 않는다.
        if place["verification_status"] == VerificationStatus.PASS.value:
            tag_codes.append(CandidateTag.AVAILABLE_AT_MEETING_TIME)

        final_candidates.append(
            Candidate(
                activity=place["activity"],
                place=Place(
                    kakao_place_id=place["kakao_place_id"],
                    name=place["name"],
                    address=place["address"],
                    category=place["category"],
                    place_url=place["place_url"],
                ),
                verification=Verification(
                    status=VerificationStatus(place["verification_status"]),
                    evidence=place["verification_evidence"],
                    source=place["verification_source"],
                    confidence=place["verification_confidence"],
                ),
                rationale=ranked.rationale,
                tags=[to_candidate_tag(t) for t in tag_codes],
            )
        )

    return {"final_candidates": final_candidates}
