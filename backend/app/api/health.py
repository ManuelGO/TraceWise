"""Health check endpoints."""
import logging
from fastapi import APIRouter, Request

from app.cache import check_redis_health, get_redis_info

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get("", name="health_check")
async def health_check(request: Request) -> dict:
    """Health check endpoint with database and optional Redis connectivity verification.

    Returns healthy if the database is connected. Redis is optional; if unavailable,
    the service is reported as degraded (but not unhealthy).
    """
    try:
        app = request.app
        db_healthy = False
        redis_healthy = None

        if hasattr(app.state, "session_factory"):
            from app.db import health_check as db_health_check
            db_healthy = await db_health_check(app.state.session_factory)

        if hasattr(app.state, "redis_client"):
            redis_healthy = await check_redis_health(app.state.redis_client, max_retries=1)

        result = {
            "status": "healthy" if db_healthy else "unhealthy",
            "database": "connected" if db_healthy else "disconnected",
        }

        if redis_healthy is not None:
            result["redis"] = "connected" if redis_healthy else "disconnected"

        return result
    except Exception as e:
        logger.error(f"Health check failed: {type(e).__name__}: {e}")
        return {"status": "unhealthy"}
