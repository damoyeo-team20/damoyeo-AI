import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.config import configure_langsmith
from app.core.errors import AIServiceError

logger = logging.getLogger(__name__)

configure_langsmith()

app = FastAPI(title="damoyeo-ai")
app.include_router(api_router)


def _error_response(
    status_code: int, code: str, message: str, retryable: bool, request_id: str | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "requestId": request_id,
            }
        },
    )


@app.exception_handler(AIServiceError)
def handle_ai_service_error(request: Request, exc: AIServiceError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, exc.retryable, exc.request_id)


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI 기본 {"detail": [...]} 대신 공통 에러 포맷으로 통일한다.
    return _error_response(
        422, "REQUEST_SCHEMA_INVALID", "요청 필드가 계약과 일치하지 않습니다.", retryable=False
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # 문서상 500은 "AI 서비스 내부 오류"로만 정의되어 있고 구체 code는 명시되어 있지 않다 —
    # INTERNAL_ERROR는 이 문서에 없는 값을 우리가 임의로 붙인 것이므로 확정 계약은 아니다.
    logger.exception("처리되지 않은 예외")
    return _error_response(500, "INTERNAL_ERROR", "예기치 못한 오류가 발생했습니다.", retryable=False)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
