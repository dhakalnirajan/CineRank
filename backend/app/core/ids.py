"""Stable, time-ordered title identifier generation (UUIDv7 + namespace prefix)."""
from __future__ import annotations

import secrets
import threading
import time
import uuid

_LOCK = threading.Lock()
_LAST_MILLIS = -1
_LAST_RANDOM = -1
_RANDOM_MASK = (1 << 74) - 1


def uuid7() -> uuid.UUID:
    """Generate an RFC 9562 UUIDv7 with monotonic ordering within this process.

    The timestamp occupies the most significant 48 bits. Random bits are
    incremented when multiple IDs are generated in one millisecond; this also
    prevents local clock rollback from reversing process-local order.
    """
    global _LAST_MILLIS, _LAST_RANDOM
    now_ms = int(time.time_ns() // 1_000_000)
    with _LOCK:
        if now_ms > _LAST_MILLIS:
            timestamp_ms = now_ms
            random_bits = secrets.randbits(74)
        else:
            timestamp_ms = _LAST_MILLIS
            random_bits = _LAST_RANDOM + 1
            if random_bits > _RANDOM_MASK:
                timestamp_ms += 1
                random_bits = secrets.randbits(74)
        _LAST_MILLIS = timestamp_ms
        _LAST_RANDOM = random_bits

    rand_a = (random_bits >> 62) & 0xFFF
    rand_b = random_bits & ((1 << 62) - 1)
    value = (
        ((timestamp_ms & ((1 << 48) - 1)) << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid.UUID(int=value)


def generate_title_id() -> str:
    """Return an immutable title ID, e.g. ``title_019...``."""
    return f"title_{uuid7()}"


def is_title_id(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith("title_"):
        return False
    try:
        parsed = uuid.UUID(value.removeprefix("title_"))
    except (ValueError, AttributeError):
        return False
    return parsed.version == 7
