import asyncio

from app.graph import build_preference_graph
from app.schemas.preference import ExtractedPreference, MappingType, Sentiment, Strength


def _preference() -> ExtractedPreference:
    return ExtractedPreference(
        vocabulary_code="SPICY_FOOD",
        display_name="매운 음식",
        domain="FOOD",
        raw_value="매운 음식",
        sentiment=Sentiment.POSITIVE,
        strength=Strength.MODERATE,
        mapping_type=MappingType.EXACT,
    )


def test_in_scope_input_is_extracted_and_acknowledged(monkeypatch):
    async def route(_state):
        return {"route": "IN_SCOPE"}

    async def extract(state):
        assert state["message"] == "매운 음식 좋아해"
        return {"preferences": [_preference()]}

    async def fail_guardrail(_state):
        raise AssertionError("정상 선호 입력에서 가드레일을 실행하면 안 된다")

    monkeypatch.setattr(build_preference_graph, "route_message", route)
    monkeypatch.setattr(build_preference_graph, "extract_preferences_node", extract)
    monkeypatch.setattr(build_preference_graph, "guide_preference_input", fail_guardrail)

    graph = build_preference_graph.build_preference_graph()
    result = asyncio.run(graph.ainvoke({"message": "매운 음식 좋아해"}))

    assert result["preferences"] == [_preference()]
    assert result["assistant_reply"] == "말씀해주신 내용을 선호에 반영했어요."


def test_out_of_scope_input_uses_fixed_guardrail_without_extraction(monkeypatch):
    async def route(_state):
        return {"route": "OUT_OF_SCOPE"}

    async def fail_extract(_state):
        raise AssertionError("범위 밖 입력에서 추출기를 실행하면 안 된다")

    monkeypatch.setattr(build_preference_graph, "route_message", route)
    monkeypatch.setattr(build_preference_graph, "extract_preferences_node", fail_extract)

    graph = build_preference_graph.build_preference_graph()
    result = asyncio.run(graph.ainvoke({"message": "오늘 날씨 알려줘"}))

    assert result["preferences"] == []
    assert result["assistant_reply"] == (
        "좋아하거나 피하고 싶은 음식, 음주 여부, 원하는 분위기나 활동을 알려주세요."
    )


def test_empty_extraction_falls_back_to_same_guardrail(monkeypatch):
    async def route(_state):
        return {"route": "IN_SCOPE"}

    async def extract(_state):
        return {"preferences": []}

    monkeypatch.setattr(build_preference_graph, "route_message", route)
    monkeypatch.setattr(build_preference_graph, "extract_preferences_node", extract)

    graph = build_preference_graph.build_preference_graph()
    result = asyncio.run(graph.ainvoke({"message": "아무거나"}))

    assert result["preferences"] == []
    assert "알려주세요" in result["assistant_reply"]
