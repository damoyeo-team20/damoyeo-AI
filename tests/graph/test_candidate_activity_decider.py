import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.errors import AIServiceError
from app.graph.nodes import n_candidate_activity_decider
from app.schemas.candidates import ConfirmedSlot, MeetingInput


def _activity(
    label: str = "저녁 식사",
    *,
    source: str = "MEETING_PURPOSE",
    queries: list[str] | None = None,
    rationale: str = "모임 목적에 맞는 저녁 식사를 찾습니다.",
) -> dict:
    return {
        "activity": label,
        "source": source,
        "search_queries": queries or ["한식"],
        "rationale_group": rationale,
    }


def _state(region: str = "건대") -> dict:
    return {
        "meeting": MeetingInput(id=29, purpose="저녁 모임", region=region),
        "confirmed_slot": ConfirmedSlot(
            confirmed_start_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
            confirmed_end_at=datetime(2026, 8, 21, 11, 0, tzinfo=UTC),
        ),
        "participants": [],
    }


def _stub_llm(monkeypatch, result, received: dict[str, str] | None = None) -> None:
    class _StructuredLLM:
        async def ainvoke(self, messages):
            if received is not None:
                received["system"] = messages[0]["content"]
            return {"raw": None, "parsed": result, "parsing_error": None}

    class _LLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            return _StructuredLLM()

    monkeypatch.setattr(n_candidate_activity_decider, "get_llm", lambda: _LLM())


def _valid_activities(count: int) -> list[dict]:
    sources = [
        "MEETING_PURPOSE",
        "PARTICIPANT_PREFERENCE",
        "PARTICIPANT_PREFERENCE",
        "MEETING_MEMORY",
    ]
    return [
        _activity(f"검색 계획 {index + 1}", source=sources[index], queries=[f"검색어 {index + 1}"])
        for index in range(count)
    ]


def test_activity_prompt_uses_seoul_local_time(monkeypatch):
    received: dict[str, str] = {}
    result = n_candidate_activity_decider._ActivityDecision.model_validate(
        {
            "status": "OK",
            "activities": [_activity()],
            "meeting_tags": [],
            "summary": "저녁 식사 장소를 찾습니다.",
        }
    )
    _stub_llm(monkeypatch, result, received)

    asyncio.run(n_candidate_activity_decider.decide_activities(_state()))

    assert "2026-08-21T18:00:00+09:00" in received["system"]
    assert "2026-08-21T20:00:00+09:00" in received["system"]


@pytest.mark.parametrize("plan_count", [1, 2, 3, 4])
def test_ok_accepts_one_to_four_plans_with_a_meeting_purpose_source(plan_count):
    decision = n_candidate_activity_decider._ActivityDecision.model_validate(
        {
            "status": "OK",
            "activities": _valid_activities(plan_count),
        }
    )

    assert len(decision.activities) == plan_count
    assert any(activity.source == "MEETING_PURPOSE" for activity in decision.activities)


def test_ok_rejects_zero_plans():
    with pytest.raises(ValidationError, match="최소 1개"):
        n_candidate_activity_decider._ActivityDecision.model_validate(
            {"status": "OK", "activities": []}
        )


def test_ok_requires_a_meeting_purpose_plan():
    with pytest.raises(ValidationError, match="모임 목적"):
        n_candidate_activity_decider._ActivityDecision.model_validate(
            {
                "status": "OK",
                "activities": [
                    _activity("선호 계획", source="PARTICIPANT_PREFERENCE"),
                    _activity("메모리 계획", source="MEETING_MEMORY"),
                ],
            }
        )


def test_conflict_allows_zero_plans_and_decider_returns_no_search_plan(monkeypatch):
    decision = n_candidate_activity_decider._ActivityDecision.model_validate(
        {
            "status": "CONFLICT",
            "activities": [],
            "conflict_reason": "모임 목적과 선호가 충돌합니다.",
            "conflicting_preferences": ["ALCOHOL"],
        }
    )
    _stub_llm(monkeypatch, decision)

    result = asyncio.run(n_candidate_activity_decider.decide_activities(_state()))

    assert result["search_plans"] == []
    assert result["meeting_tags"] == []
    assert result["action_required"].conflicting_preference_codes == ["ALCOHOL"]


def test_conflict_rejects_nonempty_plans():
    with pytest.raises(ValidationError, match="CONFLICT"):
        n_candidate_activity_decider._ActivityDecision.model_validate(
            {"status": "CONFLICT", "activities": [_activity()]}
        )


def test_plan_count_is_capped_at_four():
    activities = [
        _activity(f"계획 {index}", queries=[f"검색어 {index}"])
        for index in range(5)
    ]

    with pytest.raises(ValidationError):
        n_candidate_activity_decider._ActivityDecision.model_validate(
            {"status": "OK", "activities": activities}
        )


def test_query_count_is_capped_at_three_per_plan():
    with pytest.raises(ValidationError):
        n_candidate_activity_decider._ActivityDraft.model_validate(
            _activity(queries=["검색어 1", "검색어 2", "검색어 3", "검색어 4"])
        )


