import os
import redis
from dotenv import load_dotenv

load_dotenv(override=True)

REDIS_URL = os.environ["REDIS_URL"]

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
)
