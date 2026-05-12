"""Cache and Redis utilities."""

from app.cache.cache import (
    CACHE_TTL_DEFAULT,
    CACHE_TTL_LONG,
    CACHE_TTL_SHORT,
    clear_cache_pattern,
    delete_cache,
    format_cache_key,
    get_cache,
    set_cache,
)
from app.cache.health import check_redis_health, get_redis_info
from app.cache.redis_client import create_redis_pool, verify_redis_connection

__all__ = [
    "create_redis_pool",
    "verify_redis_connection",
    "check_redis_health",
    "get_redis_info",
    "get_cache",
    "set_cache",
    "delete_cache",
    "clear_cache_pattern",
    "format_cache_key",
    "CACHE_TTL_DEFAULT",
    "CACHE_TTL_SHORT",
    "CACHE_TTL_LONG",
]
