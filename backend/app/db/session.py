"""Session and transaction management utilities for async database operations."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_transaction_for_dependency(
    session: AsyncSession,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for explicit transaction control on externally-owned sessions.

    Use with FastAPI dependency-injected sessions (e.g., Depends(get_db)).
    Does NOT close the session; lifecycle is managed by the dependency provider.

    Usage:
        @router.post("/cases")
        async def create_case(db: AsyncSession = Depends(get_db)):
            async with get_transaction_for_dependency(db):
                # ... database operations ...
            # Session remains open for other operations in the request

    Args:
        session: AsyncSession instance (managed externally)

    Yields:
        The same AsyncSession for use within the context

    Raises:
        Any exception raised during the context is re-raised after rollback
    """
    try:
        yield session
        await session.commit()
        logger.debug("Transaction committed successfully")
    except Exception:
        await session.rollback()
        logger.error("Transaction rolled back due to exception", exc_info=True)
        raise


@asynccontextmanager
async def get_transaction(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for explicit transaction control with auto-cleanup.

    Use in service methods or background tasks where YOU own and create the session.
    Automatically closes the session in the finally block.

    Usage:
        async def process_cases():
            session = AsyncSession(engine)
            async with get_transaction(session):
                # ... database operations ...
                # Session is automatically closed after context

    Args:
        session: AsyncSession instance (created and owned by caller)

    Yields:
        The same AsyncSession for use within the context

    Raises:
        Any exception raised during the context is re-raised after rollback
    """
    try:
        yield session
        await session.commit()
        logger.debug("Transaction committed successfully")
    except Exception:
        await session.rollback()
        logger.error("Transaction rolled back due to exception", exc_info=True)
        raise
    finally:
        await session.close()


@asynccontextmanager
async def get_nested_transaction(
    session: AsyncSession,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for savepoint (nested transaction) support.

    Creates a savepoint within the current transaction. If an exception occurs,
    the savepoint is rolled back but the parent transaction continues.
    Requires an active outer transaction.

    Usage:
        async with get_transaction(session):
            # Outer transaction
            await operation_one()
            try:
                async with get_nested_transaction(session):
                    # Inner savepoint
                    await risky_operation()
            except Exception:
                # Savepoint rolled back, outer transaction continues
                pass

    Args:
        session: AsyncSession instance with active transaction

    Yields:
        The same AsyncSession for use within the context

    Note:
        Savepoint is automatically rolled back on exception.
        Parent transaction can continue if properly handled.
    """
    savepoint = await session.begin_nested()
    try:
        yield session
        await savepoint.commit()
        logger.debug("Nested transaction (savepoint) committed successfully")
    except Exception:
        await savepoint.rollback()
        logger.warning("Savepoint rolled back due to exception", exc_info=True)
        raise


async def commit_session(session: AsyncSession) -> None:
    """Explicitly commit current transaction.

    Args:
        session: AsyncSession instance

    Raises:
        Exception if commit fails
    """
    try:
        await session.commit()
        logger.debug("Session committed successfully")
    except Exception:
        await session.rollback()
        logger.error("Failed to commit session", exc_info=True)
        raise


async def rollback_session(session: AsyncSession) -> None:
    """Explicitly rollback current transaction.

    Args:
        session: AsyncSession instance

    Raises:
        Exception if rollback fails (caller must know)
    """
    try:
        await session.rollback()
        logger.debug("Session rolled back successfully")
    except Exception:
        logger.error("Error during rollback", exc_info=True)
        raise


async def flush_session(session: AsyncSession) -> None:
    """Flush pending changes to database without committing transaction.

    Useful for retrieving generated IDs or database-computed values
    before the transaction is committed.

    Args:
        session: AsyncSession instance

    Raises:
        Exception if flush fails
    """
    try:
        await session.flush()
        logger.debug("Session flushed successfully")
    except Exception:
        logger.error("Failed to flush session", exc_info=True)
        raise


__all__ = [
    "commit_session",
    "flush_session",
    "get_nested_transaction",
    "get_transaction",
    "get_transaction_for_dependency",
    "rollback_session",
]
