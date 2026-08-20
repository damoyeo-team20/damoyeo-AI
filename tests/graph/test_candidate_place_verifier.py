import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.graph.nodes import n_candidate_place_verifier
from app.schemas.candidates import ConfirmedSlot
from app.services.serper_client import SerperResult


def _place(place_id: str):
    return {
        "search_plan_label": "카페",
        "search_plan_source": "MEETING_PURPOSE",
        "search_plan_rationale": "대화하기 좋은 카페",
        "kakao_place_id": place_id,
        "name": f"장소 {place_id}",
        "address": "서울 광진구 예시로 1",
        "category": "카페",
        "place_url": f"https://place.map.kakao.com/{place_id}",
        "latitude": 37.5401,
        "longitude": 127.0692,
    }


def _ranked(place_id: str):
    return {
        "place": _place(place_id),
        "context_relation": "DIRECT",
        "participant_satisfaction": {1: 0.5},
        "group_satisfaction": 0.5,
        "minimum_satisfaction": 0.5,
        "fairness_score": 50.0,
        "matched_preference_codes": [],
        "reasons": ["모임 목적에 적합합니다."],
        "tags": [],
        "original_index": int(place_id) - 1,
    }


def _slot():
    return ConfirmedSlot(
        confirmed_start_at=datetime(2026, 8, 30, 18, 0, tzinfo=UTC),
        confirmed_end_at=datetime(2026, 8, 30, 20, 0, tzinfo=UTC),
    )


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


def test_pass_without_hours_or_allowed_source_is_downgraded_to_unknown():
    result = n_candidate_place_verifier._normalize_classification(
        n_candidate_place_verifier._Classification(
            status="PASS",
            business_hours=None,
            source="https://hallucinated.example/hours",
        ),
        [
            SerperResult(
                title="공식 영업정보",
                snippet="매일 11:00~22:00",
                link="https://official.example/hours",
            )
        ],
    )

    assert result.status == "UNKNOWN"
    assert result.business_hours is None
    assert result.source is None


def test_pass_with_hours_and_serper_source_is_preserved():
    source = "https://official.example/hours"
    result = n_candidate_place_verifier._normalize_classification(
        n_candidate_place_verifier._Classification(
            status="PASS",
            business_hours="매일 11:00~22:00",
            source=source,
        ),
        [SerperResult(title="공식 영업정보", snippet="영업시간", link=source)],
    )

    assert result.status == "PASS"
    assert result.business_hours == "매일 11:00~22:00"
    assert result.source == source


def test_timed_out_verification_keeps_place_as_unknown(monkeypatch):
    async def never_finishes(*_args):
        await asyncio.sleep(60)

    monkeypatch.setattr(n_candidate_place_verifier, "_verify_one", never_finishes)
    monkeypatch.setattr(n_candidate_place_verifier, "_OVERALL_TIMEOUT_SECONDS", 0.001)

    state = {
        "ranked_candidates": [_ranked("1")],
        "confirmed_slot": _slot(),
    }

    result = asyncio.run(n_candidate_place_verifier.verify_places(state))

    assert result["verification_timed_out"] is True
    assert len(result["verified_places"]) == 1
    verified = result["verified_places"][0]
    assert verified["kakao_place_id"] == "1"
    assert verified["verification_status"] == "UNKNOWN"
    assert verified["business_hours"] is None
    assert verified["verification_source"] is None


@pytest.mark.parametrize(
    ("start_at", "end_at", "expected"),
    [
        (
            datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
            datetime(2026, 8, 21, 11, 0, tzinfo=UTC),
            {"date": "2026-08-21", "start_time": "18:00", "end_time": "20:00"},
        ),
        (
            datetime(2026, 8, 21, 18, 0, tzinfo=timezone(timedelta(hours=9))),
            datetime(2026, 8, 21, 20, 0, tzinfo=timezone(timedelta(hours=9))),
            {"date": "2026-08-21", "start_time": "18:00", "end_time": "20:00"},
        ),
        (
            datetime(2026, 8, 20, 16, 0, tzinfo=UTC),
            datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
            {"date": "2026-08-21", "start_time": "01:00", "end_time": "03:00"},
        ),
    ],
)
def test_slot_is_converted_to_seoul_time_before_verification(
    monkeypatch,
    start_at,
    end_at,
    expected,
):
    received: dict[str, str] = {}

    async def capture_local_time(place, date, start_time, end_time):
        received.update(date=date, start_time=start_time, end_time=end_time)
        return n_candidate_place_verifier._to_verified_place(
            place,
            n_candidate_place_verifier._Classification(status="UNKNOWN"),
        )

    monkeypatch.setattr(n_candidate_place_verifier, "_verify_one", capture_local_time)

    state = {
        "ranked_candidates": [_ranked("1")],
        "confirmed_slot": ConfirmedSlot(
            confirmed_start_at=start_at,
            confirmed_end_at=end_at,
        ),
    }

    asyncio.run(n_candidate_place_verifier.verify_places(state))

    assert received == expected


