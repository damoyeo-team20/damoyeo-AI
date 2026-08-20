"""Back이 호스팅하는 `GET /internal/preference-vocabulary` 클라이언트.

AI 서버 기동 시 1회 호출해 인메모리에 캐싱한다 (ai-part-proposal.md 6장 기준).
"""

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.errors import AIServiceError


class VocabularyEntry(BaseModel):
    """`preference_vocabulary` 테이블 1행에 대응 (docs/db_schema.md).

    스키마에 `attribute` 컬럼은 없다. 계층은 `parent_code` 하나로만 표현한다.
    """

    model_config = ConfigDict(populate_by_name=True)

    code: str
    domain: str
    display_name: str = Field(alias="displayName")
    parent_code: str | None = Field(default=None, alias="parentCode")


_cache: list[VocabularyEntry] | None = None


async def fetch_vocabulary(force_refresh: bool = False) -> list[VocabularyEntry]:
    global _cache
    if _cache is not None and not force_refresh:
        return _cache

    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            base_url=settings.backend_api_base_url, timeout=10.0
        ) as client:
            response = await client.get("/internal/preference-vocabulary")
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise AIServiceError(
            code="VOCABULARY_UNAVAILABLE",
            message=f"Vocabulary 조회 실패: {exc}",
            status_code=503,
        ) from exc

    _cache = [VocabularyEntry.model_validate(item) for item in payload["vocabulary"]]
    return _cache


def clear_cache() -> None:
    """테스트 및 수동 갱신용."""
    global _cache
    _cache = None
