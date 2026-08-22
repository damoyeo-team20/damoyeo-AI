import asyncio
from types import SimpleNamespace

from app.graph.nodes import n_context_date_reselector
from app.schemas.meeting_context import CandidateDate

_CANDIDATES = [
    CandidateDate(date="2026-08-23", selected=True),
    CandidateDate(date="2026-08-30", selected=False),
]


def test_reselect_date_moves_selected_flag_when_date_is_clear(monkeypatch):
    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(chosen_date="2026-08-30", reply="네, 30일로 바꿔드릴게요.")

    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    monkeypatch.setattr(n_context_date_reselector, "get_llm", lambda: _LLM())

    result = asyncio.run(
        n_context_date_reselector.reselect_date(
            {"message": "30일로 해줘", "history": [], "candidate_dates": _CANDIDATES}
        )
    )

    assert result["reply"] == "네, 30일로 바꿔드릴게요."
    assert result["candidate_dates"] == [
        CandidateDate(date="2026-08-23", selected=False),
        CandidateDate(date="2026-08-30", selected=True),
    ]


def test_reselect_date_keeps_selection_when_date_is_unclear(monkeypatch):
    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(
                chosen_date=None, reply="어떤 날짜로 바꿔드릴까요? 8월 23일 또는 8월 30일 중에서요."
            )

    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    monkeypatch.setattr(n_context_date_reselector, "get_llm", lambda: _LLM())

    result = asyncio.run(
        n_context_date_reselector.reselect_date(
            {"message": "다른 날로 바꾸고 싶어", "history": [], "candidate_dates": _CANDIDATES}
        )
    )

    assert "어떤 날짜" in result["reply"]
    assert result["candidate_dates"] == _CANDIDATES


def test_build_reselect_schema_rejects_dates_outside_candidates():
    schema = n_context_date_reselector._build_reselect_schema(_CANDIDATES)

    schema.model_validate({"chosen_date": "2026-08-23", "reply": "네"})
    try:
        schema.model_validate({"chosen_date": "2099-01-01", "reply": "네"})
    except Exception:
        pass
    else:
        raise AssertionError("후보 목록 밖 날짜가 통과해서는 안 된다")
