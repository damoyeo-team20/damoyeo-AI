"""N8 Revision Router.

재탐색 피드백을 어느 단계부터 재실행할지 판단한다. LLM은 라우팅 판단만 하고,
실제 재실행(해당 노드부터 파이프라인을 다시 호출하는 것)은 오케스트레이터(Back)의 책임이다.
`POST /ai/meetings/{meetingId}/revise`가 호출한다.
"""

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.prompts.n8_revision_router import SYSTEM_PROMPT, USER_TEMPLATE
from app.schemas.revise import RerouteTarget, ReviseResponse


class _ReviseDecision(BaseModel):
    reroute_to: RerouteTarget
    added_constraints: list[str] = Field(default_factory=list)
    message: str


async def route_revision(feedback: str, current_candidates: list[dict]) -> ReviseResponse:
    llm = get_llm().with_structured_output(_ReviseDecision)
    system = SYSTEM_PROMPT.format(current_candidates=current_candidates)
    user = USER_TEMPLATE.format(feedback=feedback)

    result: _ReviseDecision = await llm.ainvoke(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )

    return ReviseResponse(
        reroute_to=result.reroute_to,
        added_constraints=result.added_constraints,
        message=result.message,
    )
