from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# N8 Revision Router
# ai-part-proposal.md 5장: {revise: "place_only|activity|time", added_constraints[]}
# added_constraints는 MeetingState.revision_history[]에 누적되는 제약 목록이다.


class ReviseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    feedback: str
    current_candidates: list[dict] = Field(default_factory=list, alias="currentCandidates")


class RerouteTarget(str, Enum):
    """LLM은 라우팅 판단만 하고, 실제 재실행은 오케스트레이터(Back)가 수행한다."""

    TIME = "TIME"
    ACTIVITY = "ACTIVITY"
    PLACE = "PLACE"


class ReviseResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reroute_to: RerouteTarget = Field(alias="rerouteTo")
    # 이번 피드백으로 새로 추가된 제약. revision_history에 누적되는 것을 전제로 "추가분"만 반환한다.
    added_constraints: list[str] = Field(default_factory=list, alias="addedConstraints")
    message: str
