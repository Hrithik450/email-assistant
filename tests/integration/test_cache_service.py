"""
Integration tests for CacheService — requires a running Redis.
Skipped automatically when REDIS_URL is not set or Redis is unreachable.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def patch_redis(redis_client):
    with patch("src.services.cache_service.redis_client", redis_client):
        yield


class TestCacheService:
    def test_set_and_get(self):
        from src.services.cache_service import CacheService

        CacheService.set("test:key", "hello")
        assert CacheService.get("test:key") == "hello"

    def test_delete(self):
        from src.services.cache_service import CacheService

        CacheService.set("test:del", "to_delete")
        CacheService.delete("test:del")
        assert CacheService.get("test:del") is None

    def test_get_missing_key_returns_none(self):
        from src.services.cache_service import CacheService

        assert CacheService.get("test:does_not_exist_xyz") is None

    def test_expiry(self):
        import time
        from src.services.cache_service import CacheService

        CacheService.set("test:expiry", "ephemeral", ex=1)
        assert CacheService.get("test:expiry") == "ephemeral"
        time.sleep(1.1)
        assert CacheService.get("test:expiry") is None
