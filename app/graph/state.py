"""`/ai/meetings/{meetingId}/candidates`가 실행하는
Activity Decider -> Place Search -> Place Verifier -> Ranker 파이프라인의 상태.

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


class ActivityPlan(TypedDict):
    activity: str
    search_queries: list[str]
    # 집단 수준 표현으로 "왜 이 활동 유형을 골랐는지"를 설명. 개인 지칭 금지.
    rationale_group: str


class PlaceCandidate(TypedDict):
    activity: str
    kakao_place_id: str
    name: str
    address: str
    category: str
    place_url: str | None
    latitude: float | None
    longitude: float | None


class VerifiedPlace(TypedDict):
    activity: str
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
    activities: list[ActivityPlan]
    action_required: ActionRequired | None
    meeting_tags: list[Tag]
    summary: str

    # Place Search 산출물
    place_candidates: list[PlaceCandidate]

    # Place Verifier 산출물
    verified_places: list[VerifiedPlace]
    verification_timed_out: bool

    # Ranker 산출물
    suggestions: list[Suggestion]
