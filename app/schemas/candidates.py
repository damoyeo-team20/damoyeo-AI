from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# 노드 4개에 대응 (활동 결정 + 장소 검색 + 영업 검증 + 랭킹)
# N4 Activity Decider -> L5 Kakao 검색 -> N6 Research Sub-Agent -> N7 Ranker & Explainer
# 필드는 ai-part-proposal.md 5장의 노드별 I/O 기준으로 확장됨.


class ConfirmedSlot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    start_time: str = Field(alias="startTime")
    end_time: str = Field(alias="endTime")


class ParticipantPreference(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    vocabulary_code: str = Field(alias="vocabularyCode")
    sentiment: str
    strength: float


class CandidatesRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    confirmed_slot: ConfirmedSlot = Field(alias="confirmedSlot")
    region: str
    meeting_context: dict = Field(default_factory=dict, alias="meetingContext")
    participant_preferences: list[ParticipantPreference] = Field(
        default_factory=list, alias="participantPreferences"
    )
    # 호불호가 크게 갈리는 장소 유형(PC방 등)은 참여자/주최자가 먼저 언급하기 전까지 후보에서 제외한다.
    blocked_domains: list[str] = Field(default_factory=list, alias="blockedDomains")


class CandidatesStatus(str, Enum):
    OK = "OK"
    CONFLICT = "CONFLICT"


class VerificationStatus(str, Enum):
    """PASS/FAIL/UNKNOWN 3-state. FAIL은 후보에서 제외, UNKNOWN은 표시만 하고 후보에는 포함한다."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Verification(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: VerificationStatus
    # 판정 근거가 된 검색 결과 요약.
    evidence: str | None = None
    # 근거로 삼은 출처(URL 등).
    source: str | None = None
    # 판정 확신도 0.0~1.0. 확신할 수 없으면 status 자체를 UNKNOWN으로 둔다.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class Place(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kakao_place_id: str = Field(alias="kakaoPlaceId")
    name: str
    address: str
    category: str


class Candidate(BaseModel):
    activity: str  # N4 산출물
    place: Place  # L5 산출물
    verification: Verification  # N6 산출물
    # 추천 사유는 항상 집단 수준 표현만 사용한다 ("참여자 선호와 높은 적합도" O, 특정 참여자 지칭 X).
    rationale: str  # N7 산출물


class ExcludedActivity(BaseModel):
    """N4가 고려했지만 제외한 활동 유형. 디버깅/시연 투명성을 위해 노출."""

    activity: str
    reason: str


class ConflictInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str
    host_request: str = Field(alias="hostRequest")
    conflicting_preferences: list[str] = Field(default_factory=list, alias="conflictingPreferences")


class CandidatesResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: CandidatesStatus
    candidates: list[Candidate] = Field(default_factory=list)
    excluded: list[ExcludedActivity] = Field(default_factory=list)
    conflict: ConflictInfo | None = None
    verification_timed_out: bool = Field(default=False, alias="verificationTimedOut")
