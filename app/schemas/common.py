from pydantic import BaseModel, ConfigDict, Field

# 에러 포맷 — docs/api-design-backend.md 1장 "공통 오류 형식" 기준


class ErrorDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    retryable: bool
    # requestId가 없는 API(현재는 candidates를 제외한 전부)의 오류에서는 항상 null.
    request_id: str | None = Field(default=None, alias="requestId")


class ErrorResponse(BaseModel):
    error: ErrorDetail
