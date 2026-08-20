"""N6 Research Sub-Agent.

후보 장소별 영업시간/휴무일을 병렬로 검증한다. 검증 범위는 영업시간·휴무일로만 한정한다
(주차·웨이팅·가격 등은 다루지 않는다). PASS/FAIL/UNKNOWN 3-state를 유지하며, UNKNOWN을 임의로
PASS/FAIL로 단정하지 않는다. 전체 타임아웃을 두고, 타임아웃 시 검증 완료분만 반환한다.

날짜만이 아니라 `/schedule`이 확정한 실제 시각(confirmed_start_at~confirmed_end_at)에 영업하는지까지
판정한다.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.llm import extract_text_content, get_llm
from app.graph.state import CandidatesState, PlaceCandidate, VerifiedPlace
from app.prompts.n6_research_subagent import CLASSIFY_SYSTEM_PROMPT, SEARCH_PROMPT

logger = logging.getLogger(__name__)

_OVERALL_TIMEOUT_SECONDS = 20.0


class _Classification(BaseModel):
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    # 사용자에게 그대로 보여줄 영업시간 문구. 확인 못 했으면 None.
    business_hours: str | None = None
    source: str | None = None


async def _verify_one(
    place: PlaceCandidate, date: str, start_time: str, end_time: str
) -> VerifiedPlace:
    classification = _Classification(status="UNKNOWN")
    # 임시 우회: Gemini google_search 할당량 문제로 테스트가 막혀서, 검증 자체를 건너뛰고
    # 항상 UNKNOWN으로 둔다 (거짓 PASS/FAIL을 만들지 않음 — 기존 3-state를 그대로 활용).
    if get_settings().skip_business_hours_verification:
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
    try:
        search_llm = get_llm().bind_tools([{"google_search": {}}])
        search_response = await search_llm.ainvoke(
            SEARCH_PROMPT.format(
                place_name=place["name"],
                address=place["address"],
                date=date,
                start_time=start_time,
                end_time=end_time,
            )
        )
        search_text = extract_text_content(search_response.content)

        classify_llm = get_llm().with_structured_output(_Classification)
        classification = await classify_llm.ainvoke(
            CLASSIFY_SYSTEM_PROMPT.format(
                date=date,
                start_time=start_time,
                end_time=end_time,
                search_result=search_text,
            )
        )
    except Exception:
        logger.exception("영업 검증 실패: %s", place["name"])

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

    verified: list[VerifiedPlace] = [task.result() for task in done]
    return {"verified_places": verified, "verification_timed_out": bool(pending)}
