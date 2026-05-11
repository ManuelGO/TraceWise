"""Redis health check with retry logic."""
import asyncio
import logging
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


async def check_redis_health(
    client: Optional[redis.Redis],
    max_retries: int = 3,
) -> bool:
    """Check Redis health with exponential backoff retry logic.

    Args:
        client: Redis async client
        max_retries: Number of retry attempts (default: 3)

    Returns:
        True if Redis is healthy, False otherwise
    """
    if not client:
        logger.warning("Redis client is None, cannot check health")
        return False

    for attempt in range(max_retries):
        try:
            result = await client.ping()
            is_healthy = result is True or result == "PONG"
            if is_healthy:
                logger.debug(f"Redis health check passed (attempt {attempt + 1})")
                return True
        except (redis.RedisError, OSError, asyncio.TimeoutError) as e:
            logger.debug(f"Redis health check attempt {attempt + 1} failed: {type(e).__name__}")

        if attempt < max_retries - 1:
            delay = min(2 ** attempt, 16)
            logger.debug(
                f"Redis health check failed, retrying in {delay}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )
            await asyncio.sleep(delay)

    logger.error(f"Redis health check failed after {max_retries} attempts")
    return False


async def get_redis_info(client: Optional[redis.Redis]) -> Optional[dict]:
    """Get Redis server information.

    Args:
        client: Redis async client

    Returns:
        Dictionary with Redis server info, or None if unavailable
    """
    if not client:
        return None

    try:
        info = await client.info()
        return {
            "version": info.get("redis_version", "unknown"),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "unknown"),
        }
    except Exception as e:
        logger.debug(f"Failed to get Redis info: {e}")
        return None
