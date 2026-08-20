from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Preference Extractor
# 필드 정의는 docs/ai-part-proposal.md 6장(Preference 저장 & Vocabulary 연동 최종 계약) 기준.


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


class MappingType(str, Enum):
    EXACT = "EXACT"
    GENERALIZED = "GENERALIZED"
    # 대응되는 Vocabulary code가 없음. Back은 일반 선호 DB·Front 응답에서 제외한다.
    UNMAPPED = "UNMAPPED"


class Strength(str, Enum):
    """LLM에게 연속값을 시키지 않고 3단계로만 응답받는다. 수치 변환이 필요하면 저장 주체(Back)가 한다.

    값 이름은 `db_schema.md`의 `user_preferences.strength`를 그대로 따른다.
    """

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class PreferenceExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # 온보딩에서 이번 제출에 선택하거나 직접 입력한 문장들을 담는 배열.
    # 전체 채팅 이력을 뜻하지 않으며, 사용자 식별과 저장은 Back이 담당한다.
    # 구분자를 정하는 건 AI 쪽 책임이라 Back이 join할 필요 없이 원문 그대로 보내면 된다.
    messages: list[str] = Field(min_length=1)

    @field_validator("messages")
    @classmethod
    def _reject_all_blank(cls, messages: list[str]) -> list[str]:
        """Back이 걸러줄 걸 기대하지 않고, 공백뿐인 배열은 이 경계에서도 막는다."""
        if not any(m.strip() for m in messages):
            raise ValueError("messages에 공백이 아닌 문장이 하나 이상 있어야 합니다.")
        return messages


class ExtractedPreference(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # UNMAPPED일 때만 null.
    vocabulary_code: str | None = Field(alias="vocabularyCode")
    # LLM 산출값이 아니다. 매핑된 vocabularyCode로 캐시에서 조회해 AI 서버가 붙인다.
    # UNMAPPED일 때는 조회할 코드가 없으므로 둘 다 null이다.
    display_name: str | None = Field(alias="displayName")
    domain: str | None
    raw_value: str = Field(alias="rawValue")
    sentiment: Sentiment
    strength: Strength
    mapping_type: MappingType = Field(alias="mappingType")


class PreferenceExtractResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    extracted_preferences: list[ExtractedPreference] = Field(
        default_factory=list, alias="extractedPreferences"
    )
    # 정상 선호 입력이면 고정 완료 문구, 범위 밖 입력이면 선호 입력 안내를 반환한다.
    reply: str | None = None
