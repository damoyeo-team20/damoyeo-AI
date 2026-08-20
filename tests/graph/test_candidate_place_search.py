import asyncio
from collections import Counter

from app.graph.nodes import l_candidate_place_search
from app.schemas.candidates import MeetingInput
from app.services.kakao_client import KakaoPlace


def _plan(
    label: str,
    queries: list[str],
    *,
    source: str = "MEETING_PURPOSE",
    rationale: str | None = None,
) -> dict:
    return {
        "label": label,
        "source": source,
        "search_queries": queries,
        "rationale_group": rationale or f"{label}을 찾는 이유",
    }


def _place(place_id: str) -> KakaoPlace:
    return KakaoPlace(
        kakao_place_id=place_id,
        name=f"장소 {place_id}",
        address=f"서울 광진구 예시로 {place_id}",
        category="음식점",
        place_url=f"https://place.map.kakao.com/{place_id}",
        latitude=37.54,
        longitude=127.07,
    )


def _places(*place_ids: str) -> list[KakaoPlace]:
    return [_place(place_id) for place_id in place_ids]


def _run_search(
    monkeypatch,
    plans: list[dict],
    responses: dict[str, list[KakaoPlace]],
    *,
    excluded: list[str] | None = None,
):
    calls: list[dict] = []

    async def fake_kakao_search(*, keyword, region, size):
        calls.append({"keyword": keyword, "region": region, "size": size})
        return list(responses[keyword])

    monkeypatch.setattr(l_candidate_place_search, "kakao_search", fake_kakao_search)
    state = {
        "meeting": MeetingInput(id=20, purpose="저녁 모임", region="건대"),
        "search_plans": plans,
        "excluded_external_place_ids": excluded or [],
    }
    return asyncio.run(l_candidate_place_search.search_places(state)), calls


def test_every_query_requests_five_kakao_results(monkeypatch):
    plans = [
        _plan("식사", ["한식", "일식"]),
        _plan("대화", ["카페"], source="PARTICIPANT_PREFERENCE"),
    ]
    responses = {"한식": [], "일식": [], "카페": []}

    _, calls = _run_search(monkeypatch, plans, responses)

    assert {call["keyword"] for call in calls} == {"한식", "일식", "카페"}
    assert all(call["region"] == "건대" for call in calls)
    assert all(call["size"] == 5 for call in calls)


def test_each_plan_is_capped_at_five_candidates_across_queries(monkeypatch):
    plans = [_plan("식사", ["한식", "일식"])]
    responses = {
        "한식": _places("1", "2", "3", "4", "5"),
        "일식": _places("6", "7", "8", "9", "10"),
    }

    result, _ = _run_search(monkeypatch, plans, responses)

    assert [place["kakao_place_id"] for place in result["place_candidates"]] == [
        "1",
        "6",
        "2",
        "7",
        "3",
    ]
    assert result["search_metrics"]["selectedCandidateCount"] == 5


def test_each_query_contributes_before_one_query_fills_the_plan_cap(monkeypatch):
    plans = [_plan("식사", ["한식", "일식", "중식"])]
    responses = {
        "한식": _places("A1", "A2", "A3", "A4", "A5"),
        "일식": _places("B1", "B2", "B3", "B4", "B5"),
        "중식": _places("C1", "C2", "C3", "C4", "C5"),
    }

    result, _ = _run_search(monkeypatch, plans, responses)

    assert [place["kakao_place_id"] for place in result["place_candidates"]] == [
        "A1",
        "B1",
        "C1",
        "A2",
        "B2",
    ]


def test_total_candidate_pool_is_capped_at_fifteen(monkeypatch):
    plans = [_plan(f"계획 {index}", [f"검색어 {index}"]) for index in range(4)]
    responses = {
        f"검색어 {index}": _places(*(f"{index}-{item}" for item in range(5)))
        for index in range(4)
    }

    result, _ = _run_search(monkeypatch, plans, responses)

    candidates = result["place_candidates"]
    assert len(candidates) == 15
    assert result["search_metrics"]["selectedCandidateCount"] == 15
    assert Counter(place["search_plan_label"] for place in candidates) == {
        "계획 0": 4,
        "계획 1": 4,
        "계획 2": 4,
        "계획 3": 3,
    }


