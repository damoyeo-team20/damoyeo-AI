"""선랭킹 결과와 단계적 영업 검증 결과를 외부 ``Suggestion`` DTO로 조립한다.

이 노드는 LLM을 호출하지 않는다. 명확한 영업 검증 ``FAIL``을 제거하고, 선랭킹 순서를
유지한 채 최대 3개를 선택한다. 영업 가능 사실 필드와 태그는 ``PASS``일 때만 코드로 붙인다.
"""

import logging

from app.core.errors import AIServiceError
from app.graph.candidates_state import CandidatesState, RankedCandidate, VerifiedPlace
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


async def _domains_by_code(codes: set[str]) -> dict[str, str]:
    """Vocabulary 조회 실패로 후보 생성 전체를 실패시키지 않는다."""

    if not codes:
        return {}
    try:
        vocabulary = await fetch_vocabulary()
    except AIServiceError:
        logger.warning("후보 조립 중 Vocabulary 조회 실패 — matchedPreferenceDomains 없이 진행")
        return {}
    return {entry.code: entry.domain for entry in vocabulary if entry.code in codes}


def _select_verified_candidates(
    ranked_candidates: list[RankedCandidate],
    verified_places: list[VerifiedPlace],
) -> list[tuple[RankedCandidate, VerifiedPlace]]:
    """검증 완료 후보를 선랭킹 순서로 복원하고 FAIL을 제외해 최대 3개를 고른다."""

    verified_by_id = {
        place["kakao_place_id"]: place for place in verified_places
    }
    selected: list[tuple[RankedCandidate, VerifiedPlace]] = []
    for candidate in ranked_candidates:
        place_id = candidate["place"]["kakao_place_id"]
        verified = verified_by_id.get(place_id)
        if verified is None or verified["verification_status"] == _FAIL:
            continue
        selected.append((candidate, verified))
        if len(selected) == _MAX_SUGGESTIONS:
            break
    return selected


async def build_suggestions(state: CandidatesState) -> dict:
    selected = _select_verified_candidates(
        state.get("ranked_candidates", []),
        state.get("verified_places", []),
    )
    if not selected:
        return {"suggestions": []}

    matched_codes = {
        code
        for candidate, _ in selected
        for code in candidate["matched_preference_codes"]
    }
    domain_by_code = await _domains_by_code(matched_codes)

    confirmed_slot = state["confirmed_slot"]
    suggestions: list[Suggestion] = []
    for candidate, place in selected:
        # PASS라도 표시할 영업시간 근거가 없으면 확인 완료라고 주장하지 않는다.
        verified = (
            place["verification_status"] == _PASS
            and place["business_hours"] is not None
        )
        tag_codes = [CandidateTag(tag) for tag in dict.fromkeys(candidate["tags"])]
        if verified and CandidateTag.AVAILABLE_AT_MEETING_TIME not in tag_codes:
            tag_codes.append(CandidateTag.AVAILABLE_AT_MEETING_TIME)

        domains = [
            domain_by_code[code]
            for code in candidate["matched_preference_codes"]
            if code in domain_by_code
        ]
        kakao_url = place["place_url"] or (
            f"https://place.map.kakao.com/{place['kakao_place_id']}"
        )
        source_urls = [
            url
            for url in dict.fromkeys([kakao_url, place["verification_source"]])
            if url
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
                external_url=kakao_url,
                proposed_start_at=confirmed_slot.confirmed_start_at,
                proposed_end_at=confirmed_slot.confirmed_end_at,
                business_hours=place["business_hours"],
                business_hours_verified=verified,
                open_at_meeting_time=True if verified else None,
                matched_preference_domains=list(dict.fromkeys(domains)),
                reasons=candidate["reasons"],
                tags=[to_candidate_tag(tag) for tag in tag_codes],
                source_urls=source_urls,
                checked_at=place["checked_at"],
            )
        )

    return {"suggestions": suggestions}
