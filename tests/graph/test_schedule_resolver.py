import asyncio
from types import SimpleNamespace

from app.graph.nodes import n_schedule_resolver
from app.schemas.schedule import ScheduleRequest


def test_resolve_schedule_only_picks_from_common_dates(monkeypatch):
    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(chosen_date="2026-08-30", reason="주말이라 여유 있어요.")

    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    monkeypatch.setattr(n_schedule_resolver, "get_llm", lambda: _LLM())

    request = ScheduleRequest.model_validate(
        {
            "commonAvailableDates": ["2026-08-23", "2026-08-30"],
            "preferredTimeOfDay": "EVENING",
            "durationMinutes": 120,
            "timezone": "Asia/Seoul",
        }
    )
    response = asyncio.run(n_schedule_resolver.resolve_schedule(request))

    assert response.reason == "주말이라 여유 있어요."
    assert response.resolved_start_at.isoformat() == "2026-08-30T18:00:00+09:00"
    assert response.resolved_end_at.isoformat() == "2026-08-30T20:00:00+09:00"
    # 계약: 두 시각의 차이는 정확히 durationMinutes.
    delta = response.resolved_end_at - response.resolved_start_at
    assert delta.total_seconds() / 60 == 120
