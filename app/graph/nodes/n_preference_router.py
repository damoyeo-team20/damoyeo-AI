"""Preference Scope Router.

사용자 입력이 개인 선호 화면의 범위 안인지 판별한다. 선호를 직접 추출하거나 사용자 답변을
만들지는 않는다.
"""

from typing import Literal

from pydantic import BaseModel

from app.core.debug import record_debug  # TEMP DEBUG
from app.core.llm import get_llm
from app.graph.preference_state import PreferenceState
from app.prompts.n_preference_router import SYSTEM_PROMPT, USER_TEMPLATE


class _RouteResult(BaseModel):
    route: Literal["IN_SCOPE", "OUT_OF_SCOPE"]


async def route_message(state: PreferenceState) -> dict:
    llm = get_llm().with_structured_output(_RouteResult)
    user = USER_TEMPLATE.format(message=state["message"])

    result: _RouteResult = await llm.ainvoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
    )
    record_debug("n_preference_router", result)  # TEMP DEBUG

    return {"route": result.route}
