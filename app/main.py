import json
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.api.routes import api_router
from app.core.config import configure_langsmith
from app.core.debug import get_debug_trace, reset_debug_trace
from app.core.errors import AIServiceError

logger = logging.getLogger(__name__)

configure_langsmith()

app = FastAPI(title="damoyeo-ai")
app.include_router(api_router)


# ===== TEMP DEBUG: 배포 전에 이 미들웨어와 app/core/debug.py, 각 노드의 record_debug 호출을 지운다 =====
# 새 JSON 키를 만들지 않는다 — 백엔드가 모르는 필드가 생기면 파싱이 깨질 수 있어서, 이미 있는
# 문자열 필드(reply/reason/summary/message) 뒤에 "[DEBUG: ...]"를 그대로 이어붙이기만 한다.
_DEBUG_TEXT_KEYS = ("reply", "reason", "summary", "message")
_EXPOSE_DEBUG_IN_RESPONSE = False


def _append_debug_text(obj: dict, trace_text: str) -> None:
    for key in _DEBUG_TEXT_KEYS:
        value = obj.get(key)
        if isinstance(value, str):
            obj[key] = f"{value} [DEBUG: {trace_text}]"
    for nested_key in ("error", "actionRequired"):
        nested = obj.get(nested_key)
        if isinstance(nested, dict):
            _append_debug_text(nested, trace_text)


@app.middleware("http")
async def inject_debug_trace(request: Request, call_next):
    reset_debug_trace()
    response = await call_next(request)

    if "application/json" not in response.headers.get("content-type", ""):
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        payload = None

    if isinstance(payload, dict):
        trace = get_debug_trace()
        if _EXPOSE_DEBUG_IN_RESPONSE and trace:
            trace_text = json.dumps(trace, default=str, ensure_ascii=False)
            _append_debug_text(payload, trace_text)
        body = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")

    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    return Response(
        content=body, status_code=response.status_code, headers=headers, media_type="application/json"
    )
# ===== TEMP DEBUG 끝 =====


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
    logger.warning(
        "%s %s %s: %s", exc.code, request.method, request.url.path, exc.message
    )
    return _error_response(exc.status_code, exc.code, exc.message, exc.retryable, exc.request_id)


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI 기본 {"detail": [...]} 대신 공통 에러 포맷으로 통일한다.
    logger.warning("REQUEST_SCHEMA_INVALID %s %s: %s", request.method, request.url.path, exc.errors())
    # 라우트 진입 전 검증이라 노드 trace가 없다 — 여기서 직접 message에 이어붙인다.
    # TEMP DEBUG: 원래는 상세 필드 오류를 message에 안 넣는다. 배포 전에 아래 f-string을
    # 원래 메시지("요청 필드가 계약과 일치하지 않습니다.")로 되돌린다.
    detail = json.dumps(exc.errors(), default=str, ensure_ascii=False)
    return _error_response(
        422, "REQUEST_SCHEMA_INVALID", f"요청 필드가 계약과 일치하지 않습니다. [DEBUG: {detail}]" if _EXPOSE_DEBUG_IN_RESPONSE else "요청 필드가 계약과 일치하지 않습니다.", retryable=False
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # 문서상 500은 "AI 서비스 내부 오류"로만 정의되어 있고 구체 code는 명시되어 있지 않다 —
    # INTERNAL_ERROR는 이 문서에 없는 값을 우리가 임의로 붙인 것이므로 확정 계약은 아니다.
    logger.exception("처리되지 않은 예외")
    # TEMP DEBUG: 실제 예외를 응답 message에도 남긴다. 배포 전에 str(exc) 부분 제거.
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return _error_response(
        500, "INTERNAL_ERROR", f"예기치 못한 오류가 발생했습니다. [DEBUG: {exc!r}\n{detail}]" if _EXPOSE_DEBUG_IN_RESPONSE else "예기치 못한 오류가 발생했습니다.", retryable=False
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
