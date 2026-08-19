"""`/ai/preferences/extract` 파이프라인(라우터 -> 추출/스몰톡 팬아웃) LangGraph 조립.

라우터가 발화를 선호 부분/잡담 부분으로 나누고, 존재하는 부분에 한해 추출 노드와 스몰톡 노드가
병렬로 실행된다 (한 메시지에 둘 다 있으면 둘 다 실행됨).
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.n1_message_router import route_message
from app.graph.nodes.n1_preference_extractor import extract_preferences_node
from app.graph.nodes.n1_smalltalk_handler import handle_smalltalk
from app.graph.preference_state import PreferenceState


def _route_after_split(state: PreferenceState) -> list[str]:
    targets = []
    if state.get("preference_text"):
        targets.append("extract_preferences")
    if state.get("smalltalk_text"):
        targets.append("handle_smalltalk")
    return targets or ["handle_smalltalk"]


def build_preference_graph() -> CompiledStateGraph:
    graph = StateGraph(PreferenceState)
    graph.add_node("route_message", route_message)
    graph.add_node("extract_preferences", extract_preferences_node)
    graph.add_node("handle_smalltalk", handle_smalltalk)

    graph.set_entry_point("route_message")
    graph.add_conditional_edges(
        "route_message",
        _route_after_split,
        {"extract_preferences": "extract_preferences", "handle_smalltalk": "handle_smalltalk"},
    )
    graph.add_edge("extract_preferences", END)
    graph.add_edge("handle_smalltalk", END)

    return graph.compile()


_preference_graph: CompiledStateGraph | None = None


def get_preference_graph() -> CompiledStateGraph:
    global _preference_graph
    if _preference_graph is None:
        _preference_graph = build_preference_graph()
    return _preference_graph
