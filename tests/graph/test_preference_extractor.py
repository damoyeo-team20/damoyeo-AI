import asyncio
from types import SimpleNamespace

from app.graph.nodes import n_preference_extractor
from app.schemas.preference import MappingType, Sentiment, Strength
from app.services.vocabulary_client import VocabularyEntry


class _StructuredLLM:
    async def ainvoke(self, _messages):
        return SimpleNamespace(
            preferences=[
                SimpleNamespace(
                    vocabulary_code="SEAFOOD",
                    raw_value="해산물",
                    sentiment=Sentiment.POSITIVE,
                    strength=Strength.MODERATE,
                    mapping_type=MappingType.EXACT,
                ),
                SimpleNamespace(
                    vocabulary_code="NOT_IN_VOCABULARY",
                    raw_value="고수",
                    sentiment=Sentiment.NEGATIVE,
                    strength=Strength.STRONG,
                    mapping_type=MappingType.EXACT,
                ),
                SimpleNamespace(
                    vocabulary_code="SEAFOOD",
                    raw_value="모델이 모순되게 반환한 값",
                    sentiment=Sentiment.NEGATIVE,
                    strength=Strength.STRONG,
                    mapping_type=MappingType.UNMAPPED,
                ),
                SimpleNamespace(
                    vocabulary_code=None,
                    raw_value="코드 없는 값",
                    sentiment=Sentiment.NEGATIVE,
                    strength=Strength.MODERATE,
                    mapping_type=MappingType.GENERALIZED,
                ),
                SimpleNamespace(
                    vocabulary_code="MEAT",
                    raw_value="사슴고기",
                    sentiment=Sentiment.POSITIVE,
                    strength=Strength.MODERATE,
                    mapping_type=MappingType.GENERALIZED,
                ),
            ]
        )


class _LLM:
    def with_structured_output(self, _schema):
        return _StructuredLLM()


def test_extract_preferences_enriches_known_code_and_normalizes_unknown_code(monkeypatch):
    async def fake_fetch_vocabulary():
        return [
            VocabularyEntry(
                code="SEAFOOD",
                domain="FOOD",
                display_name="해산물",
                parent_code=None,
            ),
            VocabularyEntry(
                code="MEAT",
                domain="FOOD",
                display_name="육류",
                parent_code=None,
            ),
        ]

    monkeypatch.setattr(n_preference_extractor, "fetch_vocabulary", fake_fetch_vocabulary)
    monkeypatch.setattr(n_preference_extractor, "get_llm", lambda: _LLM())

    preferences = asyncio.run(n_preference_extractor.extract_preferences("해산물 좋아해"))

    assert preferences[0].model_dump(by_alias=True)["displayName"] == "해산물"
    assert preferences[0].domain == "FOOD"
    assert preferences[1].vocabulary_code is None
    assert preferences[1].display_name is None
    assert preferences[1].domain is None
    assert preferences[1].mapping_type == MappingType.UNMAPPED
    assert preferences[1].raw_value == "고수"
    assert preferences[1].sentiment == Sentiment.NEGATIVE
    assert preferences[1].strength == Strength.STRONG

    for preference in preferences[2:4]:
        assert preference.vocabulary_code is None
        assert preference.display_name is None
        assert preference.domain is None
        assert preference.mapping_type == MappingType.UNMAPPED

    assert preferences[4].vocabulary_code == "MEAT"
    assert preferences[4].display_name == "육류"
    assert preferences[4].domain == "FOOD"
    assert preferences[4].mapping_type == MappingType.GENERALIZED


def test_llm_schema_accepts_string_code_without_vocabulary_enum():
    schema = n_preference_extractor._ExtractionResult.model_json_schema()
    code_schema = schema["$defs"]["_ExtractedPreferenceItem"]["properties"][
        "vocabulary_code"
    ]

    assert "enum" not in code_schema
    assert {item.get("type") for item in code_schema["anyOf"]} == {"string", "null"}

    result = n_preference_extractor._ExtractionResult.model_validate(
        {
            "preferences": [
                {
                    "vocabulary_code": "ANY_MODEL_GENERATED_CODE",
                    "raw_value": "새로운 취향",
                    "sentiment": "POSITIVE",
                    "strength": "WEAK",
                    "mapping_type": "EXACT",
                }
            ]
        }
    )

    assert result.preferences[0].vocabulary_code == "ANY_MODEL_GENERATED_CODE"
