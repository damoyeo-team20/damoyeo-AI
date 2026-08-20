import asyncio
from types import SimpleNamespace

import pytest

from app.graph.nodes import n_preference_router


@pytest.mark.parametrize("route", ["IN_SCOPE", "OUT_OF_SCOPE"])
def test_preference_router_returns_common_scope_route(monkeypatch, route):
    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(route=route)

    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    monkeypatch.setattr(n_preference_router, "get_llm", lambda: _LLM())

    result = asyncio.run(n_preference_router.route_message({"message": "입력"}))

    assert result == {"route": route}


def test_preference_route_schema_rejects_context_only_route():
    with pytest.raises(Exception):
        n_preference_router._RouteResult.model_validate({"route": "DATE_CHANGE"})
