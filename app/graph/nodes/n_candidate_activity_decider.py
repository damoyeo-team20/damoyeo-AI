"""Candidate Activity Decider.

모임 목적과 참여자 선호를 종합해 무슨 활동을 할지, 이번 자리의 성격 태그, 전체 설명 문장을
결정한다. candidates 그래프의 진입 노드.

날짜·시간은 이미 `/schedule`(Schedule Resolver)이 확정한 뒤 넘어오므로 이 노드는 관여하지
않는다 — 확정된 시간은 활동을 고르는 참고 맥락으로만 쓰인다.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.debug import record_debug  # TEMP DEBUG
from app.core.llm import get_llm
from app.graph.state import ActivityPlan, CandidatesState
from app.prompts.n_candidate_activity_decider import SYSTEM_PROMPT
from app.schemas.candidates import ActionRequired, ActionRequiredType, MeetingTag, to_meeting_tag


class _ActivityDraft(BaseModel):
    activity: str
    search_queries: list[str] = Field(default_factory=list)
    rationale_group: str


class _ActivityDecision(BaseModel):
    status: Literal["OK", "CONFLICT"]
    activities: list[_ActivityDraft] = Field(default_factory=list)
    # 확실히 해당하는 것만 담는다. 근거가 없으면 빈 배열이 정상 — 억지로 채우지 않는다.
    meeting_tags: list[MeetingTag] = Field(default_factory=list)
    summary: str = ""
    conflict_reason: str | None = None
    conflicting_preferences: list[str] = Field(default_factory=list)


async def decide_activities(state: CandidatesState) -> dict:
    meeting = state["meeting"]
    confirmed_slot = state["confirmed_slot"]

    llm = get_llm().with_structured_output(_ActivityDecision)
    system = SYSTEM_PROMPT.format(
        purpose=meeting.purpose,
        confirmed_slot=confirmed_slot.model_dump(by_alias=True, mode="json"),
        region=meeting.region,
        meeting_memory_summary=state.get("meeting_memory_summary") or "(없음)",
        participant_preferences=[
            p.model_dump(by_alias=True) for p in state.get("participant_preferences", [])
        ],
    )

    result: _ActivityDecision = await llm.ainvoke(
        [{"role": "system", "content": system}, {"role": "user", "content": "활동을 결정해줘."}]
    )
    record_debug("n_candidate_activity_decider", result)  # TEMP DEBUG

    if result.status == "CONFLICT":
        return {
            "action_required": ActionRequired(
                type=ActionRequiredType.PREFERENCE_CONFLICT,
                message=result.conflict_reason or "모임 목적과 참여자 선호가 충돌합니다.",
                host_request=meeting.purpose,
                conflicting_preference_codes=result.conflicting_preferences,
            ),
            "activities": [],
            "meeting_tags": [],
        }

    # dict.fromkeys로 순서를 지키면서 중복만 제거한다.
    meeting_tags = [to_meeting_tag(t) for t in dict.fromkeys(result.meeting_tags)]

    activities: list[ActivityPlan] = [
        {
            "activity": a.activity,
            "search_queries": a.search_queries,
            "rationale_group": a.rationale_group,
        }
        for a in result.activities
    ]
    return {
        "activities": activities,
        "action_required": None,
        "meeting_tags": meeting_tags,
        "summary": result.summary,
    }
