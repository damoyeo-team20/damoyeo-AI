from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.preference import Sentiment, Strength

# `POST /ai/meetings/{meetingId}/candidates` 계약.
# 필드는 docs/api-design-backend.md 6장 기준이며, 파이프라인은
# Activity Decider -> Place Search -> Place Verifier -> Ranker이다.
#
# 날짜/시각 확정은 이 API의 일이 아니다 — `POST /ai/meetings/{meetingId}/schedule`(Schedule
# Resolver)이 먼저 확정한 `confirmedSlot`을 그대로 받아서 그 시각에 맞는 장소만 고른다.


class ConfirmedSlot(BaseModel):
    """`meetings.confirmed_start_at` / `confirmed_end_at`에 대응. `/schedule` 응답을 그대로 받는다."""

    model_config = ConfigDict(populate_by_name=True)

    confirmed_start_at: datetime = Field(alias="confirmedStartAt")
    confirmed_end_at: datetime = Field(alias="confirmedEndAt")

    @field_validator("confirmed_end_at")
    @classmethod
    def _end_after_start(cls, confirmed_end_at: datetime, info) -> datetime:
        start = info.data.get("confirmed_start_at")
        if start is not None and confirmed_end_at <= start:
            raise ValueError("confirmedEndAt은 confirmedStartAt보다 뒤여야 합니다.")
        return confirmed_end_at

    @property
    def date_str(self) -> str:
        return self.confirmed_start_at.date().isoformat()

    @property
    def duration_minutes(self) -> int:
        return int((self.confirmed_end_at - self.confirmed_start_at).total_seconds() // 60)


class MeetingInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # meetings.id — path의 meetingId와 일치해야 한다 (라우터에서 검증).
    id: int
    # meetings.purpose — /context가 정리한 한 문장. CONFLICT 응답의 hostRequest로 그대로 되돌려준다.
    purpose: str = Field(max_length=1000)
    region: str = Field(max_length=100)


class ParticipantPreference(BaseModel):
    """`user_preferences` 1행에 대응."""

    model_config = ConfigDict(populate_by_name=True)

    vocabulary_code: str = Field(alias="vocabularyCode")
    sentiment: Sentiment
    strength: Strength
    raw_value: str = Field(alias="rawValue", max_length=255)


class ParticipantInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # users.id (BIGINT)
    user_id: int = Field(alias="userId")
    preferences: list[ParticipantPreference] = Field(default_factory=list)


class CandidatesRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    contract_version: str = Field(alias="contractVersion")
    request_id: str = Field(alias="requestId")
    meeting: MeetingInput
    # `/schedule`이 확정한 시간. AI는 이 시간에 맞는 장소만 찾는다.
    confirmed_slot: ConfirmedSlot = Field(alias="confirmedSlot")
    participants: list[ParticipantInput] = Field(min_length=1)
    # 구조가 확정되지 않아 확장 가능한 object로 둔다. AI는 summary만 사용한다.
    meeting_memory: dict | None = Field(default=None, alias="meetingMemory")
    # 이미 보여준 장소 ID 전체. 비어 있으면 최초 생성과 동일하게 동작한다.
    excluded_external_place_ids: list[str] = Field(
        default_factory=list, alias="excludedExternalPlaceIds"
    )

    @field_validator("participants")
    @classmethod
    def _reject_duplicate_users(cls, participants: list[ParticipantInput]) -> list[ParticipantInput]:
        user_ids = [p.user_id for p in participants]
        if len(set(user_ids)) != len(user_ids):
            raise ValueError("participants에 중복된 userId가 있습니다.")
        for participant in participants:
            codes = [pref.vocabulary_code for pref in participant.preferences]
            if len(set(codes)) != len(codes):
                raise ValueError(
                    f"userId={participant.user_id}의 선호에 중복된 vocabularyCode가 있습니다."
                )
        return participants

    @field_validator("excluded_external_place_ids")
    @classmethod
    def _reject_duplicate_excluded(cls, place_ids: list[str]) -> list[str]:
        if len(set(place_ids)) != len(place_ids):
            raise ValueError("excludedExternalPlaceIds에 중복된 ID가 있습니다.")
        return place_ids


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

    Ranker가 실제로 받는 정보(활동 유형, 장소명, 카테고리, 모임 목적)로 판단 가능한 것만 둔다.
    근거가 없는 태그를 목록에 넣으면 LLM이 아무 후보에나 붙인다 — 예산 관련 태그를 뺀 이유다
    (Kakao 응답에 가격 정보가 없어 판단할 근거 자체가 없음).

    AVAILABLE_AT_MEETING_TIME은 LLM이 고르지 않는다 — 영업 검증(Place Verifier) 결과에서 코드로 파생한다.
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
    NO_CANDIDATE = "NO_CANDIDATE"
    CONFLICT = "CONFLICT"


class ActionRequiredType(str, Enum):
    NO_CANDIDATE = "NO_CANDIDATE"
    PREFERENCE_CONFLICT = "PREFERENCE_CONFLICT"


class ActionRequired(BaseModel):
    """사용자 결정이 필요한 상태. 시스템 오류가 아니므로 HTTP 200으로 반환한다."""

    model_config = ConfigDict(populate_by_name=True)

    type: ActionRequiredType
    message: str
    # PREFERENCE_CONFLICT일 때만 채운다.
    host_request: str | None = Field(default=None, alias="hostRequest")
    conflicting_preference_codes: list[str] | None = Field(
        default=None, alias="conflictingPreferenceCodes"
    )


class PlaceProvider(str, Enum):
    KAKAO = "KAKAO"


class Suggestion(BaseModel):
    """시간과 장소가 결합된 제안 하나. 모든 제안은 요청의 confirmedSlot을 그대로 쓴다."""

    model_config = ConfigDict(populate_by_name=True)

    rank: int
    category: str
    place_provider: PlaceProvider = Field(default=PlaceProvider.KAKAO, alias="placeProvider")
    external_place_id: str = Field(alias="externalPlaceId")
    name: str
    address: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    external_url: str | None = Field(default=None, alias="externalUrl")
    proposed_start_at: datetime = Field(alias="proposedStartAt")
    proposed_end_at: datetime = Field(alias="proposedEndAt")
    # 검증으로 확인한 실제 영업시간 문구. 확인하지 못했으면 null.
    business_hours: str | None = Field(default=None, alias="businessHours")
    business_hours_verified: bool = Field(default=False, alias="businessHoursVerified")
    # 제안 시각에 영업하는지. 확인하지 못했으면 null (임의로 true/false로 단정하지 않는다).
    open_at_meeting_time: bool | None = Field(default=None, alias="openAtMeetingTime")
    # 선정에 기여한 Vocabulary domain. LLM이 고른 코드를 서버가 domain으로 변환한 값이다.
    matched_preference_domains: list[str] = Field(
        default_factory=list, alias="matchedPreferenceDomains"
    )
    # 그룹 수준 표현만 사용한다 ("참여자 선호와 높은 적합도" O, 특정 참여자 지칭 X).
    reasons: list[str] = Field(default_factory=list)
    # 짧은 배지용. 태그로 담기지 않는 뉘앙스는 reasons 문장이 받는다.
    tags: list[Tag] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list, alias="sourceUrls")
    checked_at: datetime | None = Field(default=None, alias="checkedAt")


class CandidatesResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(alias="requestId")
    status: CandidatesStatus
    applied_duration_minutes: int = Field(alias="appliedDurationMinutes")
    summary: str = ""
    # 참여자 선호를 종합한 "이런 종류의 자리" 태그. 참여자 구성이 바뀌면 함께 바뀐다.
    meeting_tags: list[Tag] = Field(default_factory=list, alias="meetingTags")
    suggestions: list[Suggestion] = Field(default_factory=list)
    action_required: ActionRequired | None = Field(default=None, alias="actionRequired")
    verification_timed_out: bool = Field(default=False, alias="verificationTimedOut")
