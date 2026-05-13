"""Base repository class with generic CRUD operations for all models."""

import logging
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic repository with common CRUD operations for database models.

    Type parameter T must be a SQLAlchemy model class.

    Protected fields (id, created_at, updated_at) cannot be modified.
    Subclasses should define FILTERABLE_FIELDS to restrict filtering.

    Example:
        class UserRepository(BaseRepository[User]):
            async def find_by_email(self, session: AsyncSession, email: str) -> User | None:
                stmt = select(self.model).where(self.model.email == email)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
    """

    PROTECTED_FIELDS: ClassVar[set[str]] = {"id", "created_at", "updated_at"}
    FILTERABLE_FIELDS: ClassVar[set[str]] = set()

    def __init__(self, model: type[T]):
        """Initialize repository for the given model.

        Args:
            model: SQLAlchemy model class
        """
        self.model = model

    async def create(self, session: AsyncSession, obj_in: T) -> T:
        """Create and persist a new object.

        Args:
            session: AsyncSession instance
            obj_in: Model instance to persist

        Returns:
            The created model instance with all generated fields populated

        Raises:
            Exception: On database constraint violation or other persistence errors
        """
        session.add(obj_in)
        await session.flush()
        logger.debug(f"Created new {self.model.__name__}: {obj_in.id}")  # type: ignore[attr-defined]
        return obj_in

    async def read(self, session: AsyncSession, obj_id: UUID) -> T | None:
        """Retrieve an object by ID.

        Args:
            session: AsyncSession instance
            obj_id: UUID of the object to retrieve

        Returns:
            The model instance if found, None otherwise
        """
        stmt = select(self.model).where(self.model.id == obj_id)  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        logger.debug(f"Read {self.model.__name__}: {obj_id} - Found: {obj is not None}")
        return obj

    async def update(self, session: AsyncSession, obj_id: UUID, obj_in: dict[str, Any]) -> T | None:
        """Update an object with the given fields.

        Protected fields (id, created_at, updated_at) cannot be modified.
        Only model-defined columns can be updated.

        Args:
            session: AsyncSession instance
            obj_id: UUID of the object to update
            obj_in: Dictionary of field names and values to update

        Returns:
            The updated model instance if found, None if not found

        Raises:
            ValueError: If attempting to update protected fields
            Exception: On database constraint violation or other persistence errors
        """
        protected_in_request = set(obj_in.keys()) & self.PROTECTED_FIELDS
        if protected_in_request:
            raise ValueError(
                f"Cannot update protected fields: {protected_in_request}. "
                f"Only updateable fields can be modified."
            )

        obj = await self.read(session, obj_id)
        if not obj:
            logger.debug(f"Update failed: {self.model.__name__} {obj_id} not found")
            return None

        for field, value in obj_in.items():
            if hasattr(obj, field) and field not in self.PROTECTED_FIELDS:
                setattr(obj, field, value)
                logger.debug(f"Updated field {field} on {self.model.__name__}: {obj_id}")

        await session.flush()
        logger.debug(f"Updated {self.model.__name__}: {obj_id}")
        return obj

    async def delete(self, session: AsyncSession, obj_id: UUID) -> bool:
        """Delete an object by ID.

        Args:
            session: AsyncSession instance
            obj_id: UUID of the object to delete

        Returns:
            True if object was deleted, False if not found

        Raises:
            Exception: On database constraint violation or other persistence errors
        """
        obj = await self.read(session, obj_id)
        if not obj:
            logger.debug(f"Delete failed: {self.model.__name__} {obj_id} not found")
            return False

        session.delete(obj)  # type: ignore[unused-coroutine]
        await session.flush()
        logger.debug(f"Deleted {self.model.__name__}: {obj_id}")
        return True

    async def list(self, session: AsyncSession, skip: int = 0, limit: int = 100) -> Any:
        """Retrieve a paginated list of objects.

        Args:
            session: AsyncSession instance
            skip: Number of records to skip (default 0, must be >= 0)
            limit: Maximum number of records to return (default 100, max 1000)

        Returns:
            List of model instances

        Raises:
            ValueError: If skip < 0 or limit < 1
        """
        if skip < 0:
            raise ValueError("skip must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        limit = min(limit, 1000)
        stmt = select(self.model).offset(skip).limit(limit)
        result = await session.execute(stmt)
        objects = result.scalars().all()
        logger.debug(
            f"Listed {self.model.__name__}: skip={skip}, limit={limit}, count={len(objects)}"
        )
        return objects

    async def list_by_filter(
        self,
        session: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Any:
        """Retrieve a filtered and paginated list of objects.

        Only fields in FILTERABLE_FIELDS are allowed. Unknown filter keys
        raise ValueError to catch typos and prevent silent filtering bypasses.

        Args:
            session: AsyncSession instance
            skip: Number of records to skip (default 0, must be >= 0)
            limit: Maximum number of records to return (default 100, capped at 1000)
            **filters: Keyword arguments for filtering (must match FILTERABLE_FIELDS)

        Returns:
            List of model instances matching the filter criteria

        Raises:
            ValueError: If unrecognized filter fields are provided
            ValueError: If skip < 0 or limit < 1

        Example:
            cases = await repository.list_by_filter(
                session,
                status=CaseStatus.ACTIVE,
                skip=0,
                limit=10
            )
        """
        unknown_filters = set(filters.keys()) - self.FILTERABLE_FIELDS
        if unknown_filters:
            raise ValueError(
                f"Unknown filter fields: {unknown_filters}. "
                f"Allowed fields: {self.FILTERABLE_FIELDS}"
            )

        if skip < 0:
            raise ValueError("skip must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        limit = min(limit, 1000)

        # Build filter conditions
        conditions = []
        for field, value in filters.items():
            conditions.append(getattr(self.model, field) == value)

        if conditions:
            stmt = select(self.model).where(and_(*conditions)).offset(skip).limit(limit)
        else:
            stmt = select(self.model).offset(skip).limit(limit)

        result = await session.execute(stmt)
        objects = result.scalars().all()
        logger.debug(
            f"Listed {self.model.__name__} with filters: skip={skip}, limit={limit}, count={len(objects)}"
        )
        return objects

    async def count(self, session: AsyncSession) -> int:
        """Get the total count of objects.

        Args:
            session: AsyncSession instance

        Returns:
            Total number of objects of this model type
        """
        stmt = select(func.count(self.model.id))  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        count = result.scalar_one()
        logger.debug(f"Counted {self.model.__name__}: {count}")
        return count

    async def exists(self, session: AsyncSession, obj_id: UUID) -> bool:
        """Check if an object with the given ID exists.

        Args:
            session: AsyncSession instance
            obj_id: UUID to check

        Returns:
            True if object exists, False otherwise
        """
        stmt = select(func.count(self.model.id)).where(self.model.id == obj_id)  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        count = result.scalar_one()
        return count > 0


__all__ = ["BaseRepository"]
