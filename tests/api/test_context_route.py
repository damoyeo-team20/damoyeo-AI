from fastapi.testclient import TestClient

from app.api.routes import meetings
from app.main import app

client = TestClient(app)


def _stub_graph(monkeypatch, result):
    class _Graph:
        async def ainvoke(self, state):
            self.state = state
            return result

    graph = _Graph()
    monkeypatch.setattr(meetings, "get_context_graph", lambda: graph)
    return graph


def test_context_message_without_candidate_dates(monkeypatch):
    _stub_graph(monkeypatch, {"reply": "편안하게 준비할게요.", "candidate_dates": None})

    response = client.post(
        "/ai/meetings/20/context/messages",
        json={"history": [], "message": "오늘 뭐 먹을까요?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"reply": "편안하게 준비할게요.", "candidateDates": None}


def test_context_message_with_candidate_dates_round_trips_selection(monkeypatch):
    graph = _stub_graph(
        monkeypatch,
        {
            "reply": "네, 30일로 바꿔드릴게요.",
            "candidate_dates": [
                {"date": "2026-08-23", "selected": False},
                {"date": "2026-08-30", "selected": True},
            ],
        },
    )

    response = client.post(
        "/ai/meetings/20/context/messages",
        json={
            "history": [],
            "message": "30일로 바꿔줘",
            "candidateDates": [
                {"date": "2026-08-23", "selected": True},
                {"date": "2026-08-30", "selected": False},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidateDates"] == [
        {"date": "2026-08-23", "selected": False},
        {"date": "2026-08-30", "selected": True},
    ]
    assert graph.state["candidate_dates"][0].selected is True


def test_context_message_rejects_invalid_candidate_dates():
    response = client.post(
        "/ai/meetings/20/context/messages",
        json={
            "history": [],
            "message": "30일로 바꿔줘",
            "candidateDates": [{"date": "2026-08-23", "selected": False}],
        },
    )

    assert response.status_code == 422
