import asyncio
from types import SimpleNamespace

import pytest

from app.graph.nodes import n_context_router
from app.schemas.meeting_context import CandidateDate


def _route(monkeypatch, route, state):
    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(route=route)

    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    monkeypatch.setattr(n_context_router, "get_llm", lambda: _LLM())
    return asyncio.run(n_context_router.route_context_message(state))


@pytest.mark.parametrize("route", ["IN_SCOPE", "OUT_OF_SCOPE"])
def test_router_checks_scope_without_candidate_dates(monkeypatch, route):
    result = _route(
        monkeypatch,
        route,
        {"message": "조용한 곳에서 이야기하고 싶어요", "history": []},
    )

    assert result == {"route": route}


def test_router_classifies_date_change_intent(monkeypatch):
    result = _route(
        monkeypatch,
        "DATE_CHANGE",
        {
            "message": "30일로 바꿔줘",
            "history": [],
            "candidate_dates": [
                CandidateDate(date="2026-08-23", selected=True),
                CandidateDate(date="2026-08-30", selected=False),
            ],
        },
    )

    assert result == {"route": "DATE_CHANGE"}


def test_route_schema_disallows_date_change_without_candidates():
    schema = n_context_router._build_route_schema(has_candidate_dates=False)

    with pytest.raises(Exception):
        schema.model_validate({"route": "DATE_CHANGE"})


def test_route_schema_allows_date_change_with_candidates():
    schema = n_context_router._build_route_schema(has_candidate_dates=True)

    assert schema.model_validate({"route": "DATE_CHANGE"}).route == "DATE_CHANGE"
