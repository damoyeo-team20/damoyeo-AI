"""Candidate Place Search. Kakao Local 검색. 비-LLM 노드.

Activity Decider의 검색 계획을 병렬 실행해 넓은 후보 풀을 만든다. 검색어마다 5개를 조회하고,
검색 계획별 최대 5개·전체 최대 15개를 round-robin으로 보존한다. 공정성 계산 전에 한 계획이
후보 풀을 독점하지 않게 하며, 이미 보여준 장소와 중복 장소는 최대한 앞에서 제외한다.
"""

import asyncio

from app.graph.candidates_state import CandidatesState, PlaceCandidate, SearchPlan
from app.services.kakao_client import KakaoPlace, search_places as kakao_search

_KAKAO_RESULTS_PER_QUERY = 5
_MAX_CANDIDATES_PER_PLAN = 5
_MAX_TOTAL_CANDIDATES = 15
_MAX_CONCURRENT_SEARCHES = 4


async def _search_one(
    semaphore: asyncio.Semaphore,
    *,
    keyword: str,
    region: str,
) -> list[KakaoPlace]:
    async with semaphore:
        return await kakao_search(
            keyword=keyword,
            region=region,
            size=_KAKAO_RESULTS_PER_QUERY,
        )


def _to_candidate(plan: SearchPlan, place: KakaoPlace) -> PlaceCandidate:
    return {
        "search_plan_label": plan["label"],
        "search_plan_source": plan["source"],
        "search_plan_rationale": plan["rationale_group"],
        "kakao_place_id": place.kakao_place_id,
        "name": place.name,
        "address": place.address,
        "category": place.category,
        "place_url": place.place_url,
        "latitude": place.latitude,
        "longitude": place.longitude,
    }


def _select_balanced_candidates(
    per_plan_candidates: list[list[PlaceCandidate]],
) -> list[PlaceCandidate]:
    """계획별 한 개씩 번갈아 뽑아 다양성을 지키면서 전역 장소 중복을 제거한다."""

    selected: list[PlaceCandidate] = []
    seen_ids: set[str] = set()
    cursors = [0] * len(per_plan_candidates)
    selected_per_plan = [0] * len(per_plan_candidates)

    made_progress = True
    while len(selected) < _MAX_TOTAL_CANDIDATES and made_progress:
        made_progress = False
        for plan_index, candidates in enumerate(per_plan_candidates):
            if len(selected) >= _MAX_TOTAL_CANDIDATES:
                break
            if selected_per_plan[plan_index] >= _MAX_CANDIDATES_PER_PLAN:
                continue

            while cursors[plan_index] < len(candidates):
                candidate = candidates[cursors[plan_index]]
                cursors[plan_index] += 1
                if candidate["kakao_place_id"] in seen_ids:
                    continue
                seen_ids.add(candidate["kakao_place_id"])
                selected.append(candidate)
                selected_per_plan[plan_index] += 1
                made_progress = True
                break

    return selected


def _merge_query_candidates(
    per_query_candidates: list[list[PlaceCandidate]],
) -> list[PlaceCandidate]:
    """한 SearchPlan 안에서도 각 검색어 결과를 번갈아 배치해 첫 검색어 독점을 막는다."""

    merged: list[PlaceCandidate] = []
    seen_ids: set[str] = set()
    cursors = [0] * len(per_query_candidates)
    made_progress = True
    while made_progress:
        made_progress = False
        for query_index, candidates in enumerate(per_query_candidates):
            while cursors[query_index] < len(candidates):
                candidate = candidates[cursors[query_index]]
                cursors[query_index] += 1
                if candidate["kakao_place_id"] in seen_ids:
                    continue
                seen_ids.add(candidate["kakao_place_id"])
                merged.append(candidate)
                made_progress = True
                break
    return merged


async def search_places(state: CandidatesState) -> dict:
    region = state["meeting"].region
    excluded = set(state.get("excluded_external_place_ids", []))
    search_plans = state.get("search_plans", [])
    if not search_plans:
        return {
            "place_candidates": [],
            "search_metrics": {
                "searchPlanCount": 0,
                "queryCount": 0,
                "rawKakaoCandidateCount": 0,
                "deduplicatedCandidateCount": 0,
                "selectedCandidateCount": 0,
            },
        }

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SEARCHES)
    query_specs = [
        (plan_index, query)
        for plan_index, plan in enumerate(search_plans)
        for query in plan["search_queries"]
    ]
    query_results = await asyncio.gather(
        *(
            _search_one(semaphore, keyword=query, region=region)
            for _, query in query_specs
        )
    )

    per_plan_query_candidates: list[list[list[PlaceCandidate]]] = [
        [] for _ in search_plans
    ]
    raw_count = 0
    for (plan_index, _), places in zip(query_specs, query_results, strict=True):
        plan = search_plans[plan_index]
        raw_count += len(places)
        query_candidates: list[PlaceCandidate] = []
        for place in places:
            place_id = place.kakao_place_id
            if place_id in excluded:
                continue
            query_candidates.append(_to_candidate(plan, place))
        per_plan_query_candidates[plan_index].append(query_candidates)

    per_plan_candidates = [
        _merge_query_candidates(query_candidates)
        for query_candidates in per_plan_query_candidates
    ]

    selected = _select_balanced_candidates(per_plan_candidates)
    deduplicated_count = len(
        {
            candidate["kakao_place_id"]
            for candidates in per_plan_candidates
            for candidate in candidates
        }
    )
    return {
        "place_candidates": selected,
        "search_metrics": {
            "searchPlanCount": len(search_plans),
            "queryCount": len(query_specs),
            "rawKakaoCandidateCount": raw_count,
            "deduplicatedCandidateCount": deduplicated_count,
            "selectedCandidateCount": len(selected),
        },
    }
