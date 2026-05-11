"""Database connection management."""
import asyncio
import logging
from typing import Optional

import asyncpg
import redis.asyncio as redis

from app.db.database import Base, create_db_engine, create_session_factory, get_db, health_check, init_db

logger = logging.getLogger(__name__)


async def connect_with_retry(
    database_url: str, redis_url: str, max_retries: int = 5
) -> tuple[Optional[redis.Redis], None]:
    """Establish Redis connection with exponential backoff retry logic.

    PostgreSQL connections are now managed exclusively via SQLAlchemy engine.
    This function handles Redis connectivity only.

    Returns:
        tuple: (redis_client, None) or (None, None) on failure
    """
    for attempt in range(max_retries):
        redis_client = None
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info(f"Connected to Redis (attempt {attempt + 1})")
            return redis_client, None

        except (redis.RedisError, OSError, asyncio.TimeoutError) as e:
            if redis_client:
                try:
                    await redis_client.aclose()
                except Exception as close_err:
                    logger.debug(f"Error closing Redis connection: {close_err}")

            delay = min(2**attempt, 16)
            if attempt < max_retries - 1:
                logger.warning(
                    f"Redis connection attempt {attempt + 1} failed: {e}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"Redis connection failed on attempt {attempt + 1}: {e}")

    logger.error(f"Failed to connect to Redis after {max_retries} attempts")
    return None, None


__all__ = [
    "connect_with_retry",
    "Base",
    "create_db_engine",
    "create_session_factory",
    "get_db",
    "health_check",
    "init_db",
]
