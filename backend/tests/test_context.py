"""Tests for context variable management."""

import asyncio

import pytest

from app.context import get_context_var, reset_context, reset_token, set_context_var


class TestContextVariables:
    """Test context variable get/set operations."""

    def test_set_and_get_context_var(self):
        """Set a context variable and retrieve it."""
        set_context_var("request_id", "test-request-123")
        assert get_context_var("request_id") == "test-request-123"
        reset_context()

    def test_get_nonexistent_returns_none(self):
        """get_context_var returns None if not set."""
        reset_context()
        assert get_context_var("request_id") is None
        assert get_context_var("case_id") is None

    def test_reset_clears_context(self):
        """reset_context clears all variables."""
        set_context_var("request_id", "req-123")
        set_context_var("case_id", "case-456")
        set_context_var("user_id", "user-789")

        reset_context()

        assert get_context_var("request_id") is None
        assert get_context_var("case_id") is None
        assert get_context_var("user_id") is None

    def test_set_multiple_context_vars(self):
        """Set and retrieve multiple context variables."""
        reset_context()
        set_context_var("request_id", "req-123")
        set_context_var("case_id", "case-456")
        set_context_var("user_id", "user-789")
        set_context_var("document_id", "doc-101")
        set_context_var("session_id", "sess-202")

        assert get_context_var("request_id") == "req-123"
        assert get_context_var("case_id") == "case-456"
        assert get_context_var("user_id") == "user-789"
        assert get_context_var("document_id") == "doc-101"
        assert get_context_var("session_id") == "sess-202"

        reset_context()

    def test_invalid_context_var_raises_error(self):
        """get_context_var raises error for unknown variable."""
        with pytest.raises(ValueError, match="Unknown context variable"):
            get_context_var("invalid_var")

    def test_set_invalid_context_var_raises_error(self):
        """set_context_var raises error for unknown variable."""
        with pytest.raises(ValueError, match="Unknown context variable"):
            set_context_var("invalid_var", "value")

    def test_overwrite_context_var(self):
        """Overwriting a context variable works correctly."""
        reset_context()
        set_context_var("request_id", "req-old")
        assert get_context_var("request_id") == "req-old"

        set_context_var("request_id", "req-new")
        assert get_context_var("request_id") == "req-new"

        reset_context()

    @pytest.mark.asyncio
    async def test_context_isolated_per_async_task(self):
        """Context variables are isolated between async tasks."""

        async def task1():
            set_context_var("request_id", "task1-id")
            await asyncio.sleep(0.01)
            # Should still see task1's value
            return get_context_var("request_id")

        async def task2():
            await asyncio.sleep(0.005)
            set_context_var("request_id", "task2-id")
            return get_context_var("request_id")

        reset_context()
        result1, result2 = await asyncio.gather(task1(), task2())

        # Each task should have its own context
        assert result1 == "task1-id"
        assert result2 == "task2-id"

        reset_context()

    def test_set_context_var_returns_token(self):
        """set_context_var should return a Token for precise restoration."""
        reset_context()
        # get initial value
        assert get_context_var("request_id") is None

        # set a value and get token
        token = set_context_var("request_id", "value-1")
        assert get_context_var("request_id") == "value-1"

        # change the value
        set_context_var("request_id", "value-2")
        assert get_context_var("request_id") == "value-2"

        # restore via token
        reset_token("request_id", token)
        assert get_context_var("request_id") is None  # Restored to initial state

    def test_reset_token_restores_prior_value(self):
        """reset_token should restore the value that was set before the token."""
        reset_context()
        # Set initial value
        set_context_var("request_id", "initial")
        assert get_context_var("request_id") == "initial"

        # Set new value and capture token
        token = set_context_var("request_id", "new-value")
        assert get_context_var("request_id") == "new-value"

        # Reset to prior value
        reset_token("request_id", token)
        assert get_context_var("request_id") == "initial"
