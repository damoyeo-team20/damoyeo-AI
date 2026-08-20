"""`/ai/meetings/{meetingId}/context/messages`가 실행하는 Context 채팅 한 턴 파이프라인의 상태.

candidate_dates가 있을 때만 라우터가 실제로 날짜 변경 의사를 분류한다. 외부 API 계약
(app/schemas/meeting_context.py)은 이 분리와 무관하게 그대로 유지된다.
"""

from typing import TypedDict

from app.schemas.meeting_context import CandidateDate, ChatTurn


class ContextChatState(TypedDict, total=False):
    # 입력
    history: list[ChatTurn]
    message: str
    candidate_dates: list[CandidateDate] | None

    # 라우터 산출물
    wants_date_change: bool

    # 최종 산출물
    reply: str
