import os
import sys
import redis
from dotenv import load_dotenv

load_dotenv(override=True)

REDIS_URL = os.environ["REDIS_URL"]


def create_redis_client():
    return redis.from_url(
        REDIS_URL,
        decode_responses=True,
    )


if "streamlit" in sys.modules:
    import streamlit as st

    @st.cache_resource
    def get_redis_client():
        return create_redis_client()

    redis_client = get_redis_client()

else:
    redis_client = create_redis_client()
