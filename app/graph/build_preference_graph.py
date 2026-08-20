"""`/ai/preferences/extract` 파이프라인(범위 판별 -> 추출 또는 가드레일) 조립.

정상 선호 입력만 추출기로 보내고, 범위 밖 입력이나 추출 결과가 비어 있는 입력은 고정 가드레일
안내로 되돌린다. 사용자와 불필요한 잡담을 이어가는 노드는 두지 않는다.
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.l_preference_guardrail import (
    acknowledge_preferences,
    guide_preference_input,
)
from app.graph.nodes.n_preference_router import route_message
from app.graph.nodes.n_preference_extractor import extract_preferences_node
from app.graph.preference_state import PreferenceState


def _route_after_scope_check(state: PreferenceState) -> str:
    return "extract_preferences" if state.get("route") == "IN_SCOPE" else "guardrail"


def _route_after_extraction(state: PreferenceState) -> str:
    return "acknowledge" if state.get("preferences") else "guardrail"


def build_preference_graph() -> CompiledStateGraph:
    graph = StateGraph(PreferenceState)
    graph.add_node("route_message", route_message)
    graph.add_node("extract_preferences", extract_preferences_node)
    graph.add_node("guardrail", guide_preference_input)
    graph.add_node("acknowledge", acknowledge_preferences)

    graph.set_entry_point("route_message")
    graph.add_conditional_edges(
        "route_message",
        _route_after_scope_check,
        {
            "extract_preferences": "extract_preferences",
            "guardrail": "guardrail",
        },
    )
    graph.add_conditional_edges(
        "extract_preferences",
        _route_after_extraction,
        {"acknowledge": "acknowledge", "guardrail": "guardrail"},
    )
    graph.add_edge("guardrail", END)
    graph.add_edge("acknowledge", END)

    return graph.compile()


_preference_graph: CompiledStateGraph | None = None


def get_preference_graph() -> CompiledStateGraph:
    global _preference_graph
    if _preference_graph is None:
        _preference_graph = build_preference_graph()
    return _preference_graph
