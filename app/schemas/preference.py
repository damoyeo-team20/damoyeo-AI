from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# N1 Preference Extractor
# 필드 정의는 docs/ai-part-proposal.md 6장(Preference 저장 & Vocabulary 연동 최종 계약) 기준.


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


class MappingType(str, Enum):
    EXACT = "EXACT"
    GENERALIZED = "GENERALIZED"
    # 대응되는 Vocabulary code가 없음. vocabularyCode는 null. 장기 저장 여부는 Back이 결정.
    UNMAPPED = "UNMAPPED"


class Strength(str, Enum):
    """LLM에게 연속값을 시키지 않고 3단계로만 응답받는다. 수치 변환이 필요하면 저장 주체(Back)가 한다."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PreferenceExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    message: str
    conversation_id: str | None = Field(default=None, alias="conversationId")


class ExtractedPreference(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # UNMAPPED일 때만 null.
    vocabulary_code: str | None = Field(alias="vocabularyCode")
    raw_value: str = Field(alias="rawValue")
    sentiment: Sentiment
    strength: Strength
    mapping_type: MappingType = Field(alias="mappingType")


class PreferenceExtractResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    preferences: list[ExtractedPreference] = Field(default_factory=list)
    # 선호와 무관한 잡담이 섞였을 때만 non-null (기획서에는 없는 필드지만, 온보딩 대화 UX를 위해 유지).
    assistant_reply: str | None = Field(default=None, alias="assistantReply")
