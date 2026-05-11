"""FastAPI application factory and lifespan management."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.db import connect_with_retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    settings = get_settings()

    db_pool, redis_client = await connect_with_retry(
        settings.DATABASE_URL, settings.REDIS_URL
    )
    if not db_pool or not redis_client:
        raise RuntimeError(
            "Failed to connect to required services (PostgreSQL and Redis) at startup"
        )

    app.state.db_pool = db_pool
    app.state.redis_client = redis_client
    logger.info("Backend started and connected to services")

    yield

    await app.state.db_pool.close()
    await app.state.redis_client.close()
    logger.info("Backend shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app


app = create_app()
