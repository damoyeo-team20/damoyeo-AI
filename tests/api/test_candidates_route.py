from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.routes import meetings
from app.main import app
from app.schemas.candidates import (
    ActionRequired,
    ActionRequiredType,
    PlaceProvider,
    Suggestion,
    Tag,
)

client = TestClient(app)


def _payload(**overrides):
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


def _stub_graph(monkeypatch, result):
    class _Graph:
        async def ainvoke(self, state):
            self.state = state
            return result

    graph = _Graph()
    monkeypatch.setattr(meetings, "get_candidates_graph", lambda: graph)
    return graph


def _suggestion():
    return Suggestion(
        rank=1,
        category="한식",
        place_provider=PlaceProvider.KAKAO,
        external_place_id="12345678",
        name="건대 예시 한식당",
        address="서울 광진구 예시로 1",
        latitude=37.5401,
        longitude=127.0692,
        external_url="https://place.map.kakao.com/12345678",
        proposed_start_at=datetime(2026, 8, 30, 18, 0, tzinfo=UTC),
        proposed_end_at=datetime(2026, 8, 30, 20, 0, tzinfo=UTC),
        business_hours="매일 11:30~22:00",
        business_hours_verified=True,
        open_at_meeting_time=True,
        reasons=["대화하기 좋아요."],
    )


def test_ok_response_echoes_request_id_and_applied_duration(monkeypatch):
    _stub_graph(
        monkeypatch,
        {
            "suggestions": [_suggestion()],
            "summary": "대화하기 좋은 장소를 우선했어요.",
            "meeting_tags": [Tag(code="QUIET", label="차분한")],
            "verification_timed_out": False,
        },
    )

    response = client.post("/ai/meetings/20/candidates", json=_payload())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "OK"
    assert body["requestId"] == "6e214a43-56a6-4b3b-a63c-14a1d3bb3c72"
    # confirmedSlot이 18:00~20:00이므로 파생값은 120분이어야 한다.
    assert body["appliedDurationMinutes"] == 120
    assert body["suggestions"][0]["externalPlaceId"] == "12345678"
    assert body["actionRequired"] is None


def test_meeting_id_mismatch_returns_400(monkeypatch):
    _stub_graph(monkeypatch, {})

    # path는 99인데 body의 meeting.id는 20이다.
    response = client.post("/ai/meetings/99/candidates", json=_payload())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MEETING_ID_MISMATCH"


def test_empty_suggestions_becomes_no_candidate(monkeypatch):
    _stub_graph(monkeypatch, {"suggestions": [], "meeting_tags": [], "verification_timed_out": False})

    response = client.post("/ai/meetings/20/candidates", json=_payload())
    body = response.json()

    # 후보가 없는 건 시스템 오류가 아니므로 200으로 내려간다.
    assert response.status_code == 200
    assert body["status"] == "NO_CANDIDATE"
    assert body["suggestions"] == []
    assert body["actionRequired"]["type"] == "NO_CANDIDATE"


def test_conflict_is_surfaced_as_action_required(monkeypatch):
    _stub_graph(
        monkeypatch,
        {
            "action_required": ActionRequired(
                type=ActionRequiredType.PREFERENCE_CONFLICT,
                message="목적과 참여자 선호가 충돌합니다.",
                host_request="술자리",
                conflicting_preference_codes=["ALCOHOL"],
            )
        },
    )

    response = client.post("/ai/meetings/20/candidates", json=_payload())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "CONFLICT"
    assert body["actionRequired"]["hostRequest"] == "술자리"
    assert body["actionRequired"]["conflictingPreferenceCodes"] == ["ALCOHOL"]


def test_participant_preferences_are_flattened_for_the_graph(monkeypatch):
    graph = _stub_graph(monkeypatch, {"suggestions": [], "meeting_tags": []})

    participants = [
        {
            "userId": 1,
            "preferences": [
                {
                    "vocabularyCode": "SPICY_FOOD",
                    "sentiment": "POSITIVE",
                    "strength": "MODERATE",
                    "rawValue": "매운 음식",
                }
            ],
        },
        {
            "userId": 2,
            "preferences": [
                {
                    "vocabularyCode": "SEAFOOD",
                    "sentiment": "NEGATIVE",
                    "strength": "STRONG",
                    "rawValue": "해산물",
                }
            ],
        },
    ]
    client.post("/ai/meetings/20/candidates", json=_payload(participants=participants))

    # 후보 선정은 집단 수준으로만 판단하므로 참여자 구분 없이 합쳐서 넘긴다.
    codes = [p.vocabulary_code for p in graph.state["participant_preferences"]]
    assert codes == ["SPICY_FOOD", "SEAFOOD"]


def test_timeout_with_no_suggestions_returns_504_not_no_candidate(monkeypatch):
    # 검증이 하나도 안 끝난 것과 "조건에 맞는 곳이 없다"는 건 다르다.
    _stub_graph(monkeypatch, {"suggestions": [], "meeting_tags": [], "verification_timed_out": True})

    response = client.post("/ai/meetings/20/candidates", json=_payload())

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "CANDIDATE_GENERATION_TIMEOUT"
    assert response.json()["error"]["retryable"] is True


def test_timeout_with_some_suggestions_still_returns_ok(monkeypatch):
    _stub_graph(
        monkeypatch,
        {
            "suggestions": [_suggestion()],
            "meeting_tags": [],
            "verification_timed_out": True,
        },
    )

    response = client.post("/ai/meetings/20/candidates", json=_payload())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "OK"
    assert body["verificationTimedOut"] is True


def test_unverified_suggestion_uses_existing_response_fields(monkeypatch):
    suggestion = _suggestion().model_copy(
        update={
            "business_hours": None,
            "business_hours_verified": False,
            "open_at_meeting_time": None,
        }
    )
    _stub_graph(
        monkeypatch,
        {
            "suggestions": [suggestion],
            "meeting_tags": [],
            "verification_timed_out": True,
        },
    )

    response = client.post("/ai/meetings/20/candidates", json=_payload())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "OK"
    assert body["suggestions"][0]["businessHours"] is None
    assert body["suggestions"][0]["businessHoursVerified"] is False
    assert body["suggestions"][0]["openAtMeetingTime"] is None
    assert body["verificationTimedOut"] is True


def test_end_before_start_is_rejected(monkeypatch):
    _stub_graph(monkeypatch, {})

    response = client.post(
        "/ai/meetings/20/candidates",
        json=_payload(
            confirmedSlot={
                "confirmedStartAt": "2026-08-30T20:00:00+09:00",
                "confirmedEndAt": "2026-08-30T18:00:00+09:00",
            }
        ),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_SCHEMA_INVALID"
