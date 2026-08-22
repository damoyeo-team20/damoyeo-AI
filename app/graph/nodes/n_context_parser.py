"""Context Parser. 모임 목적 채팅.

두 단계로 나뉜다.
- `generate_context_reply`: `POST /ai/meetings/{meetingId}/context/messages` — 채팅 한 턴.
- `finalize_meeting_context`: `POST /ai/meetings/{meetingId}/context` — 최종 전송 시 전체 대화 요약.

AI는 상태를 저장하지 않는다 — 두 함수 모두 매 호출마다 `history`를 통째로 받아야 하며, Back이
`meeting_chat_messages`에서 해당 meetingId의 대화 원문을 조회해 실어 보낸다. 지역/날짜/시간대는
다른 화면(UI)에서 이미 확정되므로 이 노드는 관여하지 않는다.
"""

from pydantic import BaseModel

from app.core.llm import extract_text_content, get_llm
from app.graph.context_state import ContextChatState
from app.prompts.n_context_parser import CHAT_SYSTEM_PROMPT, FINALIZE_SYSTEM_PROMPT
from app.schemas.meeting_context import (
    ChatRole,
    ChatTurn,
    ContextFinalizeResponse,
    ContextMessageResponse,
)


def _to_lc_role(role: ChatRole) -> str:
    return "assistant" if role == ChatRole.ASSISTANT else "user"


async def generate_context_reply(history: list[ChatTurn], message: str) -> ContextMessageResponse:
    llm = get_llm()
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    messages += [{"role": _to_lc_role(turn.role), "content": turn.content} for turn in history]
    messages.append({"role": "user", "content": message})

    response = await llm.ainvoke(messages)
    reply = extract_text_content(response.content)
    return ContextMessageResponse(reply=reply)


async def generate_reply_node(state: ContextChatState) -> dict:
    """일반 대화 분기의 그래프 노드 어댑터. candidate_dates는 손대지 않고 그대로 통과시킨다."""

    response = await generate_context_reply(state.get("history", []), state["message"])
    return {"reply": response.reply, "candidate_dates": state.get("candidate_dates")}


class _FinalizeDraft(BaseModel):
    reply: str
    purpose: str


async def finalize_meeting_context(history: list[ChatTurn]) -> ContextFinalizeResponse:
    llm = get_llm().with_structured_output(_FinalizeDraft)
    transcript = "\n".join(f"{turn.role.value}: {turn.content}" for turn in history)

    result: _FinalizeDraft = await llm.ainvoke(
        [
            {"role": "system", "content": FINALIZE_SYSTEM_PROMPT},
            {"role": "user", "content": f"## 대화 전체\n{transcript}"},
        ]
    )
    return ContextFinalizeResponse(reply=result.reply, purpose=result.purpose)
