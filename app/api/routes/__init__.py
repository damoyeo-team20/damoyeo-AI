from fastapi import APIRouter

from app.api.routes.internal import router as internal_router
from app.api.routes.meetings import router as meetings_router
from app.api.routes.preferences import router as preferences_router

api_router = APIRouter()
api_router.include_router(preferences_router)
api_router.include_router(meetings_router)
api_router.include_router(internal_router)
