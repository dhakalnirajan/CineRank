"""Redis integration checks. Skipped unless CINERANK_TEST_REDIS_URL is set.

CI supplies a disposable Redis service and a dedicated database number. These
tests must not run against a production Redis instance.
"""
from __future__ import annotations

import hashlib
import os
import uuid

import pytest

from app.core.cache import delete, get_json, set_json
from app.core.config import settings
from app.core.rate_limit import DistributedRateLimiter
from app.core.redis_client import get_redis, reset_redis_client

REDIS_URL = os.environ.get("CINERANK_TEST_REDIS_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not REDIS_URL,
    reason="Set CINERANK_TEST_REDIS_URL to run real Redis integration tests",
)


@pytest.fixture(autouse=True)
def redis_client(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", REDIS_URL)
    reset_redis_client()
    client = get_redis()
    assert client is not None
    assert client.ping()
    yield client
    reset_redis_client()


def _rate_key(key: str) -> str:
    return "cinerank:ratelimit:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def test_rate_limit_is_atomic_shared_and_expires(redis_client):
    limiter = DistributedRateLimiter()
    key = f"test-rate-{uuid.uuid4()}"
    redis_key = _rate_key(key)
    try:
        assert [limiter.check(key, 3, 2) for _ in range(3)] == [None, None, None]
        retry = limiter.check(key, 3, 2)
        assert retry is not None and retry >= 1
        assert redis_client.exists(redis_key) == 1
        # The Redis path was used, not the process-local development fallback.
        assert not limiter.local._events  # noqa: SLF001 - deliberate integration assertion

        redis_client.delete(redis_key)
        assert limiter.check(key, 3, 2) is None
    finally:
        redis_client.delete(redis_key)


def test_json_cache_round_trip_and_delete(redis_client):
    key = f"cinerank:test:cache:{uuid.uuid4()}"
    try:
        assert set_json(key, {"title": "The Matrix", "rank": 1}, 30) is True
        assert get_json(key) == {"title": "The Matrix", "rank": 1}
        assert redis_client.ttl(key) > 0
        assert delete(key) is True
        assert get_json(key) is None
    finally:
        redis_client.delete(key)
