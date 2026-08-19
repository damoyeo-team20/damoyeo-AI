from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.errors import AIServiceError

app = FastAPI(title="damoyeo-ai")
app.include_router(api_router)


@app.exception_handler(AIServiceError)
def handle_ai_service_error(request: Request, exc: AIServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
