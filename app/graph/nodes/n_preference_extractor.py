"""Preference Extractor.

가드레일을 통과한 입력에서 개인 선호만 골라 Vocabulary 매핑된 구조로 변환한다.
"""

from typing import Literal

from pydantic import BaseModel, Field, create_model

from app.core.debug import record_debug  # TEMP DEBUG
from app.core.llm import get_llm
from app.graph.preference_state import PreferenceState
from app.prompts.n_preference_extractor import SYSTEM_PROMPT, USER_TEMPLATE
from app.schemas.preference import ExtractedPreference, MappingType, Sentiment, Strength
from app.services.vocabulary_client import VocabularyEntry, fetch_vocabulary


def _build_extraction_schema(vocabulary: list[VocabularyEntry]) -> type[BaseModel]:
    """Vocabulary에 없는 code를 LLM이 임의로 만들지 못하도록 code 필드를 Literal로 동적 제약한다.

    UNMAPPED(대응 code 없음)도 유효한 결과이므로 None을 함께 허용한다.
    """
    codes = [entry.code for entry in vocabulary]
    code_type = (Literal[tuple(codes)] | None) if codes else (str | None)  # type: ignore[valid-type]

    extracted_item = create_model(
        "ExtractedPreferenceItem",
        vocabulary_code=(
            code_type,
            Field(description="Vocabulary 목록에 존재하는 code. UNMAPPED면 null."),
        ),
        raw_value=(str, ...),
        sentiment=(Sentiment, ...),
        strength=(Strength, ...),
        mapping_type=(MappingType, ...),
    )
    return create_model(
        "ExtractionResult",
        preferences=(list[extracted_item], Field(default_factory=list)),
    )


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
    schema = _build_extraction_schema(vocabulary)

    llm = get_llm().with_structured_output(schema)
    system = SYSTEM_PROMPT.format(vocabulary=_format_vocabulary(vocabulary))
    user = USER_TEMPLATE.format(message=text)

    result = await llm.ainvoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    record_debug("n_preference_extractor", result.preferences)  # TEMP DEBUG

    preferences = []
    for item in result.preferences:
        entry = vocabulary_by_code.get(item.vocabulary_code)
        preferences.append(
            ExtractedPreference(
                vocabulary_code=item.vocabulary_code,
                display_name=entry.display_name if entry else None,
                domain=entry.domain if entry else None,
                raw_value=item.raw_value,
                sentiment=item.sentiment,
                strength=item.strength,
                mapping_type=item.mapping_type,
            )
        )
    return preferences


async def extract_preferences_node(state: PreferenceState) -> dict:
    return {"preferences": await extract_preferences(state["message"])}
