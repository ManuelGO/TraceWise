"""Tests for cache operations."""

import asyncio

import pytest
import redis.asyncio as redis

from app.cache import (
    clear_cache_pattern,
    delete_cache,
    format_cache_key,
    get_cache,
    set_cache,
)


@pytest.fixture
async def redis_client():
    """Fixture for Redis client."""
    client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.mark.asyncio
async def test_format_cache_key():
    """Test cache key formatting."""
    key = format_cache_key("tracewise", "user", "123")
    assert key == "tracewise:user:123"

    key = format_cache_key("tracewise", "session", "abc-def")
    assert key == "tracewise:session:abc-def"


@pytest.mark.asyncio
async def test_set_cache_with_none_client():
    """Test set_cache with None client (graceful degradation)."""
    result = await set_cache(None, "key", "value")
    assert result is False


@pytest.mark.asyncio
async def test_get_cache_with_none_client():
    """Test get_cache with None client (graceful degradation)."""
    result = await get_cache(None, "key", default="default")
    assert result == "default"


@pytest.mark.asyncio
async def test_delete_cache_with_none_client():
    """Test delete_cache with None client (graceful degradation)."""
    result = await delete_cache(None, "key")
    assert result is False


@pytest.mark.asyncio
async def test_cache_set_get_string(redis_client):
    """Test setting and getting a string value."""
    key = "test:string:key"
    value = "test_value"

    result = await set_cache(redis_client, key, value)
    assert result is True

    cached = await get_cache(redis_client, key)
    assert cached == value


@pytest.mark.asyncio
async def test_cache_set_get_dict(redis_client):
    """Test setting and getting a dictionary value."""
    key = "test:dict:key"
    value = {"name": "John", "age": 30}

    result = await set_cache(redis_client, key, value)
    assert result is True

    cached = await get_cache(redis_client, key)
    assert cached == value


@pytest.mark.asyncio
async def test_cache_set_get_list(redis_client):
    """Test setting and getting a list value."""
    key = "test:list:key"
    value = [1, 2, 3, "item"]

    result = await set_cache(redis_client, key, value)
    assert result is True

    cached = await get_cache(redis_client, key)
    assert cached == value


@pytest.mark.asyncio
async def test_cache_miss(redis_client):
    """Test get_cache with missing key."""
    key = "test:missing:key"
    result = await get_cache(redis_client, key, default=None)
    assert result is None

    result = await get_cache(redis_client, key, default="default")
    assert result == "default"


@pytest.mark.asyncio
async def test_cache_ttl(redis_client):
    """Test cache TTL (time to live)."""
    key = "test:ttl:key"
    value = "test_value"

    result = await set_cache(redis_client, key, value, ttl=1)
    assert result is True

    cached = await get_cache(redis_client, key)
    assert cached == value

    await asyncio.sleep(1.1)

    cached = await get_cache(redis_client, key)
    assert cached is None


@pytest.mark.asyncio
async def test_delete_cache(redis_client):
    """Test deleting a cache entry."""
    key = "test:delete:key"
    value = "test_value"

    await set_cache(redis_client, key, value)
    cached = await get_cache(redis_client, key)
    assert cached == value

    result = await delete_cache(redis_client, key)
    assert result is True

    cached = await get_cache(redis_client, key)
    assert cached is None


@pytest.mark.asyncio
async def test_delete_nonexistent_key(redis_client):
    """Test deleting a non-existent key."""
    result = await delete_cache(redis_client, "nonexistent:key")
    assert result is False


@pytest.mark.asyncio
async def test_clear_cache_pattern(redis_client):
    """Test clearing cache entries by pattern."""
    keys = [
        "tracewise:user:1",
        "tracewise:user:2",
        "tracewise:user:3",
        "tracewise:session:abc",
    ]

    for key in keys:
        await set_cache(redis_client, key, "value")

    deleted = await clear_cache_pattern(redis_client, "tracewise:user:*")
    assert deleted == 3

    remaining = await get_cache(redis_client, "tracewise:session:abc")
    assert remaining == "value"


@pytest.mark.asyncio
async def test_clear_cache_pattern_no_matches(redis_client):
    """Test clearing cache pattern with no matches."""
    deleted = await clear_cache_pattern(redis_client, "nonexistent:*")
    assert deleted == 0


@pytest.mark.asyncio
async def test_cache_key_naming_convention(redis_client):
    """Test cache key naming convention."""
    key = format_cache_key("tracewise", "user", "123")
    await set_cache(redis_client, key, {"id": 123, "name": "User"})

    cached = await get_cache(redis_client, key)
    assert cached["id"] == 123
    assert cached["name"] == "User"
