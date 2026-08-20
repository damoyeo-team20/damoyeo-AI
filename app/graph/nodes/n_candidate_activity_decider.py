"""Candidate Activity Decider.

모임 목적과 참여자 선호를 종합해 후보 풀을 넓힐 SearchPlan, 이번 자리의 성격 태그,
전체 설명 문장을 결정한다. SearchPlan은 최종 활동 확정값이 아니라 Kakao 검색용 내부 계획이다.
candidates 그래프의 진입 노드.

날짜·시간은 이미 `/schedule`(Schedule Resolver)이 확정한 뒤 넘어오므로 이 노드는 관여하지
않는다 — 확정된 시간은 활동을 고르는 참고 맥락으로만 쓰인다.
"""

from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.core.debug import record_debug  # TEMP DEBUG
from app.core.errors import AIServiceError
from app.core.llm import get_llm
from app.graph.state import CandidatesState, SearchPlan
from app.prompts.n_candidate_activity_decider import SYSTEM_PROMPT
from app.schemas.candidates import ActionRequired, ActionRequiredType, MeetingTag, to_meeting_tag

_MEETING_TIMEZONE = ZoneInfo("Asia/Seoul")
_EXCLUSIVE_MEETING_TAG_AXES = (
    {MeetingTag.ACTIVE, MeetingTag.CONVERSATION_FOCUSED},
    {MeetingTag.ALCOHOL_FRIENDLY, MeetingTag.NO_ALCOHOL},
    {MeetingTag.LIVELY, MeetingTag.QUIET},
)
_SEARCH_PLAN_SOURCE_PRIORITY = {
    "MEETING_PURPOSE": 0,
    "PARTICIPANT_PREFERENCE": 1,
    "MEETING_MEMORY": 2,
}


def _invalid_model_result(message: str) -> AIServiceError:
    return AIServiceError(
        code="MODEL_RESPONSE_INVALID",
        message=message,
        status_code=502,
        retryable=True,
    )


class _ActivityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity: str = Field(min_length=1, max_length=100)
    source: Literal["MEETING_PURPOSE", "PARTICIPANT_PREFERENCE", "MEETING_MEMORY"]
    search_queries: list[str] = Field(min_length=1, max_length=3)
    rationale_group: str = Field(min_length=1, max_length=500)

    @field_validator("activity", "rationale_group")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("검색 계획의 이름과 근거에는 공백뿐인 값을 넣을 수 없습니다.")
        return normalized

    @field_validator("search_queries")
    @classmethod
    def _normalize_queries(cls, queries: list[str]) -> list[str]:
        normalized = [" ".join(query.split()) for query in queries]
        if any(not query for query in normalized):
            raise ValueError("searchQueries에는 공백뿐인 검색어를 넣을 수 없습니다.")
        if len({query.casefold() for query in normalized}) != len(normalized):
            raise ValueError("하나의 검색 계획에 중복된 searchQuery가 있습니다.")
        return normalized


class _ActivityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["OK", "CONFLICT"]
    activities: list[_ActivityDraft] = Field(default_factory=list, max_length=4)
    # 확실히 해당하는 것만 담는다. 근거가 없으면 빈 배열이 정상 — 억지로 채우지 않는다.
    meeting_tags: list[MeetingTag] = Field(default_factory=list)
    summary: str = ""
    conflict_reason: str | None = None
    conflicting_preferences: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_search_plan_policy(self) -> "_ActivityDecision":
        selected_tags = set(self.meeting_tags)
        if any(len(selected_tags & axis) > 1 for axis in _EXCLUSIVE_MEETING_TAG_AXES):
            raise ValueError("동일한 의미 축의 상반된 meetingTag를 함께 선택할 수 없습니다.")

        if self.status == "CONFLICT":
            if self.activities:
                raise ValueError("CONFLICT일 때 activities는 비어 있어야 합니다.")
            return self

        if not self.activities:
            raise ValueError("OK일 때 검색 계획이 최소 1개 필요합니다.")
        labels = [activity.activity.casefold() for activity in self.activities]
        if len(set(labels)) != len(labels):
            raise ValueError("중복된 활동 검색 계획을 만들 수 없습니다.")

        sources = [activity.source for activity in self.activities]
        if "MEETING_PURPOSE" not in sources:
            raise ValueError("모임 목적에서 나온 검색 계획이 최소 1개 필요합니다.")
        if sources.count("PARTICIPANT_PREFERENCE") > 2:
            raise ValueError("참여자 선호 기반 검색 계획은 최대 2개입니다.")
        if sources.count("MEETING_MEMORY") > 1:
            raise ValueError("모임 메모리 기반 검색 계획은 최대 1개입니다.")
        return self


