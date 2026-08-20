from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# N2 모임 목적 채팅 (2단계: /context/messages 한 턴, /context 최종 요약)
# 계약은 docs/api-design2-backend.md 5장 기준. 지역/날짜/시간대는 다른 화면(UI)에서 이미 확정되므로
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


class ContextMessageRequest(BaseModel):
    """`POST /ai/meetings/{meetingId}/context/messages` — 채팅 한 턴."""

    model_config = ConfigDict(populate_by_name=True)

    # 이전까지의 대화 전체. AI는 상태를 저장하지 않으므로 Back이 매번 통째로 다시 보낸다.
    history: list[ChatTurn] = Field(default_factory=list)
    message: str

    @field_validator("message")
    @classmethod
    def _reject_blank_message(cls, message: str) -> str:
        if not message.strip():
            raise ValueError("message는 공백일 수 없습니다.")
        return message


class ContextMessageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reply: str


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
