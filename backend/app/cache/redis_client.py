"""Redis client configuration and connection management."""

import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)


def create_redis_pool(
    redis_url: str,
    max_connections: int = 10,
    socket_timeout: float = 5.0,
    socket_keepalive: bool = True,
    retry_on_timeout: bool = True,
) -> redis.Redis:
    """Create a Redis async client with connection pooling.

    Args:
        redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        max_connections: Maximum connections in pool (default: 10)
        socket_timeout: Socket timeout in seconds (default: 5.0)
        socket_keepalive: Enable TCP keep-alive (default: True)
        retry_on_timeout: Retry on timeout (default: True)

    Returns:
        Configured redis.asyncio.Redis client with connection pool
    """
    try:
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_keepalive=socket_keepalive,
            retry_on_timeout=retry_on_timeout,
            socket_connect_timeout=5.0,
        )
        logger.info(
            f"Redis connection pool created: max_connections={max_connections}, "
            f"socket_timeout={socket_timeout}s"
        )
        return client
    except Exception as e:
        logger.error(f"Failed to create Redis pool: {e}")
        raise


async def verify_redis_connection(client: redis.Redis) -> bool:
    """Verify Redis connection with PING command.

    Args:
        client: Redis async client

    Returns:
        True if Redis responds to PING, False otherwise
    """
    try:
        result = await client.ping()
        logger.debug(f"Redis PING result: {result}")
        return result is True or result == "PONG"
    except Exception as e:
        logger.error(f"Redis PING failed: {type(e).__name__}: {e}")
        return False
