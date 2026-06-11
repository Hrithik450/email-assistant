import os
import redis
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv(override=True)

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=5,
    max_size=10,
    timeout=30,
    open=True,
)

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
)


#   conninfo="""
#         host=localhost
#         port=5432
#         dbname=postgres
#         user=hruthikm
#         password=Mhrithik450@
#     """,
