"""candidates 파이프라인(N4 -> L5 -> N6 -> N7) LangGraph 조립.

`POST /ai/meetings/{meetingId}/candidates`가 이 그래프 하나로 활동 결정 + 장소 검색 +
영업 검증 + 랭킹을 한 번에 처리한다. N4가 CONFLICT를 반환하면 이후 노드를 실행하지 않고 종료한다.
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.l5_kakao_search import search_places
from app.graph.nodes.n4_activity_decider import decide_activities
from app.graph.nodes.n6_research_subagent import verify_places
from app.graph.nodes.n7_ranker_explainer import rank_and_explain
from app.graph.state import CandidatesState


def _route_after_activity_decision(state: CandidatesState) -> str:
    return "conflict" if state.get("action_required") else "continue"


def build_candidates_graph() -> CompiledStateGraph:
    graph = StateGraph(CandidatesState)
    graph.add_node("decide_activities", decide_activities)
    graph.add_node("search_places", search_places)
    graph.add_node("verify_places", verify_places)
    graph.add_node("rank_and_explain", rank_and_explain)

    graph.set_entry_point("decide_activities")
    graph.add_conditional_edges(
        "decide_activities",
        _route_after_activity_decision,
        {"continue": "search_places", "conflict": END},
    )
    graph.add_edge("search_places", "verify_places")
    graph.add_edge("verify_places", "rank_and_explain")
    graph.add_edge("rank_and_explain", END)

    return graph.compile()


_candidates_graph: CompiledStateGraph | None = None


def get_candidates_graph() -> CompiledStateGraph:
    global _candidates_graph
    if _candidates_graph is None:
        _candidates_graph = build_candidates_graph()
    return _candidates_graph
