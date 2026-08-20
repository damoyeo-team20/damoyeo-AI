"""모임 목적 입력의 결정론적 응답 가드레일."""

from app.graph.context_state import ContextChatState


async def guide_context_input(state: ContextChatState) -> dict:
    return {
        "reply": "이번 모임의 목적, 원하는 분위기나 활동, 꼭 반영할 조건을 알려주세요.",
        "candidate_dates": state.get("candidate_dates"),
    }
