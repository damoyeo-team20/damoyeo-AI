import pytest
from pydantic import ValidationError

from app.schemas.schedule import DEFAULT_DURATION_MINUTES, ScheduleRequest


def _request(**overrides):
    payload = {
        "commonAvailableDates": ["2026-08-23", "2026-08-30"],
        "preferredTimeOfDay": "EVENING",
        "durationMinutes": 120,
        "timezone": "Asia/Seoul",
    }
    payload.update(overrides)
    return payload


def test_request_parses_camel_case_contract():
    request = ScheduleRequest.model_validate(_request())

    assert [d.isoformat() for d in request.common_available_dates] == [
        "2026-08-23",
        "2026-08-30",
    ]
    assert request.applied_duration_minutes == 120


def test_null_duration_falls_back_to_default():
    request = ScheduleRequest.model_validate(_request(durationMinutes=None))

    assert request.applied_duration_minutes == DEFAULT_DURATION_MINUTES


def test_duplicate_dates_are_rejected():
    with pytest.raises(ValidationError):
        ScheduleRequest.model_validate(
            _request(commonAvailableDates=["2026-08-23", "2026-08-23"])
        )


def test_empty_dates_are_rejected():
    with pytest.raises(ValidationError):
        ScheduleRequest.model_validate(_request(commonAvailableDates=[]))
