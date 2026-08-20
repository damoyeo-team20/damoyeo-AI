"""N2 Context Router.

candidate_dates가 있을 때만, 이번 발화가 "확정된 날짜를 바꾸고 싶다"는 의사인지 분류한다.
candidate_dates가 없으면(아직 /schedule 호출 전) LLM 호출 없이 곧장 일반 대화로 판단한다 —
기존 동작과 100% 동일하게 유지하기 위함이다.
"""

from pydantic import BaseModel

from app.core.debug import record_debug  # TEMP DEBUG
from app.core.llm import get_llm
from app.graph.context_state import ContextChatState
from app.prompts.n2_context_parser import DATE_INTENT_ROUTER_PROMPT


class _DateIntentResult(BaseModel):
    wants_date_change: bool


async def route_context_message(state: ContextChatState) -> dict:
    candidate_dates = state.get("candidate_dates")
    if not candidate_dates:
        return {"wants_date_change": False}

    history = state.get("history", [])
    transcript = "\n".join(f"{turn.role.value}: {turn.content}" for turn in history)
    candidates_text = ", ".join(c.date.isoformat() for c in candidate_dates)

    llm = get_llm().with_structured_output(_DateIntentResult)
    user = (
        f"## 지금까지 대화\n{transcript}\n\n"
        f"## 고를 수 있는 날짜 후보\n{candidates_text}\n\n"
        f"## 이번 발화\n{state['message']}"
    )
    result: _DateIntentResult = await llm.ainvoke(
        [
            {"role": "system", "content": DATE_INTENT_ROUTER_PROMPT},
            {"role": "user", "content": user},
        ]
    )
    record_debug("n2_context_router", result)  # TEMP DEBUG

    return {"wants_date_change": result.wants_date_change}
