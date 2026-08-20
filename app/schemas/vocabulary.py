"""`GET /internal/preference-vocabulary` 응답 스키마.

docs/api-design2-backend.md 3장 형식 그대로. 이 문서는 "Back이 제공하고 AI가 호출한다"고
적혀 있지만, ~/Downloads/CLAUDE.md 기준으로 DB 소유권이 AI 서비스로 이전되어 지금은 AI가
직접 호스팅한다 — 응답 JSON 형태 자체는 그대로 유지한다.
"""

from pydantic import BaseModel, ConfigDict, Field


class VocabularyEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    domain: str
    display_name: str = Field(alias="displayName")
    parent_code: str | None = Field(default=None, alias="parentCode")


class VocabularyListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vocabulary: list[VocabularyEntry] = Field(default_factory=list)
