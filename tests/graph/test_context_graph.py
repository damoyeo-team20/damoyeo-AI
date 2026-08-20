import asyncio
from types import SimpleNamespace

from app.graph import build_context_graph
from app.graph.nodes import n_context_date_reselector, n_context_parser, n_context_router
from app.schemas.meeting_context import CandidateDate

_CANDIDATES = [
    CandidateDate(date="2026-08-23", selected=True),
    CandidateDate(date="2026-08-30", selected=False),
]


def test_graph_routes_to_generate_reply_without_candidate_dates(monkeypatch):
    class _RouterLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(route="IN_SCOPE")

    class _ChatLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="편안하게 준비할게요.")

    monkeypatch.setattr(
        n_context_router,
        "get_llm",
        lambda: SimpleNamespace(with_structured_output=lambda _s: _RouterLLM()),
    )
    monkeypatch.setattr(n_context_parser, "get_llm", lambda: _ChatLLM())

    graph = build_context_graph.build_context_graph()
    result = asyncio.run(graph.ainvoke({"history": [], "message": "오늘 뭐 먹을까요?"}))

    assert result["reply"] == "편안하게 준비할게요."
    assert result.get("candidate_dates") is None


def test_graph_routes_to_reselect_date_when_intent_detected(monkeypatch):
    class _RouterLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(route="DATE_CHANGE")

    class _ReselectLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(chosen_date="2026-08-30", reply="네, 30일로 바꿔드릴게요.")

    monkeypatch.setattr(
        n_context_router, "get_llm", lambda: SimpleNamespace(with_structured_output=lambda _s: _RouterLLM())
    )
    monkeypatch.setattr(
        n_context_date_reselector,
        "get_llm",
        lambda: SimpleNamespace(with_structured_output=lambda _s: _ReselectLLM()),
    )

    def _fail_chat(*_args, **_kwargs):
        raise AssertionError("날짜 변경 분기에서는 일반 대화 LLM을 호출하면 안 된다")

    monkeypatch.setattr(n_context_parser, "get_llm", _fail_chat)

    graph = build_context_graph.build_context_graph()
    result = asyncio.run(
        graph.ainvoke(
            {"history": [], "message": "30일로 바꿔줘", "candidate_dates": _CANDIDATES}
        )
    )

    assert result["reply"] == "네, 30일로 바꿔드릴게요."
    assert result["candidate_dates"] == [
        CandidateDate(date="2026-08-23", selected=False),
        CandidateDate(date="2026-08-30", selected=True),
    ]


def test_graph_routes_out_of_scope_to_fixed_guardrail(monkeypatch):
    class _RouterLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(route="OUT_OF_SCOPE")

    def _fail_downstream(*_args, **_kwargs):
        raise AssertionError("범위 밖 입력에서 Parser나 Date Reselector를 실행하면 안 된다")

    monkeypatch.setattr(
        n_context_router,
        "get_llm",
        lambda: SimpleNamespace(with_structured_output=lambda _s: _RouterLLM()),
    )
    monkeypatch.setattr(n_context_parser, "get_llm", _fail_downstream)
    monkeypatch.setattr(n_context_date_reselector, "get_llm", _fail_downstream)

    graph = build_context_graph.build_context_graph()
    result = asyncio.run(
        graph.ainvoke(
            {"history": [], "message": "오늘 날씨 알려줘", "candidate_dates": _CANDIDATES}
        )
    )

    assert result["reply"] == (
        "이번 모임의 목적, 원하는 분위기나 활동, 꼭 반영할 조건을 알려주세요."
    )
    assert result["candidate_dates"] == _CANDIDATES
