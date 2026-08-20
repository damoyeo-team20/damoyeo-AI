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
                    vocabulary_code=None,
                    raw_value="새로운 취향",
                    sentiment=Sentiment.POSITIVE,
                    strength=Strength.WEAK,
                    mapping_type=MappingType.UNMAPPED,
                ),
            ]
        )


class _LLM:
    def with_structured_output(self, _schema):
        return _StructuredLLM()


def test_extract_preferences_enriches_from_vocabulary(monkeypatch):
    async def fake_fetch_vocabulary():
        return [
            VocabularyEntry(
                code="SEAFOOD",
                domain="FOOD",
                display_name="해산물",
                parent_code=None,
            )
        ]

    monkeypatch.setattr(n_preference_extractor, "fetch_vocabulary", fake_fetch_vocabulary)
    monkeypatch.setattr(n_preference_extractor, "get_llm", lambda: _LLM())

    preferences = asyncio.run(n_preference_extractor.extract_preferences("해산물 좋아해"))

    assert preferences[0].model_dump(by_alias=True)["displayName"] == "해산물"
    assert preferences[0].domain == "FOOD"
    assert preferences[1].vocabulary_code is None
    assert preferences[1].display_name is None
    assert preferences[1].domain is None
