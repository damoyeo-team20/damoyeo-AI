"""Candidate Place Verifier (Research Sub-Agent).

후보 장소별 영업시간/휴무일을 병렬로 검증한다. 검증 범위는 영업시간·휴무일로만 한정한다
(주차·웨이팅·가격 등은 다루지 않는다). PASS/FAIL/UNKNOWN 3-state를 유지하며, UNKNOWN을 임의로
PASS/FAIL로 단정하지 않는다. 전체 타임아웃을 두되, 시간 안에 검증하지 못한 후보도 UNKNOWN으로
남겨 장소 후보 자체가 사라지지 않게 한다.

날짜만이 아니라 `/schedule`이 확정한 실제 시각(confirmed_start_at~confirmed_end_at)에 영업하는지까지
판정한다.

검색과 판정을 분리한다 — 검색은 Serper(https://serper.dev)로, 판정(구조화 출력)은 Gemini로.
Gemini의 `google_search` grounding 도구를 그대로 썼을 때 별도의 빡빡한 할당량(일반 텍스트 생성과
무관하게) 때문에 자주 막혀서, 검색만 별도 서비스로 뗐다.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.debug import record_debug  # TEMP DEBUG
from app.core.llm import get_llm
from app.graph.state import CandidatesState, PlaceCandidate, VerifiedPlace
from app.prompts.n_candidate_place_verifier import CLASSIFY_SYSTEM_PROMPT, SEARCH_QUERY_TEMPLATE
from app.services.serper_client import SerperResult, search as serper_search

logger = logging.getLogger(__name__)

_OVERALL_TIMEOUT_SECONDS = 20.0


def _format_search_results(results: list[SerperResult]) -> str:
    if not results:
        return "(검색 결과 없음)"
    return "\n".join(
        f"- {r.title}\n  {r.snippet}\n  출처: {r.link}" for r in results
    )


class _Classification(BaseModel):
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    # 사용자에게 그대로 보여줄 영업시간 문구. 확인 못 했으면 None.
    business_hours: str | None = None
    source: str | None = None


def _to_verified_place(
    place: PlaceCandidate, classification: _Classification
) -> VerifiedPlace:
    """검증 여부와 무관하게 Kakao 장소 정보는 보존한다."""
    return {
        "activity": place["activity"],
        "kakao_place_id": place["kakao_place_id"],
        "name": place["name"],
        "address": place["address"],
        "category": place["category"],
        "place_url": place["place_url"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "verification_status": classification.status,
        "business_hours": classification.business_hours,
        "verification_source": classification.source,
        "checked_at": datetime.now(UTC),
    }


async def _verify_one(
    place: PlaceCandidate, date: str, start_time: str, end_time: str
) -> VerifiedPlace:
    classification = _Classification(status="UNKNOWN")
    # 검증 자체를 건너뛰고 항상 UNKNOWN으로 둔다 (거짓 PASS/FAIL을 만들지 않음 — 기존 3-state를
    # 그대로 활용). 빠른 로컬 테스트용 플래그.
    if get_settings().skip_business_hours_verification:
        record_debug(  # TEMP DEBUG
            "n_candidate_place_verifier", {"place": place["name"], "skipped": True}
        )
        return _to_verified_place(place, classification)
    try:
        query = SEARCH_QUERY_TEMPLATE.format(place_name=place["name"], address=place["address"])
        results = await serper_search(query)
        search_text = _format_search_results(results)

        classify_llm = get_llm().with_structured_output(_Classification)
        classification = await classify_llm.ainvoke(
            CLASSIFY_SYSTEM_PROMPT.format(
                date=date,
                start_time=start_time,
                end_time=end_time,
                search_result=search_text,
            )
        )
    except Exception as exc:
        logger.exception("영업 검증 실패: %s", place["name"])
        record_debug(  # TEMP DEBUG
            "n_candidate_place_verifier", {"place": place["name"], "error": repr(exc)}
        )
    else:
        record_debug(  # TEMP DEBUG
            "n_candidate_place_verifier",
            {"place": place["name"], "search_text": search_text, "classification": classification.model_dump()},
        )

    return _to_verified_place(place, classification)


async def verify_places(state: CandidatesState) -> dict:
    places = state.get("place_candidates", [])
    if not places:
        return {"verified_places": [], "verification_timed_out": False}

    confirmed_slot = state["confirmed_slot"]
    start_at = confirmed_slot.confirmed_start_at
    end_at = confirmed_slot.confirmed_end_at
    date = start_at.date().isoformat()
    start_time = start_at.strftime("%H:%M")
    end_time = end_at.strftime("%H:%M")

    tasks = [
        asyncio.create_task(_verify_one(place, date, start_time, end_time)) for place in places
    ]
    done, pending = await asyncio.wait(tasks, timeout=_OVERALL_TIMEOUT_SECONDS)

    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        logger.warning(
            "영업 검증 시간 초과: %d개 후보를 UNKNOWN으로 유지합니다.", len(pending)
        )

    # 입력 순서를 유지한다. 완료된 결과는 그대로 사용하고, timeout된 후보는 장소 정보를 버리지
    # 않은 채 UNKNOWN으로 복원한다. Ranker는 FAIL만 제외하므로 이 후보들도 추천 대상이 된다.
    verified: list[VerifiedPlace] = [
        task.result()
        if task in done
        else _to_verified_place(place, _Classification(status="UNKNOWN"))
        for task, place in zip(tasks, places, strict=True)
    ]
    return {"verified_places": verified, "verification_timed_out": bool(pending)}
