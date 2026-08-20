"""`preference_vocabulary` 테이블 ORM 모델.

실제 로컬 스키마(data/vocabulary_seed.sql)와 docs/db_schema.md(Back 확정본)를 함께 반영한다.
PK 타입만 SERIAL(INTEGER)/BIGINT로 다를 뿐 컬럼 구성은 동일하다.
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PreferenceVocabulary(Base):
    __tablename__ = "preference_vocabulary"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    domain: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(100))
    parent_code: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("preference_vocabulary.code"), default=None
    )
