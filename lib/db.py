import os
import sys
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv(override=True)

DATABASE_URL = os.environ["DATABASE_URL"]


def create_pool():
    return ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=5,
        max_size=10,
        timeout=30,
        open=True,
    )


if "streamlit" in sys.modules:
    import streamlit as st

    @st.cache_resource
    def get_pool():
        return create_pool()

    pool = get_pool()

else:
    pool = create_pool()
