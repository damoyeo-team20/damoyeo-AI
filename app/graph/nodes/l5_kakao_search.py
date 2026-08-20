"""L5 Kakao Local 검색. 비-LLM 노드.

N4가 결정한 활동별 검색어(들)로 Kakao Local API를 호출하고, 중복 제거 후 활동별 상위 N개를 남긴다.
"""

from app.graph.state import CandidatesState, PlaceCandidate
from app.services.kakao_client import search_places as kakao_search

_TOP_N_PER_ACTIVITY = 3


async def search_places(state: CandidatesState) -> dict:
    region = state["region"]
    place_candidates: list[PlaceCandidate] = []
    seen_ids: set[str] = set()

    for activity_plan in state.get("activities", []):
        activity_places: list[PlaceCandidate] = []
        for query in activity_plan["search_queries"]:
            places = await kakao_search(keyword=query, region=region, size=_TOP_N_PER_ACTIVITY)
            for place in places:
                if place.kakao_place_id in seen_ids:
                    continue
                seen_ids.add(place.kakao_place_id)
                activity_places.append(
                    {
                        "activity": activity_plan["activity"],
                        "kakao_place_id": place.kakao_place_id,
                        "name": place.name,
                        "address": place.address,
                        "category": place.category,
                        "place_url": place.place_url,
                    }
                )
        place_candidates.extend(activity_places[:_TOP_N_PER_ACTIVITY])

    return {"place_candidates": place_candidates}
