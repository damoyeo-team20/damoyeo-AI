"""Preference Extractor.

가드레일을 통과한 입력에서 개인 선호만 골라 Vocabulary 매핑된 구조로 변환한다.
"""

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.graph.preference_state import PreferenceState
from app.prompts.n_preference_extractor import SYSTEM_PROMPT, USER_TEMPLATE
from app.schemas.preference import ExtractedPreference, MappingType, Sentiment, Strength
from app.services.vocabulary_client import VocabularyEntry, fetch_vocabulary


class _ExtractedPreferenceItem(BaseModel):
    """Gemini가 반환하는 내부 DTO.

    Vocabulary 전체를 JSON Schema enum으로 만들지 않는다. code 실존 여부와 UNMAPPED 정규화는
    응답을 받은 뒤 AI 서버가 현재 Vocabulary를 기준으로 수행한다.
    """

    vocabulary_code: str | None = Field(
        description="Vocabulary 목록의 code. 대응되는 항목이 없으면 null."
    )
    raw_value: str
    sentiment: Sentiment
    strength: Strength
    mapping_type: MappingType


class _ExtractionResult(BaseModel):
    preferences: list[_ExtractedPreferenceItem] = Field(default_factory=list)


def _format_vocabulary(vocabulary: list[VocabularyEntry]) -> str:
    lines = [
        f"- {entry.code} ({entry.display_name}, domain={entry.domain}, "
        f"parentCode={entry.parent_code})"
        for entry in vocabulary
    ]
    return "\n".join(lines) if lines else "(비어있음)"


async def extract_preferences(text: str) -> list[ExtractedPreference]:
    vocabulary = await fetch_vocabulary()
    vocabulary_by_code = {entry.code: entry for entry in vocabulary}

    llm = get_llm().with_structured_output(_ExtractionResult)
    system = SYSTEM_PROMPT.format(vocabulary=_format_vocabulary(vocabulary))
    user = USER_TEMPLATE.format(message=text)

    result = await llm.ainvoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )

    preferences = []
    for item in result.preferences:
        entry = (
            vocabulary_by_code.get(item.vocabulary_code)
            if item.vocabulary_code is not None
            else None
        )
        is_mapped = entry is not None and item.mapping_type != MappingType.UNMAPPED
        preferences.append(
            ExtractedPreference(
                vocabulary_code=entry.code if is_mapped else None,
                display_name=entry.display_name if is_mapped else None,
                domain=entry.domain if is_mapped else None,
                raw_value=item.raw_value,
                sentiment=item.sentiment,
                strength=item.strength,
                mapping_type=item.mapping_type if is_mapped else MappingType.UNMAPPED,
            )
        )
    return preferences


async def extract_preferences_node(state: PreferenceState) -> dict:
    return {"preferences": await extract_preferences(state["message"])}