def test_initial_six_are_verified_and_fallback_is_not_called_when_usable(monkeypatch):
    called: list[str] = []

    async def verify_as_unknown(place, *_args):
        called.append(place["kakao_place_id"])
        return n_candidate_place_verifier._to_verified_place(
            place,
            n_candidate_place_verifier._Classification(status="UNKNOWN"),
        )

    monkeypatch.setattr(n_candidate_place_verifier, "_verify_one", verify_as_unknown)
    state = {
        "ranked_candidates": [_ranked(str(index)) for index in range(1, 10)],
        "confirmed_slot": _slot(),
    }

    result = asyncio.run(n_candidate_place_verifier.verify_places(state))

    assert called == ["1", "2", "3", "4", "5", "6"]
    assert [place["kakao_place_id"] for place in result["verified_places"]] == called
    assert result["verification_metrics"] == {
        "rankedCandidateCount": 9,
        "attemptedCandidateCount": 6,
        "usableCandidateCount": 6,
    }


def test_followup_batches_continue_until_three_usable(monkeypatch):
    called: list[str] = []

    async def verify_with_failures(place, *_args):
        place_id = place["kakao_place_id"]
        called.append(place_id)
        status = "PASS" if place_id in {"6", "7", "13"} else "FAIL"
        return n_candidate_place_verifier._to_verified_place(
            place,
            n_candidate_place_verifier._Classification(status=status),
        )

    monkeypatch.setattr(n_candidate_place_verifier, "_verify_one", verify_with_failures)
    state = {
        "ranked_candidates": [_ranked(str(index)) for index in range(1, 16)],
        "confirmed_slot": _slot(),
    }

    result = asyncio.run(n_candidate_place_verifier.verify_places(state))

    assert called == [str(index) for index in range(1, 16)]
    assert [place["kakao_place_id"] for place in result["verified_places"]] == called
    assert result["verification_metrics"] == {
        "rankedCandidateCount": 15,
        "attemptedCandidateCount": 15,
        "usableCandidateCount": 3,
    }


def test_two_batches_share_one_timeout_budget(monkeypatch):
    received_timeouts: list[float] = []

    async def capture_batch(places, *, date, start_time, end_time, timeout):
        del date, start_time, end_time
        received_timeouts.append(timeout)
        await asyncio.sleep(0.001)
        return [
            n_candidate_place_verifier._to_verified_place(
                place,
                n_candidate_place_verifier._Classification(status="FAIL"),
            )
            for place in places
        ], False

    monkeypatch.setattr(n_candidate_place_verifier, "_verify_batch", capture_batch)
    state = {
        "ranked_candidates": [_ranked(str(index)) for index in range(1, 10)],
        "confirmed_slot": _slot(),
    }

    asyncio.run(n_candidate_place_verifier.verify_places(state))

    assert len(received_timeouts) == 2
    assert received_timeouts[0] <= n_candidate_place_verifier._OVERALL_TIMEOUT_SECONDS
    assert received_timeouts[1] < received_timeouts[0]


def test_empty_ranked_candidates_skip_verification():
    result = asyncio.run(
        n_candidate_place_verifier.verify_places(
            {"ranked_candidates": [], "confirmed_slot": _slot()}
        )
    )

    assert result == {
        "verified_places": [],
        "verification_timed_out": False,
        "verification_metrics": {
            "rankedCandidateCount": 0,
            "attemptedCandidateCount": 0,
            "usableCandidateCount": 0,
        },
    }
