import asyncio
from types import SimpleNamespace

import pytest

from app.core.errors import AIServiceError
from app.services import vocabulary_client


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """실제 httpx.AsyncClient 대신 생성자 kwargs(headers 포함)와 요청을 기록한다."""

    last_init_kwargs: dict | None = None

    def __init__(self, *args, **kwargs):
        _FakeAsyncClient.last_init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, path):
        return _FakeResponse(200, {"vocabulary": []})


@pytest.fixture(autouse=True)
def _reset_cache():
    vocabulary_client.clear_cache()
    yield
    vocabulary_client.clear_cache()


def test_fetch_vocabulary_sends_internal_api_key_header(monkeypatch):
    fake_settings = SimpleNamespace(
        backend_api_base_url="http://backend:8080", internal_api_key="test-secret"
    )
    monkeypatch.setattr(vocabulary_client, "get_settings", lambda: fake_settings)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    asyncio.run(vocabulary_client.fetch_vocabulary())

    # Back이 401로 막는 헤더 이름이므로, 조용히 빠지면 회귀다.
    sent_headers = _FakeAsyncClient.last_init_kwargs["headers"]
    assert sent_headers == {"X-Internal-Api-Key": "test-secret"}


def test_fetch_vocabulary_raises_service_error_on_http_failure(monkeypatch):
    class _FailingClient(_FakeAsyncClient):
        async def get(self, path):
            import httpx

            request = httpx.Request("GET", "http://backend/internal/preference-vocabulary")
            raise httpx.ConnectError("연결 실패", request=request)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)

    with pytest.raises(AIServiceError) as exc:
        asyncio.run(vocabulary_client.fetch_vocabulary())

    assert exc.value.code == "VOCABULARY_UNAVAILABLE"
    assert exc.value.retryable is True
