"""Best-effort JSON cache backed by Redis; PostgreSQL remains authoritative."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.metrics import REDIS_OPERATION_ERRORS, RECOMMENDATION_CACHE_EVENTS
from app.core.redis_client import get_redis

logger = logging.getLogger("cinerank.cache")


def get_json(key: str) -> Any | None:
    try:
        client = get_redis()
        if client is None:
            RECOMMENDATION_CACHE_EVENTS.labels("shared", "disabled").inc()
            return None
        value = client.get(key)
        if value is None:
            RECOMMENDATION_CACHE_EVENTS.labels("shared", "miss").inc()
            return None
        RECOMMENDATION_CACHE_EVENTS.labels("shared", "hit").inc()
        return json.loads(value)
    except Exception:
        REDIS_OPERATION_ERRORS.labels("cache_get").inc()
        RECOMMENDATION_CACHE_EVENTS.labels("shared", "error").inc()
        logger.warning("Redis cache read failed", exc_info=True)
        return None


def set_json(key: str, value: Any, ttl_seconds: int) -> bool:
    try:
        client = get_redis()
        if client is None:
            RECOMMENDATION_CACHE_EVENTS.labels("shared", "disabled").inc()
            return False
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        written = bool(client.setex(key, max(1, int(ttl_seconds)), encoded))
        RECOMMENDATION_CACHE_EVENTS.labels("shared", "write" if written else "write_failed").inc()
        return written
    except (TypeError, ValueError):
        RECOMMENDATION_CACHE_EVENTS.labels("shared", "serialization_error").inc()
        logger.warning("Cache value is not JSON serializable: %s", key)
        return False
    except Exception:
        REDIS_OPERATION_ERRORS.labels("cache_set").inc()
        RECOMMENDATION_CACHE_EVENTS.labels("shared", "error").inc()
        logger.warning("Redis cache write failed", exc_info=True)
        return False


def delete(key: str) -> bool:
    try:
        client = get_redis()
        if client is None:
            return False
        return bool(client.delete(key))
    except Exception:
        REDIS_OPERATION_ERRORS.labels("cache_delete").inc()
        logger.warning("Redis cache delete failed", exc_info=True)
        return False
