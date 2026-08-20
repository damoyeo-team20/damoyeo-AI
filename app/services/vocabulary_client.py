"""`preference_vocabulary` 조회.

이전에는 Back의 HTTP 엔드포인트를 호출했지만, DB 소유권이 AI 서비스로 이전되면서
(~/Downloads/CLAUDE.md 기준) 로컬 DB를 SQLAlchemy로 직접 조회하는 방식으로 바뀌었다.
N1 파이프라인은 계속 `fetch_vocabulary()`를 그대로 호출한다 — 시그니처는 바뀌지 않았다.
"""

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_sessionmaker
from app.core.errors import AIServiceError
from app.models.vocabulary import PreferenceVocabulary
from app.schemas.vocabulary import VocabularyEntry

_cache: list[VocabularyEntry] | None = None


async def fetch_vocabulary(force_refresh: bool = False) -> list[VocabularyEntry]:
    global _cache
    if _cache is not None and not force_refresh:
        return _cache

    session_factory = get_sessionmaker()
    try:
        async with session_factory() as session:
            result = await session.execute(select(PreferenceVocabulary))
            rows = result.scalars().all()
    except SQLAlchemyError as exc:
        raise AIServiceError(
            code="VOCABULARY_UNAVAILABLE",
            message=f"Vocabulary 조회 실패: {exc}",
            status_code=503,
            retryable=True,
        ) from exc

    _cache = [
        VocabularyEntry(
            code=row.code,
            domain=row.domain,
            display_name=row.display_name,
            parent_code=row.parent_code,
        )
        for row in rows
    ]
    return _cache


def clear_cache() -> None:
    """테스트 및 수동 갱신용."""
    global _cache
    _cache = None
