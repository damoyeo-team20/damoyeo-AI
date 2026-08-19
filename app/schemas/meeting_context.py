from pydantic import BaseModel, ConfigDict, Field

# N2 Meeting Context Parser
# 출력 형태는 ai-part-proposal.md 5장 기준: {meeting_tone, activity_hints[], explicit_constraints[], conflicts_with_ui}


class DateRange(BaseModel):
    start: str
    end: str


class TimeRange(BaseModel):
    start: str
    end: str


class UiInputs(BaseModel):
    """지역·시간은 항상 UI 입력이 우선한다. LLM은 이 값을 추론하지 않는다."""

    model_config = ConfigDict(populate_by_name=True)

    region: str
    date_range: DateRange = Field(alias="dateRange")
    time_range: TimeRange = Field(alias="timeRange")


class MeetingContextRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    host_message: str = Field(alias="hostMessage")
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
