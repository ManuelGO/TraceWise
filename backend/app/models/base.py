"""Base model for all database entities."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import declarative_mixin

from app.db import Base


@declarative_mixin
class BaseModel:
    """Base model with common columns (id, created_at, updated_at)."""

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class User(Base, BaseModel):
    """User model example."""

    __tablename__ = "users"

    def __repr__(self):
        return f"<User(id={self.id}, created_at={self.created_at}, updated_at={self.updated_at})>"
