import asyncio
from datetime import UTC, datetime

from app.graph import build_candidates_graph
from app.graph.nodes import (
    l_candidate_place_search,
    l_candidate_suggestion_builder,
    n_candidate_activity_decider,
    n_candidate_place_verifier,
    n_candidate_ranker,
)
from app.schemas.candidates import (
    ConfirmedSlot,
    MeetingInput,
    ParticipantInput,
)
from app.services.kakao_client import KakaoPlace
from app.services.vocabulary_client import VocabularyEntry


def test_candidate_graph_runs_prerank_before_verification(monkeypatch):
    calls: list[str] = []

    async def decide(_state):
        calls.append("decide")
        return {
            "search_plans": [],
            "action_required": None,
            "meeting_tags": [],
            "summary": "요약",
        }

    async def search(_state):
        calls.append("search")
        return {"place_candidates": [], "search_metrics": {}}

    async def rank(_state):
        calls.append("rank")
        return {"ranked_candidates": []}

    async def verify(_state):
        calls.append("verify")
        return {
            "verified_places": [],
            "verification_timed_out": False,
            "verification_metrics": {},
        }

    async def build(_state):
        calls.append("build")
        return {"suggestions": []}

    monkeypatch.setattr(build_candidates_graph, "decide_activities", decide)
    monkeypatch.setattr(build_candidates_graph, "search_places", search)
    monkeypatch.setattr(build_candidates_graph, "rank_and_explain", rank)
    monkeypatch.setattr(build_candidates_graph, "verify_places", verify)
    monkeypatch.setattr(build_candidates_graph, "build_suggestions", build)

    graph = build_candidates_graph.build_candidates_graph()
    result = asyncio.run(graph.ainvoke({}))

    assert calls == ["decide", "search", "rank", "verify", "build"]
    assert result["suggestions"] == []


def test_candidate_graph_stops_after_activity_conflict(monkeypatch):
    calls: list[str] = []

    async def decide(_state):
        calls.append("decide")
        return {
            "action_required": {"type": "PREFERENCE_CONFLICT"},
            "search_plans": [],
            "meeting_tags": [],
        }

    async def must_not_run(_state):
        calls.append("unexpected")
        return {}

    monkeypatch.setattr(build_candidates_graph, "decide_activities", decide)
    monkeypatch.setattr(build_candidates_graph, "search_places", must_not_run)
    monkeypatch.setattr(build_candidates_graph, "rank_and_explain", must_not_run)
    monkeypatch.setattr(build_candidates_graph, "verify_places", must_not_run)
    monkeypatch.setattr(build_candidates_graph, "build_suggestions", must_not_run)

    graph = build_candidates_graph.build_candidates_graph()
    result = asyncio.run(graph.ainvoke({}))

    assert calls == ["decide"]
    assert result["action_required"]["type"] == "PREFERENCE_CONFLICT"


def test_full_candidate_graph_connects_search_rank_verify_and_build(monkeypatch):
    activity_result = n_candidate_activity_decider._ActivityDecision.model_validate(
        {
            "status": "OK",
            "activities": [
                {
                    "activity": "저녁 식사",
                    "source": "MEETING_PURPOSE",
                    "search_queries": ["한식"],
                    "rationale_group": "대화 중심 저녁 식사 목적을 반영합니다.",
                }
            ],
            "meeting_tags": ["MEAL_INCLUDED"],
            "summary": "저녁 식사 후보를 비교했어요.",
        }
    )

    class _ActivityStructuredLLM:
        async def ainvoke(self, _messages):
            return {"raw": None, "parsed": activity_result, "parsing_error": None}

    class _ActivityLLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            return _ActivityStructuredLLM()

    monkeypatch.setattr(
        n_candidate_activity_decider,
        "get_llm",
        lambda: _ActivityLLM(),
    )

    async def fake_kakao_search(*, keyword, region, size):
        assert (keyword, region, size) == ("한식", "건대", 5)
        return [
            KakaoPlace(
                kakao_place_id=str(index),
                name=f"한식당 {index}",
                address=f"서울 광진구 예시로 {index}",
                category="음식점 > 한식",
                place_url=f"https://place.map.kakao.com/{index}",
                latitude=37.54,
                longitude=127.07,
            )
            for index in range(1, 4)
        ]

    monkeypatch.setattr(l_candidate_place_search, "kakao_search", fake_kakao_search)

    rank_result = n_candidate_ranker._EvaluationResult.model_validate(
        {
            "evaluations": [
                {
                    "kakao_place_id": str(index),
                    "context_relation": "DIRECT",
                    "preference_relations": [
                        {
                            "user_id": 1,
                            "vocabulary_code": "KOREAN_FOOD",
                            "relation": "DIRECT" if index == 2 else "PARTIAL",
                        }
                    ],
                    "reasons": ["저녁 식사 목적에 맞는 한식당입니다."],
                    "tags": ["GOOD_FOR_MEAL"],
                }
                for index in range(1, 4)
            ]
        }
    )

    class _RankStructuredLLM:
        async def ainvoke(self, _messages):
            return {"raw": None, "parsed": rank_result, "parsing_error": None}

    class _RankLLM:
        def with_structured_output(self, _schema, *, include_raw=False):
            assert include_raw is True
            return _RankStructuredLLM()

    monkeypatch.setattr(n_candidate_ranker, "get_llm", lambda: _RankLLM())

    async def verify_as_pass(place, *_args):
        return n_candidate_place_verifier._to_verified_place(
            place,
            n_candidate_place_verifier._Classification(
                status="PASS",
                business_hours="매일 11:00~22:00",
                source="https://example.com/hours",
            ),
        )

    monkeypatch.setattr(n_candidate_place_verifier, "_verify_one", verify_as_pass)

    async def fake_fetch_vocabulary():
        return [
            VocabularyEntry(
                code="KOREAN_FOOD",
                domain="FOOD",
                display_name="한식",
                parent_code=None,
            )
        ]

    monkeypatch.setattr(
        l_candidate_suggestion_builder,
        "fetch_vocabulary",
        fake_fetch_vocabulary,
    )

    graph = build_candidates_graph.build_candidates_graph()
    result = asyncio.run(
        graph.ainvoke(
            {
                "meeting": MeetingInput(id=20, purpose="조용한 저녁 식사", region="건대"),
                "confirmed_slot": ConfirmedSlot(
                    confirmed_start_at=datetime(2026, 8, 30, 9, 0, tzinfo=UTC),
                    confirmed_end_at=datetime(2026, 8, 30, 11, 0, tzinfo=UTC),
                ),
                "participants": [
                    ParticipantInput.model_validate(
                        {
                            "userId": 1,
                            "preferences": [
                                {
                                    "vocabularyCode": "KOREAN_FOOD",
                                    "sentiment": "POSITIVE",
                                    "strength": "MODERATE",
                                    "rawValue": "한식이 좋아",
                                }
                            ],
                        }
                    )
                ],
                "meeting_memory_summary": None,
                "excluded_external_place_ids": [],
            }
        )
    )

    assert [suggestion.external_place_id for suggestion in result["suggestions"]] == [
        "2",
        "1",
        "3",
    ]
    assert all(
        suggestion.business_hours_verified for suggestion in result["suggestions"]
    )
    assert result["search_metrics"]["selectedCandidateCount"] == 3
    assert result["verification_metrics"]["attemptedCandidateCount"] == 3