def _without_region_prefix(query: str, region: str) -> str:
    """Kakao 클라이언트가 지역을 한 번 붙이므로 LLM 검색어의 중복 지역 접두사를 제거한다."""

    normalized_query = " ".join(query.split())
    normalized_region = " ".join(region.split())
    while normalized_query.casefold().startswith(f"{normalized_region.casefold()} "):
        normalized_query = normalized_query[len(normalized_region) :].strip()
    if normalized_query.casefold() == normalized_region.casefold():
        return ""
    return normalized_query


async def decide_activities(state: CandidatesState) -> dict:
    meeting = state["meeting"]
    confirmed_slot = state["confirmed_slot"]
    # Back이 UTC(`Z`)로 보낸 같은 시점도 활동 선택 프롬프트에서는 한국 현지 시각으로 보인다.
    local_confirmed_slot = {
        "confirmedStartAt": confirmed_slot.confirmed_start_at.astimezone(
            _MEETING_TIMEZONE
        ).isoformat(),
        "confirmedEndAt": confirmed_slot.confirmed_end_at.astimezone(
            _MEETING_TIMEZONE
        ).isoformat(),
    }

    llm = get_llm().with_structured_output(_ActivityDecision, include_raw=True)
    system = SYSTEM_PROMPT.format(
        purpose=meeting.purpose,
        confirmed_slot=local_confirmed_slot,
        region=meeting.region,
        meeting_memory_summary=state.get("meeting_memory_summary") or "(없음)",
        participants=[
            participant.model_dump(by_alias=True) for participant in state.get("participants", [])
        ],
    )

    try:
        structured_result = await llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "활동을 결정해줘."},
            ]
        )
    except ValidationError as exc:
        raise _invalid_model_result("모델 구조화 응답 검증에 실패했습니다.") from exc

    if not isinstance(structured_result, dict):
        raise _invalid_model_result("모델 구조화 응답 검증에 실패했습니다.")
    parsing_error = structured_result.get("parsing_error")
    result = structured_result.get("parsed")
    if parsing_error is not None or not isinstance(result, _ActivityDecision):
        error = _invalid_model_result("모델 구조화 응답 검증에 실패했습니다.")
        if isinstance(parsing_error, BaseException):
            raise error from parsing_error
        raise error
    record_debug("n_candidate_activity_decider", result)  # TEMP DEBUG

    if result.status == "CONFLICT":
        return {
            "action_required": ActionRequired(
                type=ActionRequiredType.PREFERENCE_CONFLICT,
                message=result.conflict_reason or "모임 목적과 참여자 선호가 충돌합니다.",
                host_request=meeting.purpose,
                conflicting_preference_codes=result.conflicting_preferences,
            ),
            "search_plans": [],
            "meeting_tags": [],
        }

    # dict.fromkeys로 순서를 지키면서 중복만 제거한다.
    meeting_tags = [to_meeting_tag(t) for t in dict.fromkeys(result.meeting_tags)]

    search_plans: list[SearchPlan] = []
    for activity in result.activities:
        queries = list(
            dict.fromkeys(
                query
                for query in (
                    _without_region_prefix(query, meeting.region)
                    for query in activity.search_queries
                )
                if query
            )
        )
        if not queries:
            raise AIServiceError(
                code="MODEL_RESPONSE_INVALID",
                message="모델이 지역명만 포함된 장소 검색어를 반환했습니다.",
                status_code=502,
                retryable=True,
            )
        search_plans.append(
            {
                "label": activity.activity,
                "source": activity.source,
                "search_queries": queries,
                "rationale_group": activity.rationale_group,
            }
        )
    # 같은 장소가 여러 계획에서 검색될 때 목적 근거를 우선 보존하도록 계획 순서를 고정한다.
    search_plans.sort(key=lambda plan: _SEARCH_PLAN_SOURCE_PRIORITY[plan["source"]])
    return {
        "search_plans": search_plans,
        "action_required": None,
        "meeting_tags": meeting_tags,
        "summary": result.summary,
    }
