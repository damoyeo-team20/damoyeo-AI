"""`/ai/meetings/{meetingId}/candidates`가 실행하는 N4 -> L5 -> N6 -> N7 파이프라인의 상태.

README/ai-part-proposal.md의 MeetingState 전체 중 이 4개 노드가 필요로 하는 부분만 다룬다.
L3(시간 교집합)와 L9(캘린더 등록)는 이 저장소의 담당 범위가 아니다.
"""

from typing import TypedDict

from app.schemas.candidates import Candidate, ConfirmedSlot, ConflictInfo, ExcludedActivity, ParticipantPreference


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


class VerifiedPlace(TypedDict):
    activity: str
    kakao_place_id: str
    name: str
    address: str
    category: str
    verification_status: str
    verification_evidence: str | None
    verification_source: str | None
    verification_confidence: float | None


class CandidatesState(TypedDict, total=False):
    # 입력
    confirmed_slot: ConfirmedSlot
    region: str
    meeting_context: dict
    participant_preferences: list[ParticipantPreference]
    blocked_domains: list[str]

    # N4 산출물
    activities: list[ActivityPlan]
    excluded: list[ExcludedActivity]
    conflict: ConflictInfo | None

    # L5 산출물
    place_candidates: list[PlaceCandidate]

    # N6 산출물
    verified_places: list[VerifiedPlace]
    verification_timed_out: bool

    # N7 산출물
    final_candidates: list[Candidate]
