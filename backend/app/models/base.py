"""Base model for all database entities."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Uuid
from sqlalchemy.orm import Mapped, declarative_mixin

from app.db.database import Base


@declarative_mixin
class BaseModel:
    """Base model with common columns (created_at, updated_at).

    Note: Each concrete model must declare its own id column.
    Provides only timestamp tracking, not primary key.
    """

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class User(Base, BaseModel):
    """User model with authentication info.

    Phase 3: Will be extended with:
    - username (unique)
    - email (unique)
    - password_hash
    - role (compliance_officer, legal_reviewer, etc.)
    - created_at (inherited from BaseModel)
    - updated_at (inherited from BaseModel)
    """

    __tablename__ = "users"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
        nullable=False,
    )

    def __repr__(self):
        return f"<User(id={self.id}, created_at={self.created_at}, updated_at={self.updated_at})>"
