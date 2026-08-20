import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.graph.nodes import n7_ranker_explainer
from app.schemas.candidates import ConfirmedSlot, MeetingInput, ParticipantPreference
from app.schemas.preference import Sentiment, Strength
from app.services.vocabulary_client import VocabularyEntry

_START = datetime(2026, 8, 30, 18, 0, tzinfo=UTC)
_END = datetime(2026, 8, 30, 20, 0, tzinfo=UTC)


def _place(place_id: str, status: str, **overrides):
    place = {
        "activity": "저녁 식사",
        "kakao_place_id": place_id,
        "name": f"장소 {place_id}",
        "address": "서울 광진구 예시로 1",
        "category": "한식",
        "place_url": f"https://place.map.kakao.com/{place_id}",
        "latitude": 37.5401,
        "longitude": 127.0692,
        "verification_status": status,
        "business_hours": "매일 11:30~22:00",
        "verification_source": "https://example.com/hours",
        "checked_at": datetime(2026, 8, 20, 3, 11, tzinfo=UTC),
    }
    place.update(overrides)
    return place


def _state(places):
    return {
        "meeting": MeetingInput.model_validate(
            {
                "id": 20,
                "purpose": "조용한 저녁 식사",
                "region": "건대",
            }
        ),
        "confirmed_slot": ConfirmedSlot(confirmed_start_at=_START, confirmed_end_at=_END),
        "participant_preferences": [
            ParticipantPreference(
                vocabulary_code="SPICY_FOOD",
                sentiment=Sentiment.POSITIVE,
                strength=Strength.MODERATE,
                raw_value="매운 음식",
            )
        ],
        "activities": [
            {"activity": "저녁 식사", "search_queries": ["한식"], "rationale_group": "대화 중심"}
        ],
        "verified_places": places,
    }


def _run(monkeypatch, places, ranked):
    class _StructuredLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(ranked=ranked)

    class _LLM:
        def with_structured_output(self, _schema):
            return _StructuredLLM()

    async def fake_fetch_vocabulary():
        return [
            VocabularyEntry(code="SPICY_FOOD", domain="FOOD", display_name="매운 음식", parent_code=None)
        ]

    monkeypatch.setattr(n7_ranker_explainer, "get_llm", lambda: _LLM())
    monkeypatch.setattr(n7_ranker_explainer, "fetch_vocabulary", fake_fetch_vocabulary)

    return asyncio.run(n7_ranker_explainer.rank_and_explain(_state(places)))["suggestions"]


def test_pass_place_gets_availability_tag_and_open_flag(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "PASS")],
        [
            SimpleNamespace(
                kakao_place_id="1",
                reasons=["대화하기 좋아요."],
                matched_preference_codes=["SPICY_FOOD"],
                tags=["HIGH_GROUP_FIT"],
            )
        ],
    )

    assert len(suggestions) == 1
    codes = [t.code for t in suggestions[0].tags]
    assert "AVAILABLE_AT_MEETING_TIME" in codes
    assert suggestions[0].open_at_meeting_time is True
    assert suggestions[0].business_hours_verified is True


def test_unknown_place_is_kept_but_not_claimed_open(monkeypatch):
    # UNKNOWN을 PASS로 단정하면 확인되지 않은 사실을 사용자에게 주장하게 된다.
    suggestions = _run(
        monkeypatch,
        [_place("1", "UNKNOWN")],
        [
            SimpleNamespace(
                kakao_place_id="1",
                reasons=["분위기가 조용해요."],
                matched_preference_codes=[],
                tags=[],
            )
        ],
    )

    assert len(suggestions) == 1
    assert [t.code for t in suggestions[0].tags] == []
    assert suggestions[0].open_at_meeting_time is None
    assert suggestions[0].business_hours_verified is False


def test_failed_place_is_dropped(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "FAIL")],
        [
            SimpleNamespace(
                kakao_place_id="1",
                reasons=["폐업한 곳"],
                matched_preference_codes=[],
                tags=[],
            )
        ],
    )

    assert suggestions == []


def test_hallucinated_place_and_preference_codes_are_dropped(monkeypatch):
    suggestions = _run(
        monkeypatch,
        [_place("1", "PASS")],
        [
            SimpleNamespace(
                kakao_place_id="does-not-exist",
                reasons=["지어낸 장소"],
                matched_preference_codes=[],
                tags=[],
            ),
            SimpleNamespace(
                kakao_place_id="1",
                reasons=["실제 장소"],
                matched_preference_codes=["SPICY_FOOD", "NEVER_REQUESTED"],
                tags=[],
            ),
        ],
    )

    assert len(suggestions) == 1
    assert suggestions[0].external_place_id == "1"
    # 요청에 없던 코드는 domain으로 변환되지 않는다.
    assert suggestions[0].matched_preference_domains == ["FOOD"]


def test_rank_is_sequential_from_one(monkeypatch):
    places = [_place("1", "PASS"), _place("2", "PASS"), _place("3", "PASS"), _place("4", "PASS")]
    ranked = [
        SimpleNamespace(
            kakao_place_id=str(i), reasons=["이유"], matched_preference_codes=[], tags=[]
        )
        for i in range(1, 5)
    ]

    suggestions = _run(monkeypatch, places, ranked)

    # 최대 3개까지만 반환하고 rank는 1부터 끊김 없이 증가한다.
    assert [s.rank for s in suggestions] == [1, 2, 3]
