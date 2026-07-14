"""
Shared pytest fixtures.
"""

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

SAMPLE_JSON_PATH = Path(__file__).parent.parent / "src" / "lib" / "data" / "sample.json"


@pytest.fixture(scope="session")
def sample_email() -> dict:
    """Single normalized email record from sample.json."""
    with open(SAMPLE_JSON_PATH) as f:
        data = json.load(f)
    return data if isinstance(data, dict) else data[0]


@pytest.fixture(scope="session")
def db_pool():
    """
    Shared psycopg3 connection pool.
    Skipped automatically when DATABASE_URL is not set or postgres is unreachable.
    """
    from psycopg_pool import ConnectionPool

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")

    dsn = url.replace("postgresql+psycopg://", "postgresql://")
    try:
        pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=3, timeout=5, open=True)
    except Exception as exc:
        pytest.skip(f"Cannot connect to postgres: {exc}")

    yield pool
    pool.close()


@pytest.fixture(scope="session")
def redis_client():
    """
    Redis client. Skipped when REDIS_URL is not set or Redis is unreachable.
    """
    import redis as _redis

    url = os.environ.get("REDIS_URL", "")
    if not url:
        pytest.skip("REDIS_URL not set")

    client = _redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
    try:
        client.ping()
    except Exception as exc:
        pytest.skip(f"Cannot connect to Redis: {exc}")

    yield client
