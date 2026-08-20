import pytest
from pydantic import ValidationError

from app.schemas.candidates import CandidatesRequest


def _request(**overrides):
    payload = {
        "contractVersion": "1.0",
        "requestId": "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72",
        "meeting": {
            "id": 20,
            "purpose": "오랜만에 만나 조용한 곳에서 대화하는 저녁 식사",
            "region": "건대",
        },
        "confirmedSlot": {
            "confirmedStartAt": "2026-08-30T18:00:00+09:00",
            "confirmedEndAt": "2026-08-30T20:00:00+09:00",
        },
        "participants": [{"userId": 1, "preferences": []}],
        "meetingMemory": None,
        "excludedExternalPlaceIds": [],
    }
    payload.update(overrides)
    return payload


def test_request_parses_camel_case_contract():
    request = CandidatesRequest.model_validate(_request())

    assert request.meeting.region == "건대"
    assert request.confirmed_slot.confirmed_start_at.hour == 18


def test_confirmed_slot_duration_is_derived_from_start_and_end():
    request = CandidatesRequest.model_validate(_request())

    assert request.confirmed_slot.duration_minutes == 120


def test_confirmed_slot_date_str_uses_local_calendar_date():
    request = CandidatesRequest.model_validate(_request())

    assert request.confirmed_slot.date_str == "2026-08-30"


def test_duplicate_user_ids_are_rejected():
    with pytest.raises(ValidationError):
        CandidatesRequest.model_validate(
            _request(
                participants=[{"userId": 1, "preferences": []}, {"userId": 1, "preferences": []}]
            )
        )


def test_duplicate_preference_codes_for_one_user_are_rejected():
    duplicated = {
        "userId": 1,
        "preferences": [
            {
                "vocabularyCode": "SPICY_FOOD",
                "sentiment": "POSITIVE",
                "strength": "MODERATE",
                "rawValue": "매운 음식",
            },
            {
                "vocabularyCode": "SPICY_FOOD",
                "sentiment": "NEGATIVE",
                "strength": "WEAK",
                "rawValue": "매운 거",
            },
        ],
    }
    with pytest.raises(ValidationError):
        CandidatesRequest.model_validate(_request(participants=[duplicated]))


def test_duplicate_excluded_place_ids_are_rejected():
    with pytest.raises(ValidationError):
        CandidatesRequest.model_validate(_request(excludedExternalPlaceIds=["1", "1"]))


def test_confirmed_slot_end_before_start_is_rejected():
    with pytest.raises(ValidationError):
        CandidatesRequest.model_validate(
            _request(
                confirmedSlot={
                    "confirmedStartAt": "2026-08-30T20:00:00+09:00",
                    "confirmedEndAt": "2026-08-30T18:00:00+09:00",
                }
            )
        )
