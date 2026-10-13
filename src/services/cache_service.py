from src.lib.logger import get_logger

logger = get_logger(__name__)

class CacheService:
    """In-memory cache fallback (Redis removed)."""
    _cache: dict = {}

    @staticmethod
    def delete(key: str):
        return 1 if CacheService._cache.pop(key, None) is not None else 0

    @staticmethod
    def get(key: str):
        return CacheService._cache.get(key)

    @staticmethod
    def set(key: str, value, ex=None):
        CacheService._cache[key] = value
        return True
