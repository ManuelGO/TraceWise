import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
import psycopg2
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def connect_with_retry(max_retries=5):
    database_url = os.getenv('DATABASE_URL')
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')

    if not database_url:
        logger.error("DATABASE_URL environment variable is not set")
        return None, None

    retry_delays = [1, 2, 4, 8, 16]

    for attempt in range(max_retries):
        db_conn = None
        try:
            db_conn = psycopg2.connect(database_url)
            logger.info(f"Connected to PostgreSQL (attempt {attempt + 1})")

            redis_client = redis.from_url(redis_url)
            redis_client.ping()
            logger.info(f"Connected to Redis (attempt {attempt + 1})")

            return db_conn, redis_client
        except (psycopg2.OperationalError, redis.exceptions.RedisError) as e:
            if db_conn:
                try:
                    db_conn.close()
                except Exception:
                    pass

            if attempt < max_retries - 1:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Failed to connect after {max_retries} attempts: {e}")
                return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_conn, redis_client = await connect_with_retry()
    if not db_conn or not redis_client:
        raise RuntimeError("Failed to connect to required services (PostgreSQL and Redis) at startup")
    app.state.db_conn = db_conn
    app.state.redis_client = redis_client
    logger.info("Backend started and connected to services")
    yield
    if app.state.db_conn:
        app.state.db_conn.close()
    if app.state.redis_client:
        app.state.redis_client.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
