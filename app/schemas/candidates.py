from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.meeting_context import MeetingContext
from app.schemas.preference import Sentiment, Strength

# 노드 4개에 대응 (활동 결정 + 장소 검색 + 영업 검증 + 랭킹)
# N4 Activity Decider -> L5 Kakao 검색 -> N6 Research Sub-Agent -> N7 Ranker & Explainer
# 필드는 ai-part-proposal.md 5장의 노드별 I/O 기준으로 확장됨.


class ConfirmedSlot(BaseModel):
    """`meetings.confirmed_start_at` / `confirmed_end_at` (TIMESTAMPTZ)에 대응."""

    model_config = ConfigDict(populate_by_name=True)

    confirmed_start_at: datetime = Field(alias="confirmedStartAt")
    confirmed_end_at: datetime = Field(alias="confirmedEndAt")

    @property
    def date(self) -> str:
        """영업일 검증(N6)은 날짜 단위로만 판단하므로 시작 시각의 날짜를 쓴다."""
        return self.confirmed_start_at.date().isoformat()


class ParticipantPreference(BaseModel):
    """`user_preferences` 1행에 대응. N1이 뱉은 값이 그대로 들어오므로 타입도 동일해야 한다."""

    model_config = ConfigDict(populate_by_name=True)

    # users.id (BIGINT)
    user_id: int = Field(alias="userId")
    vocabulary_code: str = Field(alias="vocabularyCode")
    sentiment: Sentiment
    strength: Strength


class CandidatesRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    confirmed_slot: ConfirmedSlot = Field(alias="confirmedSlot")
    # meetings.region
    region: str
    # meetings.purpose — 주최자가 남긴 이번 모임 목적 원문. CONFLICT 응답의 hostRequest로 그대로 되돌려준다.
    purpose: str | None = None
    meeting_context: MeetingContext = Field(
        default_factory=MeetingContext, alias="meetingContext"
    )
    participant_preferences: list[ParticipantPreference] = Field(
        default_factory=list, alias="participantPreferences"
    )
    # 호불호가 크게 갈리는 장소 유형(PC방 등)은 참여자/주최자가 먼저 언급하기 전까지 후보에서 제외한다.
    blocked_domains: list[str] = Field(default_factory=list, alias="blockedDomains")


class MeetingTag(str, Enum):
    """참여자 선호를 종합했을 때 이번 모임이 "어떤 종류의 자리"인지 (모임 전체 수준).

    네 개의 독립된 축으로 구성한다. 축을 섞으면 대응 관계가 무너져 LLM이 중복·모순 태그를 고르게 된다.
      - 무엇을 하는가 : ACTIVE <-> CONVERSATION_FOCUSED
      - 먹고 마시기   : MEAL_INCLUDED(독립) / ALCOHOL_FRIENDLY <-> NO_ALCOHOL
      - 분위기        : LIVELY <-> QUIET
      - 예산          : BUDGET_FRIENDLY

    enum 이름과 아래 라벨은 LLM의 판단 근거가 되므로 의미가 드러나게 짓는다.
    """

    # 무엇을 하는 자리인가
    ACTIVE = "ACTIVE"
    CONVERSATION_FOCUSED = "CONVERSATION_FOCUSED"
    # 먹고 마시기
    MEAL_INCLUDED = "MEAL_INCLUDED"
    ALCOHOL_FRIENDLY = "ALCOHOL_FRIENDLY"
    NO_ALCOHOL = "NO_ALCOHOL"
    # 분위기
    LIVELY = "LIVELY"
    QUIET = "QUIET"
    # 예산
    BUDGET_FRIENDLY = "BUDGET_FRIENDLY"


