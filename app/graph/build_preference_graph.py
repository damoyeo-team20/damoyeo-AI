"""`/ai/preferences/extract` 파이프라인(라우터 -> 추출/응답 팬아웃) LangGraph 조립.

라우터가 발화를 선호 부분/잡담 부분으로 나눈다. `assistant_reply`는 항상 채워지지만 경로가 다르다:
- 잡담이 있으면: handle_smalltalk(LLM)이 실제로 반응하고 다음 발화를 유도한다.
- 선호만 있으면: acknowledge_preferences_only가 LLM 없이 고정 문구로 완료만 통보한다.
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.n1_message_router import route_message
from app.graph.nodes.n1_preference_extractor import extract_preferences_node
from app.graph.nodes.n1_smalltalk_handler import acknowledge_preferences_only, handle_smalltalk
from app.graph.preference_state import PreferenceState


def _route_after_split(state: PreferenceState) -> list[str]:
    has_preference = bool(state.get("preference_text"))
    has_smalltalk = bool(state.get("smalltalk_text"))

    targets = []
    if has_preference:
        targets.append("extract_preferences")

    if has_smalltalk:
        targets.append("handle_smalltalk")
    elif has_preference:
        targets.append("acknowledge_preferences_only")

    # 라우터가 선호도 잡담도 못 찾은 극단적인 경우 — 폴백으로 잡담 취급.
    return targets or ["handle_smalltalk"]


def build_preference_graph() -> CompiledStateGraph:
    graph = StateGraph(PreferenceState)
    graph.add_node("route_message", route_message)
    graph.add_node("extract_preferences", extract_preferences_node)
    graph.add_node("handle_smalltalk", handle_smalltalk)
    graph.add_node("acknowledge_preferences_only", acknowledge_preferences_only)

    graph.set_entry_point("route_message")
    graph.add_conditional_edges(
        "route_message",
        _route_after_split,
        {
            "extract_preferences": "extract_preferences",
            "handle_smalltalk": "handle_smalltalk",
            "acknowledge_preferences_only": "acknowledge_preferences_only",
        },
    )
    graph.add_edge("extract_preferences", END)
    graph.add_edge("handle_smalltalk", END)
    graph.add_edge("acknowledge_preferences_only", END)

    return graph.compile()


_preference_graph: CompiledStateGraph | None = None


def get_preference_graph() -> CompiledStateGraph:
    global _preference_graph
    if _preference_graph is None:
        _preference_graph = build_preference_graph()
    return _preference_graph
