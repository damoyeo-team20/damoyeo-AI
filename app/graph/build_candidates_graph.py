"""candidates 파이프라인 LangGraph 조립.

`POST /ai/meetings/{meetingId}/candidates`가 검색 계획 생성 -> 넓은 장소 검색 ->
컨텍스트·공정성 선랭킹 -> 상위 후보 영업 검증 -> 응답 조립을 한 번에 처리한다.
Activity Decider가 CONFLICT를 반환하면 이후 노드를 실행하지 않고 종료한다.
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.l_candidate_place_search import search_places
from app.graph.nodes.l_candidate_suggestion_builder import build_suggestions
from app.graph.nodes.n_candidate_activity_decider import decide_activities
from app.graph.nodes.n_candidate_place_verifier import verify_places
from app.graph.nodes.n_candidate_ranker import rank_and_explain
from app.graph.candidates_state import CandidatesState


def _route_after_activity_decision(state: CandidatesState) -> str:
    return "conflict" if state.get("action_required") else "continue"


def build_candidates_graph() -> CompiledStateGraph:
    graph = StateGraph(CandidatesState)
    graph.add_node("decide_activities", decide_activities)
    graph.add_node("search_places", search_places)
    graph.add_node("rank_and_explain", rank_and_explain)
    graph.add_node("verify_places", verify_places)
    graph.add_node("build_suggestions", build_suggestions)

    graph.set_entry_point("decide_activities")
    graph.add_conditional_edges(
        "decide_activities",
        _route_after_activity_decision,
        {"continue": "search_places", "conflict": END},
    )
    graph.add_edge("search_places", "rank_and_explain")
    graph.add_edge("rank_and_explain", "verify_places")
    graph.add_edge("verify_places", "build_suggestions")
    graph.add_edge("build_suggestions", END)

    return graph.compile()


_candidates_graph: CompiledStateGraph | None = None


def get_candidates_graph() -> CompiledStateGraph:
    global _candidates_graph
    if _candidates_graph is None:
        _candidates_graph = build_candidates_graph()
    return _candidates_graph
