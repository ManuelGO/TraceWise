"""Tests for logging middleware."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient

from app.context import get_context_var, reset_context
from app.middleware.logging_middleware import RequestContextMiddleware


@pytest.fixture
def app_with_middleware():
    """Create a test app with request context middleware."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/test")
    async def test_route():
        request_id = get_context_var("request_id")
        return JSONResponse({"request_id": request_id})

    @app.get("/error")
    async def error_route():
        raise ValueError("Test error")

    return app


def test_middleware_sets_request_id(app_with_middleware):
    """Middleware should generate and set request_id."""
    client = TestClient(app_with_middleware)
    response = client.get("/test")
    data = response.json()

    # Should have a request_id
    assert data["request_id"] is not None
    assert isinstance(data["request_id"], str)
    assert len(data["request_id"]) > 0


def test_middleware_uses_x_request_id_header(app_with_middleware):
    """Middleware should use X-Request-ID header if provided (must be UUID format)."""
    # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    test_id = "12345678-1234-5678-1234-567812345678"

    client = TestClient(app_with_middleware)
    response = client.get("/test", headers={"X-Request-ID": test_id})
    data = response.json()

    assert data["request_id"] == test_id


def test_middleware_resets_context_on_response(app_with_middleware):
    """Middleware should reset context after response."""
    reset_context()
    client = TestClient(app_with_middleware)
    # Make a request
    client.get("/test")

    # Context should be reset
    assert get_context_var("request_id") is None


def test_middleware_resets_on_exception(app_with_middleware):
    """Middleware should reset context even if handler raises."""
    reset_context()
    client = TestClient(app_with_middleware)
    # Make a request that raises an error (will be caught by TestClient)
    try:
        client.get("/error")
    except Exception:
        pass  # Expected - error route raises

    # Context should still be reset
    assert get_context_var("request_id") is None


def test_middleware_multiple_requests_have_different_ids(app_with_middleware):
    """Multiple requests should have different request_ids."""
    client = TestClient(app_with_middleware)

    response1 = client.get("/test")
    data1 = response1.json()
    request_id_1 = data1["request_id"]

    response2 = client.get("/test")
    data2 = response2.json()
    request_id_2 = data2["request_id"]

    # Each request should have its own request_id
    assert request_id_1 != request_id_2


def test_middleware_rejects_invalid_x_request_id_header(app_with_middleware):
    """Middleware should reject invalid X-Request-ID (non-UUID) and generate new one."""
    client = TestClient(app_with_middleware)

    # Send with invalid request ID (not UUID format)
    response = client.get("/test", headers={"X-Request-ID": "invalid-id-123"})
    data = response.json()
    request_id = data["request_id"]

    # Should be a generated UUID, not the invalid input
    assert request_id != "invalid-id-123"
    assert len(request_id) == 36  # UUID format: 8-4-4-4-12


def test_middleware_ignores_whitespace_only_x_request_id(app_with_middleware):
    """Middleware should ignore whitespace-only X-Request-ID and generate new one."""
    client = TestClient(app_with_middleware)

    # Send with whitespace-only request ID
    response = client.get("/test", headers={"X-Request-ID": "   "})
    data = response.json()
    request_id = data["request_id"]

    # Should be a generated UUID, not whitespace
    assert request_id != "   "
    assert len(request_id) == 36  # UUID format
