"""Database connection management."""
import asyncio
import logging
from typing import Optional

import asyncpg
import redis.asyncio as redis

logger = logging.getLogger(__name__)


async def connect_with_retry(
    database_url: str, redis_url: str, max_retries: int = 5
) -> tuple[Optional[asyncpg.Pool], Optional[redis.Redis]]:
    """Establish database and Redis connections with exponential backoff retry logic.

    Returns:
        tuple: (db_pool, redis_client) or (None, None) on failure
    """
    if max_retries <= 0:
        logger.error("max_retries must be >= 1")
        return None, None

    for attempt in range(max_retries):
        db_pool = None
        redis_client = None
        try:
            db_pool = await asyncpg.create_pool(
                database_url,
                min_size=5,
                max_size=20,
                command_timeout=10,
            )
            logger.info(f"Connected to PostgreSQL (attempt {attempt + 1})")

            redis_client = redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info(f"Connected to Redis (attempt {attempt + 1})")

            return db_pool, redis_client
        except (asyncpg.PostgresError, redis.RedisError) as e:
            if db_pool:
                try:
                    await db_pool.close()
                except Exception:
                    pass

            if redis_client:
                try:
                    await redis_client.close()
                except Exception:
                    pass

            delay = min(2**attempt, 16)
            if attempt < max_retries - 1:
                logger.warning(
                    f"Connection attempt {attempt + 1} failed: {e}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)

    logger.error(f"Failed to connect after {max_retries} attempts")
    return None, None
