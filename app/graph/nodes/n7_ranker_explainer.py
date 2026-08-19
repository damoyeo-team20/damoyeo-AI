"""N7 Ranker & Explainer.

검증을 통과한(또는 UNKNOWN인) 후보 중 최대 3개를 골라 추천 사유를 작성한다.
FAIL 판정된 후보는 이 노드에 도달하기 전에 이미 제외된다.
"""

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.graph.state import CandidatesState, VerifiedPlace
from app.prompts.n7_ranker_explainer import SYSTEM_PROMPT
from app.schemas.candidates import Candidate, Place, Verification, VerificationStatus

_MAX_CANDIDATES = 3


class _RankedItem(BaseModel):
    kakao_place_id: str
    rationale: str


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

    llm = get_llm().with_structured_output(_RankingResult)
    system = SYSTEM_PROMPT.format(
        meeting_context=state.get("meeting_context", {}),
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
        final_candidates.append(
            Candidate(
                activity=place["activity"],
                place=Place(
                    kakao_place_id=place["kakao_place_id"],
                    name=place["name"],
                    address=place["address"],
                    category=place["category"],
                ),
                verification=Verification(
                    status=VerificationStatus(place["verification_status"]),
                    evidence=place["verification_evidence"],
                    source=place["verification_source"],
                    confidence=place["verification_confidence"],
                ),
                rationale=ranked.rationale,
            )
        )

    return {"final_candidates": final_candidates}
