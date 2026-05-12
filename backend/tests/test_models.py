"""Tests for database models and ORM functionality.

Integration tests for models are run in CI with PostgreSQL service.
Local unit tests verify model structure and basic functionality.
"""

from app.models.base import User


class TestUserModel:
    """Test User model structure and basic functionality."""

    def test_user_model_exists(self):
        """User model is properly defined."""
        assert hasattr(User, "__tablename__")
        assert User.__tablename__ == "users"

    def test_user_model_has_required_columns(self):
        """User model has id, created_at, and updated_at columns."""
        from app.db import Base

        user_table = Base.metadata.tables["users"]
        column_names = [col.name for col in user_table.columns]

        assert "id" in column_names
        assert "created_at" in column_names
        assert "updated_at" in column_names

    def test_user_model_repr(self):
        """User model __repr__ is defined."""
        user = User()
        repr_str = repr(user)
        assert "User" in repr_str
