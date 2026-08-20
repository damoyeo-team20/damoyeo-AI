"""`GET /internal/preference-vocabulary` 응답 스키마.

docs/api-design2-backend.md 3장 형식 그대로 — "Back이 제공하고 AI가 호출한다". DB를 AI가
직접 소유하는 안은 로컬 테스트 단계일 뿐 아직 확정되지 않았다 (app/services/vocabulary_client.py
참고). 이 파일은 AI가 Back의 응답을 파싱할 때 쓰는 스키마다.
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
