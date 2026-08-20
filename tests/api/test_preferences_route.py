from fastapi.testclient import TestClient

from app.api.routes import preferences
from app.main import app

client = TestClient(app)


def test_out_of_scope_internal_route_is_not_exposed_in_api_response(monkeypatch):
    class _Graph:
        async def ainvoke(self, state):
            assert state == {"message": "오늘 날씨 알려줘"}
            return {
                "route": "OUT_OF_SCOPE",
                "preferences": [],
                "assistant_reply": (
                    "좋아하거나 피하고 싶은 음식, 음주 여부, 원하는 분위기나 활동을 알려주세요."
                ),
            }

    monkeypatch.setattr(preferences, "get_preference_graph", lambda: _Graph())

    response = client.post("/ai/preferences/extract", json={"messages": ["오늘 날씨 알려줘"]})

    assert response.status_code == 200
    assert response.json() == {
        "extractedPreferences": [],
        "reply": "좋아하거나 피하고 싶은 음식, 음주 여부, 원하는 분위기나 활동을 알려주세요.",
    }
