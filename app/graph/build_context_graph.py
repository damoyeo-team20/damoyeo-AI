"""`/ai/meetings/{meetingId}/context/messages`의 범위 판별 기반 LangGraph 조립.

모임 목적 입력, 범위 밖 입력, 날짜 변경 입력을 각각 Parser, 고정 Guardrail, Date Reselector로
분기한다. DATE_CHANGE는 candidate_dates가 있는 요청에서만 라우터 출력으로 허용된다.
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.context_state import ContextChatState
from app.graph.nodes.l_context_guardrail import guide_context_input
from app.graph.nodes.n_context_parser import generate_reply_node
from app.graph.nodes.n_context_router import route_context_message
from app.graph.nodes.n_context_date_reselector import reselect_date


def _route_after_classification(state: ContextChatState) -> str:
    route = state.get("route")
    if route == "IN_SCOPE":
        return "generate_reply"
    if route == "DATE_CHANGE":
        return "reselect_date"
    return "guardrail"


def build_context_graph() -> CompiledStateGraph:
    graph = StateGraph(ContextChatState)
    graph.add_node("route_context_message", route_context_message)
    graph.add_node("generate_reply", generate_reply_node)
    graph.add_node("reselect_date", reselect_date)
    graph.add_node("guardrail", guide_context_input)

    graph.set_entry_point("route_context_message")
    graph.add_conditional_edges(
        "route_context_message",
        _route_after_classification,
        {
            "generate_reply": "generate_reply",
            "reselect_date": "reselect_date",
            "guardrail": "guardrail",
        },
    )
    graph.add_edge("generate_reply", END)
    graph.add_edge("reselect_date", END)
    graph.add_edge("guardrail", END)

    return graph.compile()


_context_graph: CompiledStateGraph | None = None


def get_context_graph() -> CompiledStateGraph:
    global _context_graph
    if _context_graph is None:
        _context_graph = build_context_graph()
    return _context_graph
