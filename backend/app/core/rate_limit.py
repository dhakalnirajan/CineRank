"""Atomic shared sliding-window rate limiter with a local development fallback."""
from __future__ import annotations

import hashlib
import logging
import math
import secrets
import threading
import time
from collections import deque

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger("cinerank.rate_limit")

_REDIS_WINDOW_SCRIPT = r"""
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local first = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = window
  if first[2] then retry = math.max(1, math.ceil(tonumber(first[2]) + window - now)) end
  redis.call('EXPIRE', key, math.ceil(window) + 1)
  return retry
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window) + 1)
return 0
"""


class SlidingWindowRateLimiter:
    """Process-local fallback retained for tests and single-process development."""
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, max_requests: int, window_seconds: float = 60.0,
              now: float | None = None) -> int | None:
        if max_requests <= 0:
            return 0
        current = time.monotonic() if now is None else now
        cutoff = current - window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= max_requests:
                return max(1, math.ceil(events[0] + window_seconds - current))
            events.append(current)
            return None

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


class DistributedRateLimiter:
    """Use Redis across API workers; fall back locally outside production.

    In production Redis failure is fail-closed. This avoids silently turning a
    distributed credential-abuse control into independent per-process limits.
    """
    def __init__(self) -> None:
        self.local = SlidingWindowRateLimiter()

    def check(self, key: str, max_requests: int, window_seconds: float = 60.0,
              now: float | None = None) -> int | None:
        if max_requests <= 0:
            return 0
        try:
            redis_client = get_redis()
        except Exception:
            logger.exception("Shared rate limiter client could not be initialized")
            if settings.ENVIRONMENT.strip().lower() == "production":
                return max(1, math.ceil(window_seconds))
            return self.local.check(key, max_requests, window_seconds, now)
        if redis_client is None:
            if settings.ENVIRONMENT.strip().lower() == "production":
                logger.error("Redis is required for production rate limiting")
                return max(1, math.ceil(window_seconds))
            return self.local.check(key, max_requests, window_seconds, now)
        try:
            # Do not put usernames, IPs or user IDs in Redis key names.
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            current = time.time() if now is None else float(now)
            result = redis_client.eval(
                _REDIS_WINDOW_SCRIPT, 1, f"cinerank:ratelimit:{digest}",
                current, float(window_seconds), int(max_requests),
                f"{current:.6f}:{secrets.token_hex(8)}",
            )
            retry = int(result or 0)
            return retry if retry > 0 else None
        except Exception:
            logger.exception("Shared rate limiter unavailable")
            if settings.ENVIRONMENT.strip().lower() == "production":
                return max(1, math.ceil(window_seconds))
            return self.local.check(key, max_requests, window_seconds, now)

    def reset(self) -> None:
        self.local.reset()


auth_rate_limiter = DistributedRateLimiter()
request_rate_limiter = DistributedRateLimiter()
