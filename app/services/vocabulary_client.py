"""Back이 호스팅하는 `GET /internal/preference-vocabulary` 클라이언트.

AI 서버 기동 시 1회 호출해 인메모리에 캐싱한다 (ai-part-proposal.md 6장 기준).

AI는 DB를 직접 소유하지 않는다 — Vocabulary는 항상 이 클라이언트를 통해 Back의 HTTP
엔드포인트에서 가져온다.
"""

import httpx

from app.core.config import get_settings
from app.core.errors import AIServiceError
from app.schemas.vocabulary import VocabularyEntry

_cache: list[VocabularyEntry] | None = None


async def fetch_vocabulary(force_refresh: bool = False) -> list[VocabularyEntry]:
    global _cache
    if _cache is not None and not force_refresh:
        return _cache

    settings = get_settings()
    # 헤더 이름은 Back 소스로 확인된 게 아니라 응답 코드 차이(다른 이름은 401, 이 이름은 400)로
    # 추정한 값이다 — Back 팀 확인 전까지는 최종 확정이 아니다.
    headers = {"X-Internal-Api-Key": settings.internal_api_key}
    try:
        async with httpx.AsyncClient(
            base_url=settings.backend_api_base_url, timeout=10.0, headers=headers
        ) as client:
            response = await client.get("/internal/preference-vocabulary")
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise AIServiceError(
            code="VOCABULARY_UNAVAILABLE",
            message=f"Vocabulary 조회 실패: {exc}",
            status_code=503,
            retryable=True,
        ) from exc

    _cache = [VocabularyEntry.model_validate(item) for item in payload["vocabulary"]]
    return _cache


def clear_cache() -> None:
    """테스트 및 수동 갱신용."""
    global _cache
    _cache = None
