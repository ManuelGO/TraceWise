"""Pytest configuration and shared fixtures for backend tests."""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import create_app


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Get test database URL from environment or use default.

    Tests use a separate database to avoid polluting development data.
    """
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/tracewise_test",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: integration tests requiring database (skip if unavailable)"
    )


@pytest.fixture(scope="session")
def test_engine(test_database_url: str):
    """Create async SQLAlchemy engine for test database.

    Scope: session - shared across all tests.
    Creates tables once at session start, drops them at session end.
    Skips integration tests if database is unavailable.
    """

    async def _create_engine():
        engine = create_async_engine(
            test_database_url,
            echo=False,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=False,
        )
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return engine
        except Exception:
            await engine.dispose()
            return None

    async def _teardown_engine(engine):
        if engine:
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.drop_all)
            except Exception:
                pass
            finally:
                await engine.dispose()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    engine = loop.run_until_complete(_create_engine())

    yield engine

    if engine:
        loop.run_until_complete(_teardown_engine(engine))


@pytest_asyncio.fixture(scope="function")
async def test_db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide isolated test database session with transaction rollback isolation.

    Scope: function - new session per test
    Isolation: Uses transaction savepoint rollback to avoid database state pollution.
    Each test gets a clean slate; changes are rolled back after test completes.

    Usage:
        async def test_something(test_db_session: AsyncSession):
            result = await test_db_session.execute(select(User))
            users = result.scalars().all()
    """
    if test_engine is None:
        pytest.skip("Database unavailable for integration tests")

    async with test_engine.connect() as conn:
        trans = await conn.begin()

        async_session = sessionmaker(
            conn,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        session = async_session()

        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_db_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Alias for test_db_session for consistency with test names."""
    yield test_db_session


@pytest_asyncio.fixture(scope="function")
async def session_factory(test_engine):
    """Provide AsyncSession factory for vector store integration tests.

    Scope: function - new factory per test
    Creates AsyncSession instances that can be used with VectorStore.

    Usage:
        @pytest.mark.asyncio
        async def test_vector_store(session_factory):
            store = PostgresVectorStore(session_factory)
            result = await store.search(...)
    """
    if test_engine is None:
        pytest.skip("Database unavailable")
    return sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Provide FastAPI TestClient for API endpoint testing.

    Scope: function - new client per test
    Note: Database access must be configured separately if needed.
    For async database testing, use test_db_session fixture directly.

    Usage (API testing without database):
        def test_get_health(client: TestClient):
            response = client.get("/health")
            assert response.status_code == 200

    Usage (with database, use async tests):
        @pytest.mark.asyncio
        async def test_with_db(test_db_session: AsyncSession):
            result = await test_db_session.execute(select(User))
            items = result.scalars().all()
    """
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
