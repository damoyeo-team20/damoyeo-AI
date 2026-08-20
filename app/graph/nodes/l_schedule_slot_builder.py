"""Schedule Slot Builder. 비-LLM 노드.

참여자 날짜 교집합 자체는 Back이 계산해서 `commonAvailableDates`로 넘겨준다.
`n_schedule_resolver`(Schedule Resolver)가 그중 하나를 고르면, 여기서는 그 날짜에 선호
시간대와 모임 길이를 적용해 구체적인 시작/종료 시각을 계산한다.

시각 결정은 계산이지 판단이 아니므로 LLM에 맡기지 않는다 — 시간대 창의 시작 시각에 모임을 붙이고
모임 길이만큼 뒤를 끝으로 잡는다. 같은 입력이면 항상 같은 결과가 나온다.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import AIServiceError
from app.schemas.schedule import TIME_OF_DAY_WINDOWS, PreferredTimeOfDay


def build_slot(
    chosen_date: date,
    preferred_time_of_day: PreferredTimeOfDay,
    duration_minutes: int,
    timezone: str,
) -> tuple[datetime, datetime]:
    """고른 날짜에 대한 (시작, 종료) 시각을 계산한다."""
    window_start_hour, window_end_hour = TIME_OF_DAY_WINDOWS[preferred_time_of_day]
    window_minutes = (window_end_hour - window_start_hour) * 60

    if duration_minutes > window_minutes:
        raise AIServiceError(
            code="INVALID_DURATION_FOR_TIME_OF_DAY",
            message=(
                f"모임 길이 {duration_minutes}분이 선택한 시간대"
                f"({preferred_time_of_day.value}, {window_minutes}분)보다 깁니다."
            ),
            status_code=400,
            retryable=False,
        )

    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AIServiceError(
            code="REQUEST_SCHEMA_INVALID",
            message=f"알 수 없는 timezone입니다: {timezone}",
            status_code=422,
            retryable=False,
        ) from exc

    start = datetime.combine(chosen_date, datetime.min.time(), tzinfo=tz).replace(
        hour=window_start_hour
    )
    return start, start + timedelta(minutes=duration_minutes)
