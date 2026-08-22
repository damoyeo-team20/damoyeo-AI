"""`/ai/meetings/{meetingId}/candidates`가 실행하는 후보 생성 파이프라인의 상태.

SearchPlan 생성 -> Place Search -> Context/Fairness Pre-Ranker -> Place Verifier ->
Suggestion Builder 순서로 내부 상태를 전달한다.

날짜·시간 확정(Schedule Resolver)은 `/schedule` 별도 엔드포인트가 담당하고, 이 그래프는 이미
확정된 `confirmed_slot`을 받아서 그 시각에 맞는 장소만 찾는다.
"""

from datetime import datetime
from typing import TypedDict

from app.schemas.candidates import (
    ActionRequired,
    ConfirmedSlot,
    MeetingInput,
    ParticipantInput,
    Suggestion,
    Tag,
)


class SearchPlan(TypedDict):
    """LLM이 제안하고 서버가 제한·정규화한 내부 장소 검색 계획."""

    # 기존에는 activity라고 불렀지만 실제 역할은 Kakao 검색 버킷에 가깝다.
    label: str
    source: str
    search_queries: list[str]
    # 집단 수준 표현으로 "왜 이 검색 계획을 만들었는지"를 설명. 개인 지칭 금지.
    rationale_group: str


class PlaceCandidate(TypedDict):
    search_plan_label: str
    search_plan_source: str
    search_plan_rationale: str
    kakao_place_id: str
    name: str
    address: str
    category: str
    place_url: str | None
    latitude: float | None
    longitude: float | None


class VerifiedPlace(TypedDict):
    search_plan_label: str
    search_plan_source: str
    search_plan_rationale: str
    kakao_place_id: str
    name: str
    address: str
    category: str
    place_url: str | None
    latitude: float | None
    longitude: float | None
    verification_status: str
    # 검증으로 확인한 실제 영업시간 문구. 확인 못 했으면 None.
    business_hours: str | None
    verification_source: str | None
    checked_at: datetime


class RankedCandidate(TypedDict):
    """영업 검증 전에 컨텍스트 적합성과 참여자 공정성으로 정렬된 후보."""

    place: PlaceCandidate
    context_relation: str
    participant_satisfaction: dict[int, float]
    group_satisfaction: float
    minimum_satisfaction: float
    fairness_score: float
    matched_preference_codes: list[str]
    reasons: list[str]
    tags: list[str]
    original_index: int


class CandidatesState(TypedDict, total=False):
    # 입력
    meeting: MeetingInput
    confirmed_slot: ConfirmedSlot
    # Back이 보낸 참여자별 선호 구조를 그대로 유지한다. 공정성 계산 전까지 userId 경계를
    # 잃으면 개인 만족도와 최저 만족도를 계산할 수 없다.
    participants: list[ParticipantInput]
    meeting_memory_summary: str | None
    excluded_external_place_ids: list[str]

    # Activity Decider 산출물
    search_plans: list[SearchPlan]
    action_required: ActionRequired | None
    meeting_tags: list[Tag]
    summary: str

    # Place Search 산출물
    place_candidates: list[PlaceCandidate]
    search_metrics: dict[str, int]

    # Fairness Ranker 산출물. 이 순서대로 상위 후보부터 영업 검증한다.
    ranked_candidates: list[RankedCandidate]

    # Place Verifier 산출물
    verified_places: list[VerifiedPlace]
    verification_timed_out: bool
    verification_metrics: dict[str, int]

    # Suggestion Builder 산출물
    suggestions: list[Suggestion]
