import atexit
import os
import sys

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv(override=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres.bsohudarhxrraxbmvjci:Mhrithik450%40@aws-1-ap-south-1.pooler.supabase.com:6543/postgres")

_pool: ConnectionPool | None = None


def create_pool() -> ConnectionPool:
    return ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=2,
        max_size=10,
        timeout=30,
        open=True,
    )


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if "streamlit" in sys.modules:
            import streamlit as st

            @st.cache_resource
            def _st_pool():
                return create_pool()

            _pool = _st_pool()
        else:
            _pool = create_pool()
        atexit.register(_shutdown_pool)
    return _pool


def _shutdown_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def __getattr__(name: str):
    if name == "pool":
        return get_pool()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