@pytest.mark.parametrize(
    "activities",
    [
        [
            _activity("저녁   식사", queries=["한식"]),
            _activity("  저녁 식사  ", queries=["일식"]),
        ],
        [
            _activity("CAFE", queries=["카페"]),
            _activity("cafe", queries=["디저트 카페"]),
        ],
    ],
)
def test_duplicate_plan_labels_are_rejected_after_normalization(activities):
    with pytest.raises(ValidationError, match="중복된 활동"):
        n_candidate_activity_decider._ActivityDecision.model_validate(
            {"status": "OK", "activities": activities}
        )


@pytest.mark.parametrize(
    "queries",
    [
        ["   "],
        ["한식", " 한식  "],
        ["CAFE", "cafe"],
    ],
)
def test_blank_or_duplicate_queries_are_rejected_after_normalization(queries):
    with pytest.raises(ValidationError):
        n_candidate_activity_decider._ActivityDraft.model_validate(
            _activity(queries=queries)
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("activity", "   "), ("rationale_group", " \t ")],
)
def test_blank_plan_text_is_rejected_after_normalization(field, value):
    payload = _activity()
    payload[field] = value

    with pytest.raises(ValidationError):
        n_candidate_activity_decider._ActivityDraft.model_validate(payload)


@pytest.mark.parametrize(
    "sources",
    [
        [
            "MEETING_PURPOSE",
            "PARTICIPANT_PREFERENCE",
            "PARTICIPANT_PREFERENCE",
            "PARTICIPANT_PREFERENCE",
        ],
        ["MEETING_PURPOSE", "MEETING_MEMORY", "MEETING_MEMORY"],
    ],
)
def test_preference_and_memory_plan_source_caps_are_enforced(sources):
    activities = [
        _activity(f"계획 {index}", source=source, queries=[f"검색어 {index}"])
        for index, source in enumerate(sources)
    ]

    with pytest.raises(ValidationError):
        n_candidate_activity_decider._ActivityDecision.model_validate(
            {"status": "OK", "activities": activities}
        )


@pytest.mark.parametrize(
    "tags",
    [
        ["ACTIVE", "CONVERSATION_FOCUSED"],
        ["ALCOHOL_FRIENDLY", "NO_ALCOHOL"],
        ["LIVELY", "QUIET"],
    ],
)
def test_contradictory_meeting_tags_are_rejected(tags):
    with pytest.raises(ValidationError, match="상반된 meetingTag"):
        n_candidate_activity_decider._ActivityDecision.model_validate(
            {
                "status": "OK",
                "activities": [_activity()],
                "meeting_tags": tags,
            }
        )


def test_region_prefix_is_removed_and_post_removal_duplicates_are_deduplicated(monkeypatch):
    decision = n_candidate_activity_decider._ActivityDecision.model_validate(
        {
            "status": "OK",
            "activities": [
                _activity(
                    "저녁 식사",
                    queries=["건대 건대 이자카야", "건대 카페", "카페"],
                    rationale="목적에 맞는 식사와 대화 장소를 찾습니다.",
                )
            ],
            "summary": "저녁 모임 후보를 찾습니다.",
        }
    )
    _stub_llm(monkeypatch, decision)

    result = asyncio.run(n_candidate_activity_decider.decide_activities(_state(region="건대")))

    assert result["search_plans"] == [
        {
            "label": "저녁 식사",
            "source": "MEETING_PURPOSE",
            "search_queries": ["이자카야", "카페"],
            "rationale_group": "목적에 맞는 식사와 대화 장소를 찾습니다.",
        }
    ]


def test_search_plans_are_ordered_by_source_priority(monkeypatch):
    decision = n_candidate_activity_decider._ActivityDecision.model_validate(
        {
            "status": "OK",
            "activities": [
                _activity("과거 계획", source="MEETING_MEMORY", queries=["보드게임카페"]),
                _activity("선호 계획", source="PARTICIPANT_PREFERENCE", queries=["고깃집"]),
                _activity("목적 계획", source="MEETING_PURPOSE", queries=["조용한 식당"]),
            ],
        }
    )
    _stub_llm(monkeypatch, decision)

    result = asyncio.run(n_candidate_activity_decider.decide_activities(_state()))

    assert [plan["source"] for plan in result["search_plans"]] == [
        "MEETING_PURPOSE",
        "PARTICIPANT_PREFERENCE",
        "MEETING_MEMORY",
    ]


def test_region_only_query_is_rejected_after_prefix_removal(monkeypatch):
    decision = n_candidate_activity_decider._ActivityDecision.model_validate(
        {
            "status": "OK",
            "activities": [_activity(queries=["건대", " 건대  건대 "])],
        }
    )
    _stub_llm(monkeypatch, decision)

    with pytest.raises(AIServiceError) as exc_info:
        asyncio.run(n_candidate_activity_decider.decide_activities(_state(region="건대")))

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"


def test_structured_output_parse_error_becomes_model_response_invalid(monkeypatch):
    parsing_error = ValueError("invalid structured output")

    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return {"raw": None, "parsed": None, "parsing_error": parsing_error}

    class _LLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            return _StructuredLLM()

    monkeypatch.setattr(n_candidate_activity_decider, "get_llm", lambda: _LLM())

    with pytest.raises(AIServiceError) as exc_info:
        asyncio.run(n_candidate_activity_decider.decide_activities(_state()))

    assert exc_info.value.code == "MODEL_RESPONSE_INVALID"
    assert exc_info.value.status_code == 502
