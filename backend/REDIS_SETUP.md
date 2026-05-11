# Redis Setup

TraceWise uses Redis for caching and job queue support. This document describes the Redis configuration and how to use the cache utilities.

## Configuration

### Environment Variables

```bash
# Redis connection URL (format: redis://[password@]host:port[/database])
REDIS_URL=redis://:dev_redis_password@redis:6379/0

# Optional configuration
REDIS_MAX_CONNECTIONS=10
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_KEEPALIVE=true
```

### Connection Pooling

The Redis client uses connection pooling for efficient resource management:
- **Pool Size**: 10 connections
- **Max Overflow**: 20 additional temporary connections
- **Socket Timeout**: 5 seconds
- **Socket Keep-Alive**: Enabled
- **Retry on Timeout**: Enabled

## Usage

### Basic Cache Operations

The cache module provides simple utilities for common caching patterns:

```python
from app.cache import get_cache, set_cache, delete_cache, format_cache_key
from fastapi import Request

# Format cache key using naming convention
cache_key = format_cache_key("tracewise", "user", "123")
# Result: "tracewise:user:123"

# Set a value in cache (with 1-hour TTL)
await set_cache(redis_client, cache_key, {"id": 123, "name": "User"})

# Get a value from cache
user_data = await get_cache(redis_client, cache_key, default=None)

# Delete a value from cache
await delete_cache(redis_client, cache_key)
```

### Cache Key Naming Convention

Follow this naming convention for cache keys to organize data hierarchically:

```
{service}:{entity_type}:{identifier}
```

Examples:
- `tracewise:user:123` — User with ID 123
- `tracewise:session:abc-def-ghi` — Session with ID abc-def-ghi
- `tracewise:report:monthly:2024-05` — Monthly report for May 2024

### Cache TTL (Time To Live)

Cache entries expire automatically after the specified TTL (in seconds):

```python
from app.cache import set_cache, CACHE_TTL_SHORT, CACHE_TTL_DEFAULT, CACHE_TTL_LONG

# 5 minutes
await set_cache(redis_client, key, value, ttl=CACHE_TTL_SHORT)

# 1 hour (default)
await set_cache(redis_client, key, value, ttl=CACHE_TTL_DEFAULT)

# 24 hours
await set_cache(redis_client, key, value, ttl=CACHE_TTL_LONG)

# Custom TTL (30 minutes)
await set_cache(redis_client, key, value, ttl=1800)
```

### Integration with FastAPI Routes

Access Redis client from FastAPI request context:

```python
from fastapi import APIRouter, Request
from app.cache import get_cache, set_cache, format_cache_key

router = APIRouter()

@router.get("/users/{user_id}")
async def get_user(user_id: int, request: Request):
    redis_client = request.app.state.redis_client
    
    # Try cache first
    cache_key = format_cache_key("tracewise", "user", str(user_id))
    user = await get_cache(redis_client, cache_key)
    
    if user is None:
        # Cache miss: fetch from database
        user = await db.get_user(user_id)
        # Store in cache for future requests
        await set_cache(redis_client, cache_key, user)
    
    return user
```

### Health Checks

The health check endpoint includes Redis status:

```bash
curl http://localhost:8000/api/v1/health
```

Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "redis_info": {
    "version": "7.0.5",
    "connected_clients": 1,
    "used_memory": "1.2M"
  }
}
```

### Cache in Route Handlers

To use caching in your route handlers, access the Redis client from the request context:

```python
from fastapi import APIRouter, Request
from app.cache import get_cache, set_cache, format_cache_key

router = APIRouter()

@router.get("/data/{id}")
async def get_data(id: int, request: Request):
    # Try cache first
    cache_key = format_cache_key("tracewise", "data", str(id))
    cached = await get_cache(request.app.state.redis_client, cache_key)
    
    if cached is not None:
        return cached
    
    # Fetch from database
    data = {"id": id, "value": "some data"}
    
    # Store in cache for 1 hour
    await set_cache(request.app.state.redis_client, cache_key, data, ttl=3600)
    
    return data
```

## Testing

Run cache tests with pytest:

```bash
# All cache tests
pytest tests/cache/

# Specific test file
pytest tests/cache/test_cache_operations.py

# With verbose output
pytest tests/cache/ -v

# With coverage
pytest tests/cache/ --cov=app.cache
```

## Graceful Degradation

**Redis is a soft optional dependency.** The application starts successfully even if Redis is unavailable. Cache operations fail gracefully:

```python
# If Redis is offline, set_cache returns False but doesn't raise an error
success = await set_cache(redis_client, key, value)
if not success:
    # Handle cache failure (log warning, continue without cache)
    logger.debug("Cache operation failed, continuing without cache")

# If Redis is offline, get_cache returns the default value
value = await get_cache(redis_client, key, default=None)
# If Redis is unavailable, value will be None (the default)
```

Application continues to function without Redis, though without cache benefits. The health check reports:
- `"database": "connected"` (required)
- `"redis": "disconnected"` (optional)
- `"status": "healthy"` (depends on database only)

## Monitoring

### Connection Pool Status

Monitor Redis connection pool health through logs:

```
INFO: Redis connection pool created: max_connections=10, socket_timeout=5.0s
DEBUG: Redis PING result: True
DEBUG: Cache set: tracewise:user:123 (ttl=3600s)
```

### Troubleshooting

**Issue**: `Redis connection failed on attempt 5`
- Verify Redis service is running: `docker-compose ps redis`
- Check REDIS_URL environment variable
- Verify network connectivity: `docker-compose exec backend redis-cli ping`

**Issue**: Cache operations are slow
- Check Redis server load: `docker-compose logs redis`
- Verify socket timeout isn't too short (should be 5s)
- Consider increasing pool size if using high concurrency

## Next Steps

Redis is now ready for:
- **Phase 3**: Job queue setup using Celery or similar
- **Performance optimization**: Cache frequently accessed data
- **Session management**: Store session data in Redis

See the planning documents for integration details.
