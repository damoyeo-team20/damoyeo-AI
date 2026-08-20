from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# N2 Meeting Context Parser
# 출력 형태는 ai-part-proposal.md 5장 기준: {meeting_tone, activity_hints[], explicit_constraints[], conflicts_with_ui}
# 입력 필드는 docs/db_schema.md의 `meetings` 테이블 컬럼에 1:1로 맞춘다.


class PreferredTimeOfDay(str, Enum):
    """`meetings.preferred_time_of_day`. 구체 시각이 아니라 시간대 구분만 받는다."""

    DAYTIME = "DAYTIME"
    LATE_AFTERNOON = "LATE_AFTERNOON"
    EVENING = "EVENING"
    ANY = "ANY"


class UiInputs(BaseModel):
    """지역·기간·시간대는 항상 UI 입력이 우선한다. LLM은 이 값을 추론하지 않는다."""

    model_config = ConfigDict(populate_by_name=True)

    # meetings.region
    region: str
    # meetings.schedule_search_from / schedule_search_to
    schedule_search_from: date = Field(alias="scheduleSearchFrom")
    schedule_search_to: date = Field(alias="scheduleSearchTo")
    # meetings.preferred_time_of_day
    preferred_time_of_day: PreferredTimeOfDay = Field(alias="preferredTimeOfDay")


class MeetingContextRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # meetings.purpose — 주최자가 자연어로 남긴 이번 모임 목적.
    purpose: str = Field(alias="purpose")
    ui_inputs: UiInputs = Field(alias="uiInputs")


class MeetingContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    activity_hints: list[str] = Field(default_factory=list, alias="activityHints")
    meeting_tone: str | None = Field(default=None, alias="meetingTone")
    # 주최자가 명시적으로 못박은 조건 (예: "알레르기 있는 사람 있으니 견과류 빼줘").
    explicit_constraints: list[str] = Field(default_factory=list, alias="explicitConstraints")


class UiConflict(BaseModel):
    """자연어 발화가 UI 입력값과 다를 때만 채워진다. AI는 UI 값을 임의로 덮어쓰지 않는다."""

    model_config = ConfigDict(populate_by_name=True)

    field: str
    ui_value: str = Field(alias="uiValue")
    mentioned_value: str = Field(alias="mentionedValue")
    question: str


class MeetingContextResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    meeting_context: MeetingContext = Field(alias="meetingContext")
    conflicts_with_ui: list[UiConflict] = Field(default_factory=list, alias="conflictsWithUi")
