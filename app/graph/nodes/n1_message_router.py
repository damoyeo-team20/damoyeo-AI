"""N1 Message Router.

발화를 "선호 관련 부분"과 "잡담 부분"으로 분리한다. 이후 두 노드(추출/스몰톡)로 팬아웃하기 위한
전처리 노드 — 자체적으로 선호를 추출하거나 응답을 만들지 않는다.
"""

from pydantic import BaseModel

from app.core.llm import get_llm
from app.graph.preference_state import PreferenceState
from app.prompts.n1_message_router import SYSTEM_PROMPT, USER_TEMPLATE


class _RouteResult(BaseModel):
    preference_text: str | None = None
    smalltalk_text: str | None = None


async def route_message(state: PreferenceState) -> dict:
    llm = get_llm().with_structured_output(_RouteResult)
    user = USER_TEMPLATE.format(message=state["message"])

    result: _RouteResult = await llm.ainvoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
    )

    return {
        "preference_text": result.preference_text,
        "smalltalk_text": result.smalltalk_text,
    }
