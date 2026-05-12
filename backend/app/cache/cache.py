"""Cache utilities for Redis operations."""

import json
import logging
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Default cache expiration times (in seconds)
CACHE_TTL_DEFAULT = 3600  # 1 hour
CACHE_TTL_SHORT = 300  # 5 minutes
CACHE_TTL_LONG = 86400  # 24 hours


def format_cache_key(service: str, entity_type: str, identifier: str) -> str:
    """Format a cache key following naming convention.

    Convention: {service}:{entity_type}:{identifier}
    Example: tracewise:user:123

    Args:
        service: Service name (e.g., 'tracewise')
        entity_type: Entity type (e.g., 'user', 'session')
        identifier: Unique identifier (e.g., user ID, session ID)

    Returns:
        Formatted cache key string
    """
    return f"{service}:{entity_type}:{identifier}"


async def get_cache(
    client: redis.Redis | None,
    key: str,
    default: Any = None,
) -> Any:
    """Get a value from cache.

    Args:
        client: Redis async client
        key: Cache key
        default: Default value if key not found or Redis unavailable

    Returns:
        Cached value, or default if unavailable
    """
    if not client:
        logger.debug(f"Cache get skipped (Redis unavailable): {key}")
        return default

    try:
        value = await client.get(key)
        if value is not None:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        logger.debug(f"Cache miss: {key}")
        return default
    except Exception as e:
        logger.error(f"Cache get error ({key}): {type(e).__name__}: {e}")
        return default


async def set_cache(
    client: redis.Redis | None,
    key: str,
    value: Any,
    ttl: int = CACHE_TTL_DEFAULT,
) -> bool:
    """Set a value in cache.

    Args:
        client: Redis async client
        key: Cache key
        value: Value to cache (will be JSON-serialized if dict/list)
        ttl: Time to live in seconds (default: 1 hour)

    Returns:
        True if successful, False otherwise
    """
    if not client:
        logger.debug(f"Cache set skipped (Redis unavailable): {key}")
        return False

    if ttl <= 0:
        logger.warning(f"Cache set rejected: ttl must be positive, got {ttl} for key {key}")
        return False

    try:
        if isinstance(value, dict | list):
            value = json.dumps(value)
        await client.setex(key, ttl, value)
        logger.debug(f"Cache set: {key} (ttl={ttl}s)")
        return True
    except Exception as e:
        logger.error(f"Cache set error ({key}): {type(e).__name__}: {e}")
        return False


async def delete_cache(
    client: redis.Redis | None,
    key: str,
) -> bool:
    """Delete a value from cache.

    Args:
        client: Redis async client
        key: Cache key

    Returns:
        True if key was deleted, False otherwise
    """
    if not client:
        logger.debug(f"Cache delete skipped (Redis unavailable): {key}")
        return False

    try:
        result = await client.delete(key)
        logger.debug(f"Cache delete: {key} (deleted={result > 0})")
        return result > 0
    except Exception as e:
        logger.error(f"Cache delete error ({key}): {type(e).__name__}: {e}")
        return False


async def clear_cache_pattern(
    client: redis.Redis | None,
    pattern: str,
) -> int:
    """Delete all keys matching a pattern using non-blocking SCAN.

    Args:
        client: Redis async client
        pattern: Pattern to match (e.g., 'tracewise:user:*')

    Returns:
        Number of keys deleted
    """
    if not client:
        logger.debug(f"Cache clear pattern skipped (Redis unavailable): {pattern}")
        return 0

    try:
        deleted = 0
        async for key in client.scan_iter(match=pattern, count=100):
            deleted += await client.delete(key)
        logger.debug(f"Cache pattern cleared: {pattern} (deleted={deleted})")
        return deleted
    except Exception as e:
        logger.error(f"Cache clear pattern error ({pattern}): {type(e).__name__}: {e}")
        return 0
