"""Database initialization script for creating tables and seed data."""

import asyncio
import logging
import sys

from app.config import get_settings
from app.db.database import create_session_factory, health_check, init_db
from app.models import ComplianceCase, User  # noqa: F401 - import to register with Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Initialize database and create all tables."""
    try:
        settings = get_settings()
        logger.info(f"Initializing database: {settings.DATABASE_URL}")

        session_factory, engine = await create_session_factory(settings.DATABASE_URL)

        if not await health_check(session_factory):
            logger.error("Database health check failed. Ensure PostgreSQL is running.")
            await engine.dispose()
            sys.exit(1)

        logger.info("Database health check passed")

        if not await init_db(engine):
            logger.error("Failed to initialize database tables")
            await engine.dispose()
            sys.exit(1)

        logger.info("Database initialization completed successfully")
        await engine.dispose()

    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
