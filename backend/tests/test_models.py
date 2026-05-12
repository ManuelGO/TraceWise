"""Tests for database models and ORM functionality."""

import pytest
from sqlalchemy import select

from app.models.base import User

pytestmark = pytest.mark.integration


class TestUserModel:
    """Test User model creation and database persistence."""

    @pytest.mark.asyncio
    async def test_user_creation(self, test_db_session):
        """User can be created and persisted to database.

        Demonstrates:
        - Using test_db_session fixture for database access
        - Creating SQLAlchemy ORM models
        - Async database operations
        """
        user = User()
        test_db_session.add(user)
        await test_db_session.commit()

        assert user.id is not None
        assert user.created_at is not None
        assert user.updated_at is not None

    @pytest.mark.asyncio
    async def test_user_isolation_between_tests(self, test_db_session):
        """Database state is isolated between tests via transaction rollback.

        Demonstrates:
        - Clean database state for each test
        - No pollution from previous tests
        - Transaction rollback isolation in action
        """
        result = await test_db_session.execute(select(User))
        users = result.scalars().all()

        # Should be empty (rolled back from previous test)
        assert len(users) == 0

        user = User()
        test_db_session.add(user)
        await test_db_session.commit()

        result = await test_db_session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 1

    @pytest.mark.asyncio
    async def test_user_timestamps(self, test_db_session):
        """User model automatically manages created_at and updated_at timestamps.

        Demonstrates:
        - Automatic timestamp generation
        - UTC timezone handling
        """
        user = User()
        test_db_session.add(user)
        await test_db_session.commit()

        created_at = user.created_at
        updated_at = user.updated_at

        assert created_at is not None
        assert updated_at is not None
        # Both should be recent (within last minute)
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        assert created_at > now - timedelta(minutes=1)
        assert updated_at > now - timedelta(minutes=1)

    @pytest.mark.asyncio
    async def test_user_repr(self, test_db_session):
        """User model __repr__ includes key fields for debugging.

        Demonstrates:
        - Custom __repr__ implementation
        - String representation contains model state
        """
        user = User()
        test_db_session.add(user)
        await test_db_session.commit()

        repr_str = repr(user)
        assert "User" in repr_str
        assert f"id={user.id}" in repr_str
