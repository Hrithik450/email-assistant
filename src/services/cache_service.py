from src.lib.logger import get_logger

logger = get_logger(__name__)
from src.lib.cache import redis_client


class CacheService:
    @staticmethod
    def delete(key: str):
        try:
            return redis_client.delete(key)
        except Exception as e:
            logger.warning("Redis delete failed for key=%s: %s", key, e)
            return 0

    @staticmethod
    def get(key: str):
        try:
            return redis_client.get(key)
        except Exception as e:
            logger.warning("Redis get failed for key=%s: %s", key, e)
            return None

    @staticmethod
    def set(key: str, value, ex=None):
        try:
            return redis_client.set(key, value, ex=ex)
        except Exception as e:
            logger.warning("Redis set failed for key=%s: %s", key, e)
            return False