def test_candidates_are_selected_round_robin_across_plans(monkeypatch):
    plans = [
        _plan("계획 A", ["검색어 A"]),
        _plan("계획 B", ["검색어 B"]),
        _plan("계획 C", ["검색어 C"]),
    ]
    responses = {
        "검색어 A": _places("A1", "A2"),
        "검색어 B": _places("B1", "B2"),
        "검색어 C": _places("C1", "C2"),
    }

    result, _ = _run_search(monkeypatch, plans, responses)

    assert [place["kakao_place_id"] for place in result["place_candidates"]] == [
        "A1",
        "B1",
        "C1",
        "A2",
        "B2",
        "C2",
    ]


def test_excluded_and_global_duplicates_do_not_consume_plan_caps(monkeypatch):
    plans = [
        _plan("계획 A", ["A-1", "A-2"]),
        _plan("계획 B", ["B-1", "B-2"], source="PARTICIPANT_PREFERENCE"),
    ]
    responses = {
        "A-1": _places("excluded-A", "shared", "A2", "A3", "A4"),
        "A-2": _places("A5", "A6"),
        "B-1": _places("excluded-B", "shared", "B2", "B3", "B4"),
        "B-2": _places("B5", "B6"),
    }

    result, _ = _run_search(
        monkeypatch,
        plans,
        responses,
        excluded=["excluded-A", "excluded-B"],
    )

    candidates = result["place_candidates"]
    ids = [place["kakao_place_id"] for place in candidates]
    assert len(candidates) == 10
    assert "excluded-A" not in ids
    assert "excluded-B" not in ids
    assert ids.count("shared") == 1
    assert Counter(place["search_plan_label"] for place in candidates) == {
        "계획 A": 5,
        "계획 B": 5,
    }


def test_candidate_keeps_originating_plan_metadata_and_reports_metrics(monkeypatch):
    plans = [
        _plan("목적 계획", ["목적-1", "목적-2"], rationale="모임 목적에서 나온 계획"),
        _plan(
            "선호 계획",
            ["선호-1"],
            source="PARTICIPANT_PREFERENCE",
            rationale="참여자 선호에서 나온 계획",
        ),
    ]
    responses = {
        "목적-1": _places("excluded", "1", "1", "2", "shared"),
        "목적-2": _places("2", "3"),
        "선호-1": _places("shared", "4"),
    }

    result, _ = _run_search(monkeypatch, plans, responses, excluded=["excluded"])

    candidates = result["place_candidates"]
    by_id = {place["kakao_place_id"]: place for place in candidates}
    assert by_id["1"]["search_plan_label"] == "목적 계획"
    assert by_id["1"]["search_plan_source"] == "MEETING_PURPOSE"
    assert by_id["1"]["search_plan_rationale"] == "모임 목적에서 나온 계획"
    assert by_id["shared"]["search_plan_label"] == "선호 계획"
    assert by_id["shared"]["search_plan_source"] == "PARTICIPANT_PREFERENCE"
    assert by_id["shared"]["search_plan_rationale"] == "참여자 선호에서 나온 계획"
    assert result["search_metrics"] == {
        "searchPlanCount": 2,
        "queryCount": 3,
        "rawKakaoCandidateCount": 9,
        "deduplicatedCandidateCount": 5,
        "selectedCandidateCount": 5,
    }


def test_no_search_plans_returns_empty_pool_and_zero_metrics(monkeypatch):
    result, calls = _run_search(monkeypatch, [], {})

    assert calls == []
    assert result == {
        "place_candidates": [],
        "search_metrics": {
            "searchPlanCount": 0,
            "queryCount": 0,
            "rawKakaoCandidateCount": 0,
            "deduplicatedCandidateCount": 0,
            "selectedCandidateCount": 0,
        },
    }
