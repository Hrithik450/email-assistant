import atexit
import os
import sys

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

from urllib.parse import urlparse, urlunparse
import psycopg

load_dotenv(override=True)

# Try direct connection string provided by user, but default to IPv4 pooler
_raw_url = os.environ.get("DATABASE_URL", "postgresql://postgres.bsohudarhxrraxbmvjci:Mhrithik450%40@aws-1-ap-south-1.pooler.supabase.com:6543/postgres")
parsed = urlparse(_raw_url)
if "sslmode=require" not in parsed.query:
    query = parsed.query + "&sslmode=require" if parsed.query else "sslmode=require"
    parsed = parsed._replace(query=query)
DATABASE_URL = urlunparse(parsed)

# Synchronously test the connection first so Streamlit catches auth errors instead of PoolTimeouts
try:
    _test_conn = psycopg.connect(DATABASE_URL)
    _test_conn.close()
except Exception as e:
    raise RuntimeError(f"Database connection failed: {e}")

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
