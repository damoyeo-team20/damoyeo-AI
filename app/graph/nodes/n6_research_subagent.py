"""N6 Research Sub-Agent.

후보 장소별 영업시간/휴무일을 병렬로 검증한다. 검증 범위는 영업시간·휴무일로만 한정한다
(주차·웨이팅·가격 등은 다루지 않는다). PASS/FAIL/UNKNOWN 3-state를 유지하며, UNKNOWN을 임의로
PASS/FAIL로 단정하지 않는다. 전체 타임아웃을 두고, 타임아웃 시 검증 완료분만 반환한다.
"""

import asyncio
import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.graph.state import CandidatesState, PlaceCandidate, VerifiedPlace
from app.prompts.n6_research_subagent import CLASSIFY_SYSTEM_PROMPT, SEARCH_PROMPT

logger = logging.getLogger(__name__)

_OVERALL_TIMEOUT_SECONDS = 20.0


class _Classification(BaseModel):
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    evidence: str | None = None
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


async def _verify_one(place: PlaceCandidate, date: str) -> VerifiedPlace:
    classification = _Classification(status="UNKNOWN", evidence="검증 중 오류가 발생했습니다.")
    try:
        search_llm = get_llm().bind_tools([{"google_search": {}}])
        search_response = await search_llm.ainvoke(
            SEARCH_PROMPT.format(place_name=place["name"], address=place["address"], date=date)
        )
        search_text = _extract_text(search_response.content)

        classify_llm = get_llm().with_structured_output(_Classification)
        classification = await classify_llm.ainvoke(
            CLASSIFY_SYSTEM_PROMPT.format(date=date, search_result=search_text)
        )
    except Exception:
        logger.exception("영업 검증 실패: %s", place["name"])

    return {
        "activity": place["activity"],
        "kakao_place_id": place["kakao_place_id"],
        "name": place["name"],
        "address": place["address"],
        "category": place["category"],
        "verification_status": classification.status,
        "verification_evidence": classification.evidence,
        "verification_source": classification.source,
        "verification_confidence": classification.confidence,
    }


async def verify_places(state: CandidatesState) -> dict:
    places = state.get("place_candidates", [])
    date = state["confirmed_slot"].date

    tasks = [asyncio.create_task(_verify_one(place, date)) for place in places]
    if not tasks:
        return {"verified_places": [], "verification_timed_out": False}

    done, pending = await asyncio.wait(tasks, timeout=_OVERALL_TIMEOUT_SECONDS)

    for task in pending:
        task.cancel()

    verified: list[VerifiedPlace] = [task.result() for task in done]
    return {"verified_places": verified, "verification_timed_out": bool(pending)}
