import atexit
import os
import sys
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
import psycopg
from psycopg_pool import ConnectionPool

load_dotenv(override=True)


def get_database_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if "streamlit" in sys.modules:
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
                raw = st.secrets["DATABASE_URL"]
        except Exception:
            pass

    if not raw:
        raw = "postgresql://postgres.bsohudarhxrraxbmvjci:Mhrithik450@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

    parsed = urlparse(raw)
    if "sslmode=require" not in parsed.query and "localhost" not in parsed.netloc:
        query = parsed.query + "&sslmode=require" if parsed.query else "sslmode=require"
        parsed = parsed._replace(query=query)
    return urlunparse(parsed)


DATABASE_URL = get_database_url()

_pool: ConnectionPool | None = None


def create_pool() -> ConnectionPool:
    db_url = get_database_url()
    try:
        test_conn = psycopg.connect(db_url, connect_timeout=10)
        test_conn.close()
    except Exception as e:
        from src.lib.logger import get_logger
        get_logger(__name__).error("Database connection check failed: %s", e)

    return ConnectionPool(
        conninfo=db_url,
        min_size=2,
        max_size=10,
        timeout=30,
        open=True,
        kwargs={"prepare_threshold": None, "options": "-c search_path=public"},
    )


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if "streamlit" in sys.modules:
            import streamlit as st

            @st.cache_resource
            def _st_pool_v3():
                return create_pool()

            _pool = _st_pool_v3()
        else:
            _pool = create_pool()
        atexit.register(_shutdown_pool)
    return _pool


def _shutdown_pool():
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None
