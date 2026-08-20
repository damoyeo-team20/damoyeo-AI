"""`/ai/meetings/{meetingId}/context/messages` 파이프라인(라우터 -> 일반응답/날짜재선택) LangGraph 조립.

candidate_dates가 없으면 라우터가 LLM 호출 없이 곧장 일반 응답으로 보낸다 — 기존 동작과 100%
동일하게 유지된다. candidate_dates가 있을 때만 날짜 변경 의사를 분류해서 분기한다.
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.context_state import ContextChatState
from app.graph.nodes.n_context_parser import generate_reply_node
from app.graph.nodes.n_context_router import route_context_message
from app.graph.nodes.n_context_date_reselector import reselect_date


def _route_after_classification(state: ContextChatState) -> str:
    return "reselect_date" if state.get("wants_date_change") else "generate_reply"


def build_context_graph() -> CompiledStateGraph:
    graph = StateGraph(ContextChatState)
    graph.add_node("route_context_message", route_context_message)
    graph.add_node("generate_reply", generate_reply_node)
    graph.add_node("reselect_date", reselect_date)

    graph.set_entry_point("route_context_message")
    graph.add_conditional_edges(
        "route_context_message",
        _route_after_classification,
        {"generate_reply": "generate_reply", "reselect_date": "reselect_date"},
    )
    graph.add_edge("generate_reply", END)
    graph.add_edge("reselect_date", END)

    return graph.compile()


_context_graph: CompiledStateGraph | None = None


def get_context_graph() -> CompiledStateGraph:
    global _context_graph
    if _context_graph is None:
        _context_graph = build_context_graph()
    return _context_graph
