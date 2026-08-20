from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# `POST /ai/meetings/{meetingId}/schedule` 계약.
#
# 날짜 교집합 계산은 Back이 한다. 이 API는 그 결과(commonAvailableDates) 중 어느 날이 이번 모임에
# 가장 적합한지만 고르고 이유를 한 줄로 붙인다. 구체 시각은 LLM이 아니라 코드가 계산한다.


class PreferredTimeOfDay(str, Enum):
    """`meetings.preferred_time_of_day`. 구체 시각이 아니라 시간대 구분만 받는다."""

    DAYTIME = "DAYTIME"
    LATE_AFTERNOON = "LATE_AFTERNOON"
    EVENING = "EVENING"
    ANY = "ANY"


# 각 시간대의 현지 시각 범위 (시작 가능 시각, 종료 마감 시각).
TIME_OF_DAY_WINDOWS: dict[PreferredTimeOfDay, tuple[int, int]] = {
    PreferredTimeOfDay.DAYTIME: (11, 15),
    PreferredTimeOfDay.LATE_AFTERNOON: (15, 18),
    PreferredTimeOfDay.EVENING: (18, 23),
    PreferredTimeOfDay.ANY: (11, 23),
}

DEFAULT_DURATION_MINUTES = 120


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Back이 계산한 전원 가능 날짜. AI는 이 안에서만 고른다.
    common_available_dates: list[date] = Field(alias="commonAvailableDates", min_length=1)
    preferred_time_of_day: PreferredTimeOfDay = Field(alias="preferredTimeOfDay")
    # null이면 DEFAULT_DURATION_MINUTES를 적용한다.
    duration_minutes: int | None = Field(default=None, alias="durationMinutes", gt=0)
    timezone: str = "Asia/Seoul"

    @field_validator("common_available_dates")
    @classmethod
    def _reject_duplicate_dates(cls, dates: list[date]) -> list[date]:
        if len(set(dates)) != len(dates):
            raise ValueError("commonAvailableDates에 중복된 날짜가 있습니다.")
        return dates

    @property
    def applied_duration_minutes(self) -> int:
        return self.duration_minutes or DEFAULT_DURATION_MINUTES


class ScheduleResponse(BaseModel):
    """Back이 이 응답을 검증한다 (실패 시 Front에 502 AI_RESPONSE_INVALID).

    - resolvedStartAt의 현지 날짜가 commonAvailableDates 중 하나일 것
    - resolvedEndAt이 resolvedStartAt보다 뒤일 것
    - 두 시각의 차이가 정확히 durationMinutes일 것

    세 조건 모두 이 응답을 만드는 `resolve_schedule`(N3)이 구조적으로 보장한다 — 고를 수 있는
    날짜를 LLM 응답 스키마 자체에서 Literal로 제약하고, 시각은 `l3_slot_builder`가 정확히
    duration만큼의 간격으로 계산하기 때문에 별도 런타임 검증이 없어도 어길 수 없다.
    """

    model_config = ConfigDict(populate_by_name=True)

    resolved_start_at: datetime = Field(alias="resolvedStartAt")
    resolved_end_at: datetime = Field(alias="resolvedEndAt")
    # 왜 이 날짜인지 한 문장. 모임 목적·요일 특성에 근거해야 하며 상투적인 문구는 쓰지 않는다.
    reason: str
