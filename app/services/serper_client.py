"""Serper(https://serper.dev) 검색 API 클라이언트.

candidates 파이프라인의 Place Verifier 노드가 영업시간/휴무일을 웹 검색으로 확인할 때 쓴다.
Gemini의 `google_search` grounding 도구는 일반 텍스트 생성과 별도의 빡빡한 할당량이 걸려 있어서,
검색만 이 서비스로 분리했다 — 판정(구조화 출력)은 계속 일반 Gemini 호출로 한다.
"""

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AIServiceError

_SEARCH_URL = "https://google.serper.dev/search"


class SerperResult(BaseModel):
    title: str
    snippet: str
    link: str


async def search(query: str, num: int = 5) -> list[SerperResult]:
    settings = get_settings()
    if not settings.serper_api_key:
        raise AIServiceError(
            code="SERPER_API_KEY_MISSING",
            message="SERPER_API_KEY가 설정되어 있지 않습니다.",
            status_code=500,
            # 설정 문제라 같은 요청을 재시도해도 결과가 바뀌지 않는다.
            retryable=False,
        )

    headers = {"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"}
    # gl(국가)/hl(언어)을 한국으로 고정 — 국내 상호명 검색이라 기본값(미국)으로 두면 정확도가 떨어진다.
    payload = {"q": query, "num": num, "gl": "kr", "hl": "ko"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(_SEARCH_URL, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIServiceError(
                code="SEARCH_PROVIDER_ERROR",
                message=f"Serper 검색 API 호출 실패: {exc}",
                status_code=502,
                retryable=True,
            ) from exc

    organic = response.json().get("organic", [])
    return [
        SerperResult(
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
            link=item.get("link", ""),
        )
        for item in organic[:num]
    ]
