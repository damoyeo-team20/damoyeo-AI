"""N2 Date Reselector.

라우터가 "날짜를 바꾸고 싶다"로 분류했을 때만 실행된다. 후보(candidate_dates) 중 사용자가
실제로 특정한 날짜가 있으면 그쪽으로 selected를 옮기고, 아직 어느 날짜인지 불분명하면 바꾸지
않고 되묻는다 — chosen_date를 Literal이면서 None도 허용해 억지로 아무 후보나 고르지 않게
한다. 목록 밖 날짜가 나올 수 없도록 스키마 자체에서 후보로만 제약한다 (n3_schedule_resolver와
같은 방식).
"""

from typing import Literal

from pydantic import BaseModel, create_model

from app.core.debug import record_debug  # TEMP DEBUG
from app.core.llm import get_llm
from app.graph.context_state import ContextChatState
from app.prompts.n2_context_parser import DATE_RESELECT_SYSTEM_PROMPT
from app.schemas.meeting_context import CandidateDate


def _build_reselect_schema(candidate_dates: list[CandidateDate]) -> type[BaseModel]:
    date_values = tuple(c.date.isoformat() for c in candidate_dates)
    chosen_date_type = Literal[date_values] | None  # type: ignore[valid-type]

    return create_model(
        "_DateReselection",
        chosen_date=(chosen_date_type, ...),
        reply=(str, ...),
    )


async def reselect_date(state: ContextChatState) -> dict:
    candidate_dates = state["candidate_dates"]
    schema = _build_reselect_schema(candidate_dates)
    llm = get_llm().with_structured_output(schema)

    history = state.get("history", [])
    transcript = "\n".join(f"{turn.role.value}: {turn.content}" for turn in history)
    candidates_text = ", ".join(c.date.isoformat() for c in candidate_dates)

    user = (
        f"## 지금까지 대화\n{transcript}\n\n"
        f"## 고를 수 있는 날짜 후보\n{candidates_text}\n\n"
        f"## 이번 발화\n{state['message']}"
    )
    result = await llm.ainvoke(
        [
            {"role": "system", "content": DATE_RESELECT_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
    )
    record_debug("n2_date_reselector", result)  # TEMP DEBUG

    if result.chosen_date is None:
        return {"reply": result.reply, "candidate_dates": candidate_dates}

    updated = [
        CandidateDate(date=c.date, selected=(c.date.isoformat() == result.chosen_date))
        for c in candidate_dates
    ]
    return {"reply": result.reply, "candidate_dates": updated}
