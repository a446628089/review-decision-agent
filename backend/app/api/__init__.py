from fastapi import APIRouter
from app.api.health import router as health_router
from app.api.meetings import router as meetings_router
from app.api.summaries import router as summaries_router
from app.api.summaries import global_router as summaries_global_router
api_router = APIRouter(prefix="/api")
api_router.include_router(summaries_global_router)
api_router.include_router(health_router)
api_router.include_router(meetings_router)
api_router.include_router(summaries_router)
