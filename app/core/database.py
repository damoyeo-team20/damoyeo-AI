"""SQLAlchemy(async) 엔진/세션 팩토리.

이 AI 서비스가 직접 소유하는 로컬 DB(damoyeo_ai) 연결을 담당한다. get_settings()와 같은
지연 생성 패턴을 따른다 — 모듈 임포트 시점에 바로 엔진을 만들지 않는다.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용. DB 세션이 직접 필요한 라우터에서 사용한다."""
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        yield session
