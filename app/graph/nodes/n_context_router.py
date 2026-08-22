"""Context Scope Router.

모든 자연어 입력을 모임 목적 화면의 범위 안/밖으로 분류한다. 후보 날짜가 있는 경우에만
DATE_CHANGE도 허용한다. 직접 답변하거나 날짜를 고르지는 않는다.
"""

from typing import Literal

from pydantic import BaseModel, create_model

from app.core.llm import get_llm
from app.graph.context_state import ContextChatState
from app.prompts.n_context_router import CONTEXT_ROUTE_PROMPT


def _build_route_schema(has_candidate_dates: bool) -> type[BaseModel]:
    """날짜 후보가 없으면 DATE_CHANGE가 정상 출력으로 나올 수 없게 타입에서 막는다."""
    route_values = (
        ("IN_SCOPE", "OUT_OF_SCOPE", "DATE_CHANGE")
        if has_candidate_dates
        else ("IN_SCOPE", "OUT_OF_SCOPE")
    )
    route_type = Literal[route_values]  # type: ignore[valid-type]
    return create_model("_ContextRouteResult", route=(route_type, ...))


async def route_context_message(state: ContextChatState) -> dict:
    candidate_dates = state.get("candidate_dates")
    history = state.get("history", [])
    transcript = "\n".join(f"{turn.role.value}: {turn.content}" for turn in history) or "(없음)"
    candidates_text = (
        ", ".join(c.date.isoformat() for c in candidate_dates)
        if candidate_dates
        else "(없음 — 날짜 변경을 처리할 수 없음)"
    )

    llm = get_llm().with_structured_output(_build_route_schema(bool(candidate_dates)))
    user = (
        f"## 지금까지 대화\n{transcript}\n\n"
        f"## 고를 수 있는 날짜 후보\n{candidates_text}\n\n"
        f"## 이번 발화\n{state['message']}"
    )
    result = await llm.ainvoke(
        [
            {"role": "system", "content": CONTEXT_ROUTE_PROMPT},
            {"role": "user", "content": user},
        ]
    )

    return {"route": result.route}
