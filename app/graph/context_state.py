"""`/ai/meetings/{meetingId}/context/messages`가 실행하는 Context 채팅 한 턴 파이프라인의 상태.

라우터가 모든 입력의 범위를 먼저 확인한다. 정상 모임 목적 입력은 Context Parser로, 범위 밖 입력은
고정 가드레일로, 후보 날짜가 있는 상태의 날짜 변경 요청은 Date Reselector로 보낸다. 외부 API 계약
(app/schemas/meeting_context.py)은 이 내부 분기와 무관하게 그대로 유지된다.
"""

from typing import Literal, TypedDict

from app.schemas.meeting_context import CandidateDate, ChatTurn


class ContextChatState(TypedDict, total=False):
    # 입력
    history: list[ChatTurn]
    message: str
    candidate_dates: list[CandidateDate] | None

    # 라우터 산출물: IN_SCOPE | OUT_OF_SCOPE | DATE_CHANGE
    route: Literal["IN_SCOPE", "OUT_OF_SCOPE", "DATE_CHANGE"]

    # 최종 산출물
    reply: str
