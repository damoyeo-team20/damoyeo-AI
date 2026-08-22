from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Context 모임 목적 채팅 (2단계: /context/messages 한 턴, /context 최종 요약)
# 계약은 docs/api-design-backend.md 5장 기준. 지역/날짜/시간대는 다른 화면(UI)에서 이미 확정되므로
# 이 노드는 관여하지 않는다 — UiInputs/UiConflict 같은 개념은 새 계약에 없다.
#
# 대화 결과는 구조화된 객체가 아니라 한 문장 purpose로 내려간다. /candidates도 이 문장을
# meeting.purpose로 그대로 받으므로, 중간 구조체(옛 MeetingContext)는 더 이상 없다.


class ChatRole(str, Enum):
    """`meeting_chat_messages.role`과 동일."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"


class ChatTurn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role: ChatRole
    content: str


class CandidateDate(BaseModel):
    """참여자 전원 가능 날짜 후보 하나 + 지금 확정된 날짜인지 여부."""

    model_config = ConfigDict(populate_by_name=True)

    date: date
    selected: bool


def _validate_candidate_dates(dates: list[CandidateDate]) -> list[CandidateDate]:
    if not dates:
        raise ValueError("candidateDates는 최소 1개 이상이어야 합니다.")
    if len({c.date for c in dates}) != len(dates):
        raise ValueError("candidateDates에 중복된 날짜가 있습니다.")
    if sum(1 for c in dates if c.selected) != 1:
        raise ValueError("candidateDates 중 selected:true는 정확히 1개여야 합니다.")
    return dates


class ContextMessageRequest(BaseModel):
    """`POST /ai/meetings/{meetingId}/context/messages` — 채팅 한 턴."""

    model_config = ConfigDict(populate_by_name=True)

    # 이전까지의 대화 전체. AI는 상태를 저장하지 않으므로 Back이 매번 통째로 다시 보낸다.
    history: list[ChatTurn] = Field(default_factory=list)
    message: str
    # /schedule로 날짜가 이미 확정된 뒤에만 보낸다. 없으면 날짜 변경 의도를 판단하지 않는다.
    candidate_dates: list[CandidateDate] | None = Field(default=None, alias="candidateDates")

    @field_validator("message")
    @classmethod
    def _reject_blank_message(cls, message: str) -> str:
        if not message.strip():
            raise ValueError("message는 공백일 수 없습니다.")
        return message

    @field_validator("candidate_dates")
    @classmethod
    def _check_candidate_dates(
        cls, dates: list[CandidateDate] | None
    ) -> list[CandidateDate] | None:
        if dates is None:
            return dates
        return _validate_candidate_dates(dates)


class ContextMessageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reply: str
    # 요청에 candidateDates가 있었을 때만 채워진다. 날짜를 바꿨으면 selected 위치만 이동해서 온다.
    candidate_dates: list[CandidateDate] | None = Field(default=None, alias="candidateDates")


class ContextFinalizeRequest(BaseModel):
    """`POST /ai/meetings/{meetingId}/context` — 최종 전송 시 전체 대화 요약."""

    model_config = ConfigDict(populate_by_name=True)

    history: list[ChatTurn]

    @field_validator("history")
    @classmethod
    def _require_user_turn(cls, history: list[ChatTurn]) -> list[ChatTurn]:
        if not any(turn.role == ChatRole.USER for turn in history):
            raise ValueError("history에 USER 발화가 최소 1개 있어야 합니다.")
        return history


class ContextFinalizeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reply: str
    # meetings.purpose로 저장될 한 문장 요약, 최대 1,000자.
    purpose: str
