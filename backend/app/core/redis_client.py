"""Shared Redis connection for distributed rate limits and ephemeral caches.

PostgreSQL remains the source of truth. Redis is an acceleration/coordination
layer; callers must define a safe degraded mode when it is unavailable.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import settings
from app.core.metrics import REDIS_OPERATION_ERRORS

logger = logging.getLogger("cinerank.redis")
_lock = threading.Lock()
_client: Any | None = None
_client_url: str | None = None


def get_redis():
    global _client, _client_url
    url = settings.REDIS_URL.strip()
    if not url:
        return None
    with _lock:
        if _client is not None and _client_url == url:
            return _client
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - deployment dependency guard
            raise RuntimeError("REDIS_URL is configured but the redis package is not installed") from exc
        _client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            health_check_interval=30,
            retry_on_timeout=False,
        )
        _client_url = url
        return _client


def redis_health() -> bool:
    try:
        client = get_redis()
        if client is None:
            return False
        return bool(client.ping())
    except Exception:
        REDIS_OPERATION_ERRORS.labels("health").inc()
        logger.warning("Redis health check failed", exc_info=True)
        return False


def reset_redis_client() -> None:
    """Test helper; closes the process client and clears its cached URL."""
    global _client, _client_url
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                logger.debug("Redis close failed", exc_info=True)
        _client = None
        _client_url = None
