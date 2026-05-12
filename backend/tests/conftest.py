"""Pytest configuration and shared fixtures for backend tests."""

import os
from typing import AsyncGenerator

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


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_database_url: str):
    """Create async SQLAlchemy engine for test database.

    Scope: session - shared across all tests.
    Creates tables once at session start, drops them at session end.
    """
    engine = create_async_engine(
        test_database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


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
    async with test_engine.connect() as conn:
        transaction = await conn.begin()

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
            await transaction.rollback()


@pytest.fixture(scope="function")
def client(test_db_session: AsyncSession) -> TestClient:
    """Provide FastAPI TestClient for API endpoint testing.

    Scope: function - new client per test
    Note: This is a synchronous TestClient for sync HTTP requests.
    For async API testing, use async test fixtures instead.

    Usage:
        def test_get_items(client: TestClient):
            response = client.get("/api/items")
            assert response.status_code == 200
    """

    def get_test_db():
        return test_db_session

    app = create_app()
    # Override the database dependency with test session
    from app.db import get_db
    app.dependency_overrides[get_db] = get_test_db

    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()
