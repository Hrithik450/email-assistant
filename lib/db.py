import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv(override=True)

DATABASE_URL = os.environ["DATABASE_URL"]

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=5,
    max_size=10,
    timeout=30,
    open=True,
)
