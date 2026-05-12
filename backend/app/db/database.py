"""SQLAlchemy ORM configuration and database utilities."""
import logging
from typing import AsyncGenerator
from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()


def _normalize_db_url(url: str) -> str:
    """Normalize PostgreSQL URL to async SQLAlchemy dialect.

    Handles both 'postgresql://' and 'postgres://' schemes.
    Idempotent: safe to call on already-normalized URLs.
    """
    parsed = urlparse(url)
    if parsed.scheme in ("postgresql", "postgres"):
        parsed = parsed._replace(scheme="postgresql+asyncpg")
        return urlunparse(parsed)
    return url


def create_db_engine(
    database_url: str,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
):
    """Create async SQLAlchemy engine with connection pooling.

    Args:
        database_url: PostgreSQL connection string (postgresql://, postgres://, or postgresql+asyncpg://)
        echo: Enable SQL query logging
        pool_size: Number of connections to maintain in the pool
        max_overflow: Maximum number of overflow connections
        pool_pre_ping: Enable connection health check before using from pool

    Returns:
        AsyncEngine configured with connection pooling
    """
    normalized_url = _normalize_db_url(database_url)
    engine = create_async_engine(
        normalized_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=3600,
    )
    return engine


async def create_session_factory(
    database_url: str,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
):
    """Create async session factory for database operations.

    Args:
        database_url: PostgreSQL connection string
        echo: Enable SQL query logging
        pool_size: Number of connections to maintain in the pool
        max_overflow: Maximum number of overflow connections
        pool_pre_ping: Enable connection health check before using from pool

    Returns:
        sessionmaker configured for async SQLAlchemy
    """
    engine = create_db_engine(
        database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
    )
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return async_session, engine


async def get_db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection function for database sessions in FastAPI routes.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db(engine) -> bool:
    """Initialize database tables from SQLAlchemy models.

    Args:
        engine: AsyncEngine instance

    Returns:
        True if successful, False otherwise
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False


async def health_check(session_factory) -> bool:
    """Verify PostgreSQL connectivity with a simple query.

    Args:
        session_factory: AsyncSession factory

    Returns:
        True if database is accessible, False otherwise
    """
    try:
        from sqlalchemy import text
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {type(e).__name__}")
        return False
