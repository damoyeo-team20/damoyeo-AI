"""Candidate Place Verifier (Research Sub-Agent).

선랭킹된 후보 장소의 영업시간/휴무일을 단계적으로 검증한다. 검증 범위는 영업시간·휴무일로만 한정한다
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
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.config import get_settings
from app.core.debug import record_debug  # TEMP DEBUG
from app.core.llm import get_llm
from app.graph.candidates_state import CandidatesState, PlaceCandidate, VerifiedPlace
from app.prompts.n_candidate_place_verifier import CLASSIFY_SYSTEM_PROMPT, SEARCH_QUERY_TEMPLATE
from app.services.serper_client import SerperResult, search as serper_search

logger = logging.getLogger(__name__)

_OVERALL_TIMEOUT_SECONDS = 20.0
_BUSINESS_TIMEZONE = ZoneInfo("Asia/Seoul")
_INITIAL_BATCH_SIZE = 6
_FALLBACK_BATCH_SIZE = 3
_USABLE_TARGET = 3


def _format_search_results(results: list[SerperResult]) -> str:
    if not results:
        return "(검색 결과 없음)"
    return "\n".join(
        f"- {r.title}\n  {r.snippet}\n  출처: {r.link}" for r in results
    )


class _Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "FAIL", "UNKNOWN"]
    # 사용자에게 그대로 보여줄 영업시간 문구. 확인 못 했으면 None.
    business_hours: str | None = None
    source: str | None = None

    @field_validator("business_hours", "source")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


def _normalize_classification(
    classification: _Classification,
    results: list[SerperResult],
) -> _Classification:
    """근거 없는 확정 판정을 API 경계 밖으로 내보내지 않고 UNKNOWN으로 낮춘다."""

    allowed_sources = {result.link for result in results if result.link}
    source = classification.source if classification.source in allowed_sources else None
    business_hours = classification.business_hours

    lacks_required_evidence = (
        classification.status in {"PASS", "FAIL"} and source is None
    ) or (classification.status == "PASS" and business_hours is None)
    if lacks_required_evidence:
        return _Classification(
            status="UNKNOWN",
            business_hours=business_hours,
            source=source,
        )
    return classification.model_copy(update={"source": source})


def _to_verified_place(
    place: PlaceCandidate, classification: _Classification
) -> VerifiedPlace:
    """검증 여부와 무관하게 Kakao 장소 정보는 보존한다."""
    return {
        "search_plan_label": place["search_plan_label"],
        "search_plan_source": place["search_plan_source"],
        "search_plan_rationale": place["search_plan_rationale"],
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
        query = SEARCH_QUERY_TEMPLATE.format(
            place_name=place["name"],
            address=place["address"],
        )
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
        classification = _normalize_classification(classification, results)
    except Exception as exc:
        logger.exception("영업 검증 실패: %s", place["name"])
        record_debug(  # TEMP DEBUG
            "n_candidate_place_verifier", {"place": place["name"], "error": repr(exc)}
        )
    else:
        record_debug(  # TEMP DEBUG
            "n_candidate_place_verifier",
            {
                "place": place["name"],
                "search_text": search_text,
                "classification": classification.model_dump(),
            },
        )

    return _to_verified_place(place, classification)


async def _verify_batch(
    places: list[PlaceCandidate],
    *,
    date: str,
    start_time: str,
    end_time: str,
    timeout: float,
) -> tuple[list[VerifiedPlace], bool]:
    """한 batch를 병렬 검증하고 timeout 후보를 입력 순서의 UNKNOWN으로 복원한다."""

    if not places:
        return [], False
    if timeout <= 0:
        return [
            _to_verified_place(place, _Classification(status="UNKNOWN")) for place in places
        ], True

    tasks = [
        asyncio.create_task(_verify_one(place, date, start_time, end_time)) for place in places
    ]
    done, pending = await asyncio.wait(tasks, timeout=timeout)

    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        logger.warning(
            "영업 검증 시간 초과: %d개 후보를 UNKNOWN으로 유지합니다.", len(pending)
        )

    verified: list[VerifiedPlace] = []
    for task, place in zip(tasks, places, strict=True):
        if task not in done or task.cancelled():
            verified.append(_to_verified_place(place, _Classification(status="UNKNOWN")))
            continue
        try:
            verified.append(task.result())
        except Exception as exc:  # _verify_one을 대체한 테스트/향후 구현도 fail-soft로 격리한다.
            logger.exception("영업 검증 작업 실패: %s", place["name"], exc_info=exc)
            verified.append(_to_verified_place(place, _Classification(status="UNKNOWN")))

    return verified, bool(pending)


def _usable_count(places: list[VerifiedPlace]) -> int:
    """명확한 FAIL만 제외하며 PASS와 UNKNOWN은 추천 가능한 후보로 센다."""

    return sum(place["verification_status"] != "FAIL" for place in places)


async def verify_places(state: CandidatesState) -> dict:
    ranked_candidates = state.get("ranked_candidates", [])
    ranked_places = [candidate["place"] for candidate in ranked_candidates]
    if not ranked_places:
        return {
            "verified_places": [],
            "verification_timed_out": False,
            "verification_metrics": {
                "rankedCandidateCount": 0,
                "attemptedCandidateCount": 0,
                "usableCandidateCount": 0,
            },
        }

    confirmed_slot = state["confirmed_slot"]
    # Back은 TIMESTAMPTZ를 UTC(`Z`)로 직렬화할 수 있다. 웹의 국내 매장 영업시간은 한국
    # 현지 시각 기준이므로 날짜와 시작·종료 시각을 모두 Asia/Seoul로 변환한 뒤 판정한다.
    start_at = confirmed_slot.confirmed_start_at.astimezone(_BUSINESS_TIMEZONE)
    end_at = confirmed_slot.confirmed_end_at.astimezone(_BUSINESS_TIMEZONE)
    date = start_at.date().isoformat()
    start_time = start_at.strftime("%H:%M")
    end_time = end_at.strftime("%H:%M")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _OVERALL_TIMEOUT_SECONDS

    verified: list[VerifiedPlace] = []
    timed_out = False
    cursor = 0
    batch_size = _INITIAL_BATCH_SIZE

    # 첫 6개를 확인한 뒤에도 non-FAIL 후보가 3개 미만이면 남은 선랭킹 후보를 3개씩
    # 계속 확인한다. 후보 3개 확보, 전체 후보 소진, 공통 deadline 도달 중 하나에서 끝난다.
    while cursor < len(ranked_places) and _usable_count(verified) < _USABLE_TARGET:
        batch_places = ranked_places[cursor : cursor + batch_size]
        batch_verified, batch_timed_out = await _verify_batch(
            batch_places,
            date=date,
            start_time=start_time,
            end_time=end_time,
            timeout=max(0.0, deadline - loop.time()),
        )
        verified.extend(batch_verified)
        timed_out = timed_out or batch_timed_out
        cursor += len(batch_places)
        batch_size = _FALLBACK_BATCH_SIZE

    usable_count = _usable_count(verified)
    return {
        "verified_places": verified,
        "verification_timed_out": timed_out,
        "verification_metrics": {
            "rankedCandidateCount": len(ranked_places),
            "attemptedCandidateCount": len(verified),
            "usableCandidateCount": usable_count,
        },
    }
