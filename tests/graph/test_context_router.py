import asyncio
from types import SimpleNamespace

from app.graph.nodes import n_context_router
from app.schemas.meeting_context import CandidateDate


def test_router_skips_llm_when_no_candidate_dates(monkeypatch):
    def _fail(*_args, **_kwargs):
        raise AssertionError("candidate_dates가 없으면 LLM을 호출하면 안 된다")

    monkeypatch.setattr(n_context_router, "get_llm", _fail)

    result = asyncio.run(
        n_context_router.route_context_message({"message": "오늘 뭐 먹을까요?", "history": []})
    )

    assert result == {"wants_date_change": False}


def test_router_classifies_date_change_intent(monkeypatch):
    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(wants_date_change=True)

    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    monkeypatch.setattr(n_context_router, "get_llm", lambda: _LLM())

    result = asyncio.run(
        n_context_router.route_context_message(
            {
                "message": "30일로 바꿔줘",
                "history": [],
                "candidate_dates": [
                    CandidateDate(date="2026-08-23", selected=True),
                    CandidateDate(date="2026-08-30", selected=False),
                ],
            }
        )
    )

    assert result == {"wants_date_change": True}
