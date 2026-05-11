"""FastAPI application factory and lifespan management."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.db import connect_with_retry, create_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown.

    Redis is optional (soft dependency); startup succeeds if database is available.
    Cache operations gracefully degrade if Redis is unavailable.
    """
    settings = get_settings()

    redis_client, _ = await connect_with_retry(
        settings.DATABASE_URL, settings.REDIS_URL
    )
    if redis_client:
        logger.info("Redis connected (cache enabled)")
    else:
        logger.warning("Redis unavailable (cache disabled, service continues)")

    session_factory, sqlalchemy_engine = await create_session_factory(settings.DATABASE_URL)

    app.state.redis_client = redis_client
    app.state.session_factory = session_factory
    app.state.sqlalchemy_engine = sqlalchemy_engine
    logger.info("Backend started")

    yield

    if app.state.redis_client:
        await app.state.redis_client.aclose()
    await app.state.sqlalchemy_engine.dispose()
    logger.info("Backend shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        lifespan=lifespan,
        docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
        redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
    )

    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=True,
    )

    app.include_router(api_router)

    return app


app = create_app()
