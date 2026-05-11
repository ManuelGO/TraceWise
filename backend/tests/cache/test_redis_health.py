"""Tests for Redis health checks."""
import pytest
import redis.asyncio as redis

from app.cache import check_redis_health, get_redis_info


@pytest.fixture
async def redis_client():
    """Fixture for Redis client."""
    client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_check_redis_health_success(redis_client):
    """Test health check with healthy Redis."""
    result = await check_redis_health(redis_client, max_retries=1)
    assert result is True


@pytest.mark.asyncio
async def test_check_redis_health_with_none_client():
    """Test health check with None client."""
    result = await check_redis_health(None, max_retries=1)
    assert result is False


@pytest.mark.asyncio
async def test_get_redis_info(redis_client):
    """Test getting Redis server info."""
    info = await get_redis_info(redis_client)
    assert info is not None
    assert "version" in info
    assert "connected_clients" in info
    assert "used_memory" in info


@pytest.mark.asyncio
async def test_get_redis_info_with_none_client():
    """Test getting Redis info with None client."""
    info = await get_redis_info(None)
    assert info is None
