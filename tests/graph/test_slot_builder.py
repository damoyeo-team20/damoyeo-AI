from datetime import date

import pytest

from app.core.errors import AIServiceError
from app.graph.nodes.l_schedule_slot_builder import build_slot
from app.schemas.schedule import PreferredTimeOfDay


def test_evening_slot_starts_at_window_start():
    start, end = build_slot(
        chosen_date=date(2026, 8, 30),
        preferred_time_of_day=PreferredTimeOfDay.EVENING,
        duration_minutes=120,
        timezone="Asia/Seoul",
    )

    assert start.isoformat() == "2026-08-30T18:00:00+09:00"
    assert end.isoformat() == "2026-08-30T20:00:00+09:00"


def test_duration_longer_than_window_is_rejected():
    # LATE_AFTERNOON은 15~18시로 180분이라 240분짜리 모임은 들어갈 수 없다.
    with pytest.raises(AIServiceError) as exc:
        build_slot(
            chosen_date=date(2026, 8, 30),
            preferred_time_of_day=PreferredTimeOfDay.LATE_AFTERNOON,
            duration_minutes=240,
            timezone="Asia/Seoul",
        )

    assert exc.value.code == "INVALID_DURATION_FOR_TIME_OF_DAY"
    assert exc.value.status_code == 400


def test_duration_exactly_filling_window_is_allowed():
    start, end = build_slot(
        chosen_date=date(2026, 8, 30),
        preferred_time_of_day=PreferredTimeOfDay.LATE_AFTERNOON,
        duration_minutes=180,
        timezone="Asia/Seoul",
    )

    assert start.hour == 15
    assert end.hour == 18


def test_unknown_timezone_is_rejected():
    with pytest.raises(AIServiceError) as exc:
        build_slot(
            chosen_date=date(2026, 8, 30),
            preferred_time_of_day=PreferredTimeOfDay.EVENING,
            duration_minutes=120,
            timezone="Mars/Olympus",
        )

    assert exc.value.status_code == 422
