"""N3 Schedule Resolver.

날짜 교집합(어느 날이 전원 가능한지) 자체는 Back이 계산해서 `commonAvailableDates`로 넘겨준다.
이 노드는 그중 하나를 고르고 이유를 한 줄로 붙인다. 고른 날짜에 대한 구체 시작/종료 시각은
LLM이 아니라 `l3_slot_builder`가 계산한다 — 시간대 창에 길이를 맞추는 건 판단이 아니라 계산이라
LLM에 맡기지 않는다.

`POST /ai/meetings/{meetingId}/schedule`가 호출한다.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.core.llm import get_llm
from app.graph.nodes.l3_slot_builder import build_slot
from app.prompts.schedule import SYSTEM_PROMPT
from app.schemas.schedule import ScheduleRequest, ScheduleResponse


def _build_decision_schema(common_dates: list[date]) -> type[BaseModel]:
    """고를 수 있는 날짜를 응답 스키마에 박아 넣어 목록 밖의 날짜를 원천 차단한다."""
    date_values = tuple(d.isoformat() for d in common_dates)
    ChosenDate = Literal[date_values]  # type: ignore[valid-type]

    class _ScheduleDecision(BaseModel):
        chosen_date: ChosenDate
        reason: str

    return _ScheduleDecision


async def resolve_schedule(request: ScheduleRequest) -> ScheduleResponse:
    llm = get_llm().with_structured_output(_build_decision_schema(request.common_available_dates))

    system = SYSTEM_PROMPT.format(
        common_available_dates=[
            f"{d.isoformat()} ({d.strftime('%A')})" for d in request.common_available_dates
        ],
        preferred_time_of_day=request.preferred_time_of_day.value,
    )
    result = await llm.ainvoke(
        [{"role": "system", "content": system}, {"role": "user", "content": "날짜를 골라줘."}]
    )

    chosen_date = date.fromisoformat(result.chosen_date)
    start_at, end_at = build_slot(
        chosen_date=chosen_date,
        preferred_time_of_day=request.preferred_time_of_day,
        duration_minutes=request.applied_duration_minutes,
        timezone=request.timezone,
    )

    return ScheduleResponse(resolved_start_at=start_at, resolved_end_at=end_at, reason=result.reason)
