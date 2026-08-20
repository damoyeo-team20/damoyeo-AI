import asyncio
from datetime import UTC, datetime

from app.graph.nodes import n_candidate_place_verifier
from app.schemas.candidates import ConfirmedSlot


def _place(place_id: str):
    return {
        "activity": "카페",
        "kakao_place_id": place_id,
        "name": f"장소 {place_id}",
        "address": "서울 광진구 예시로 1",
        "category": "카페",
        "place_url": f"https://place.map.kakao.com/{place_id}",
        "latitude": 37.5401,
        "longitude": 127.0692,
    }


def test_search_failure_keeps_place_as_unknown(monkeypatch):
    class _Settings:
        skip_business_hours_verification = False

    async def search_fails(_query):
        raise RuntimeError("검색 실패")

    monkeypatch.setattr(n_candidate_place_verifier, "get_settings", lambda: _Settings())
    monkeypatch.setattr(n_candidate_place_verifier, "serper_search", search_fails)

    verified = asyncio.run(
        n_candidate_place_verifier._verify_one(_place("1"), "2026-08-30", "18:00", "20:00")
    )

    assert verified["kakao_place_id"] == "1"
    assert verified["verification_status"] == "UNKNOWN"
    assert verified["business_hours"] is None
    assert verified["verification_source"] is None


def test_timed_out_verification_keeps_place_as_unknown(monkeypatch):
    async def never_finishes(*_args):
        await asyncio.sleep(60)

    monkeypatch.setattr(n_candidate_place_verifier, "_verify_one", never_finishes)
    monkeypatch.setattr(n_candidate_place_verifier, "_OVERALL_TIMEOUT_SECONDS", 0.001)

    place = _place("1")
    state = {
        "place_candidates": [place],
        "confirmed_slot": ConfirmedSlot(
            confirmed_start_at=datetime(2026, 8, 30, 18, 0, tzinfo=UTC),
            confirmed_end_at=datetime(2026, 8, 30, 20, 0, tzinfo=UTC),
        ),
    }

    result = asyncio.run(n_candidate_place_verifier.verify_places(state))

    assert result["verification_timed_out"] is True
    assert len(result["verified_places"]) == 1
    verified = result["verified_places"][0]
    assert verified["kakao_place_id"] == "1"
    assert verified["verification_status"] == "UNKNOWN"
    assert verified["business_hours"] is None
    assert verified["verification_source"] is None
