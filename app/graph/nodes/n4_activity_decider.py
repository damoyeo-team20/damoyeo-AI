"""N4 Activity Decider.

선호·모임 맥락·확정 슬롯을 종합해 활동 후보와 장소 검색어를 결정한다.
candidates 그래프의 진입 노드.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.graph.state import ActivityPlan, CandidatesState
from app.prompts.n4_activity_decider import SYSTEM_PROMPT
from app.schemas.candidates import ConflictInfo, ExcludedActivity


class _ActivityDraft(BaseModel):
    activity: str
    search_queries: list[str] = Field(default_factory=list)
    rationale_group: str


class _ExcludedDraft(BaseModel):
    activity: str
    reason: str


class _ActivityDecision(BaseModel):
    status: Literal["OK", "CONFLICT"]
    activities: list[_ActivityDraft] = Field(default_factory=list)
    excluded: list[_ExcludedDraft] = Field(default_factory=list)
    conflict_reason: str | None = None
    conflicting_preferences: list[str] = Field(default_factory=list)


async def decide_activities(state: CandidatesState) -> dict:
    llm = get_llm().with_structured_output(_ActivityDecision)

    system = SYSTEM_PROMPT.format(
        meeting_context=state.get("meeting_context", {}),
        confirmed_slot=state["confirmed_slot"].model_dump(by_alias=True),
        region=state["region"],
        blocked_domains=state.get("blocked_domains", []),
        participant_preferences=[
            p.model_dump(by_alias=True) for p in state.get("participant_preferences", [])
        ],
    )

    result: _ActivityDecision = await llm.ainvoke(
        [{"role": "system", "content": system}, {"role": "user", "content": "활동을 결정해줘."}]
    )

    excluded = [ExcludedActivity(activity=e.activity, reason=e.reason) for e in result.excluded]

    if result.status == "CONFLICT":
        return {
            "conflict": ConflictInfo(
                reason=result.conflict_reason or "주최자 요청과 참여자 선호가 충돌합니다.",
                host_request=state.get("meeting_context", {}).get("notes", "") or "",
                conflicting_preferences=result.conflicting_preferences,
            ),
            "activities": [],
            "excluded": excluded,
        }

    activities: list[ActivityPlan] = [
        {
            "activity": a.activity,
            "search_queries": a.search_queries,
            "rationale_group": a.rationale_group,
        }
        for a in result.activities
    ]
    return {"activities": activities, "excluded": excluded, "conflict": None}