class CandidateTag(str, Enum):
    """개별 장소를 추천한 이유 (후보 수준).

    N7이 실제로 받는 정보(활동 유형, 장소명, 카테고리, 모임 맥락)로 판단 가능한 것만 둔다.
    근거가 없는 태그를 목록에 넣으면 LLM이 아무 후보에나 붙인다 — 예산 관련 태그를 뺀 이유다
    (Kakao 응답에 가격 정보가 없어 판단할 근거 자체가 없음).

    AVAILABLE_AT_MEETING_TIME은 LLM이 고르지 않는다 — 영업 검증(N6) 결과에서 코드로 파생한다.
    사실 판정이라 LLM이 지어내면 거짓 정보가 되기 때문.
    """

    MATCHES_ACTIVITY = "MATCHES_ACTIVITY"
    HIGH_GROUP_FIT = "HIGH_GROUP_FIT"
    GOOD_FOR_MEAL = "GOOD_FOR_MEAL"
    GOOD_FOR_DRINKS = "GOOD_FOR_DRINKS"
    AVAILABLE_AT_MEETING_TIME = "AVAILABLE_AT_MEETING_TIME"


# 표시 문구는 LLM이 아니라 서버가 붙인다. LLM이 만들면 매번 표현이 흔들려 프론트에서 매핑할 수 없다.
MEETING_TAG_LABELS: dict[MeetingTag, str] = {
    MeetingTag.ACTIVE: "활동형",
    MeetingTag.CONVERSATION_FOCUSED: "대화 중심",
    MeetingTag.MEAL_INCLUDED: "식사 겸용",
    MeetingTag.ALCOHOL_FRIENDLY: "술 가능",
    MeetingTag.NO_ALCOHOL: "술 없이",
    MeetingTag.LIVELY: "왁자지껄",
    MeetingTag.QUIET: "차분한",
    MeetingTag.BUDGET_FRIENDLY: "가성비",
}

CANDIDATE_TAG_LABELS: dict[CandidateTag, str] = {
    # "활동형"(MeetingTag.ACTIVE)과 혼동되지 않게 — 카페 모임이면 카페에도 붙는 태그다.
    CandidateTag.MATCHES_ACTIVITY: "정한 활동에 적합",
    CandidateTag.HIGH_GROUP_FIT: "그룹 선호와 적합도 높음",
    CandidateTag.GOOD_FOR_MEAL: "식사하기 좋음",
    CandidateTag.GOOD_FOR_DRINKS: "술자리 적합",
    CandidateTag.AVAILABLE_AT_MEETING_TIME: "모임 시간에 이용 가능",
}


class Tag(BaseModel):
    """프론트가 별도 매핑 테이블 없이 그대로 렌더링할 수 있도록 코드와 표시 문구를 함께 내린다."""

    code: str
    label: str


def to_meeting_tag(code: MeetingTag) -> Tag:
    return Tag(code=code.value, label=MEETING_TAG_LABELS[code])


def to_candidate_tag(code: CandidateTag) -> Tag:
    return Tag(code=code.value, label=CANDIDATE_TAG_LABELS[code])


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
    # Kakao 장소 상세페이지 URL (가격·사진·리뷰 보기 링크로 사용).
    place_url: str | None = Field(default=None, alias="placeUrl")


class Candidate(BaseModel):
    activity: str  # N4 산출물
    place: Place  # L5 산출물
    verification: Verification  # N6 산출물
    # 추천 사유는 항상 집단 수준 표현만 사용한다 ("참여자 선호와 높은 적합도" O, 특정 참여자 지칭 X).
    rationale: str  # N7 산출물
    # 짧은 배지용. 태그로 담기지 않는 뉘앙스는 위 rationale 문장이 받는다.
    tags: list[Tag] = Field(default_factory=list)


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
    # 참여자 선호를 종합한 "이런 종류의 자리" 태그. 참여자 구성이 바뀌면 함께 바뀐다.
    meeting_tags: list[Tag] = Field(default_factory=list, alias="meetingTags")
    candidates: list[Candidate] = Field(default_factory=list)
    excluded: list[ExcludedActivity] = Field(default_factory=list)
    conflict: ConflictInfo | None = None
    verification_timed_out: bool = Field(default=False, alias="verificationTimedOut")
