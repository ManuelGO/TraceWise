"""Health check endpoints."""
import logging
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get("", name="health_check")
async def health_check(request: Request) -> dict:
    """Health check endpoint with database connectivity verification."""
    try:
        app = request.app
        if hasattr(app.state, "session_factory"):
            from app.db import health_check as db_health_check
            db_healthy = await db_health_check(app.state.session_factory)
            return {
                "status": "healthy" if db_healthy else "unhealthy",
                "database": "connected" if db_healthy else "disconnected"
            }
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {type(e).__name__}")
        return {"status": "unhealthy"}
