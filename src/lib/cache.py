import atexit
import os
import sys

import redis
from dotenv import load_dotenv

load_dotenv(override=True)

REDIS_URL = os.environ.get("REDIS_URL", "")

_redis_client: redis.Redis | None = None


def create_redis_client() -> redis.Redis:
    return redis.from_url(
        REDIS_URL,
        decode_responses=True,
    )


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        if "streamlit" in sys.modules:
            import streamlit as st

            @st.cache_resource
            def _st_redis():
                return create_redis_client()

            _redis_client = _st_redis()
        else:
            _redis_client = create_redis_client()
        atexit.register(_shutdown_redis)
    return _redis_client


def _shutdown_redis():
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None


def __getattr__(name: str):
    if name == "redis_client":
        return get_redis_client()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
