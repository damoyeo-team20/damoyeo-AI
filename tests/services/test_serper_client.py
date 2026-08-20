import asyncio
from types import SimpleNamespace

import pytest

from app.core.errors import AIServiceError
from app.services import serper_client


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
    """실제 httpx.AsyncClient 대신 생성자 kwargs와 POST 인자를 기록한다."""

    last_post_kwargs: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.last_post_kwargs = {"url": url, "headers": headers, "json": json}
        return _FakeResponse(
            200,
            {
                "organic": [
                    {"title": "테스트 식당", "snippet": "매일 11:30~22:00", "link": "https://example.com"}
                ]
            },
        )


def test_search_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        serper_client, "get_settings", lambda: SimpleNamespace(serper_api_key="")
    )

    with pytest.raises(AIServiceError) as exc:
        asyncio.run(serper_client.search("테스트 식당 영업시간"))

    assert exc.value.code == "SERPER_API_KEY_MISSING"


def test_search_sends_api_key_header_and_parses_organic(monkeypatch):
    monkeypatch.setattr(
        serper_client, "get_settings", lambda: SimpleNamespace(serper_api_key="test-key")
    )

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    results = asyncio.run(serper_client.search("테스트 식당 영업시간"))

    assert _FakeAsyncClient.last_post_kwargs["headers"]["X-API-KEY"] == "test-key"
    assert _FakeAsyncClient.last_post_kwargs["json"]["q"] == "테스트 식당 영업시간"
    assert len(results) == 1
    assert results[0].title == "테스트 식당"
    assert results[0].link == "https://example.com"


def test_search_raises_service_error_on_http_failure(monkeypatch):
    monkeypatch.setattr(
        serper_client, "get_settings", lambda: SimpleNamespace(serper_api_key="test-key")
    )

    class _FailingClient(_FakeAsyncClient):
        async def post(self, url, headers=None, json=None):
            import httpx

            request = httpx.Request("POST", url)
            raise httpx.ConnectError("연결 실패", request=request)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)

    with pytest.raises(AIServiceError) as exc:
        asyncio.run(serper_client.search("테스트 식당 영업시간"))

    assert exc.value.code == "SEARCH_PROVIDER_ERROR"
    assert exc.value.retryable is True
