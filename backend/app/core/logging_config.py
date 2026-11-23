"""Central logging: readable terminal output and rotating JSON-lines files."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.config import settings

_CONFIGURED = False
_EXTRA_FIELDS = (
    "event",
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "user_id",
    "session_id",
    "scope",
    "job_name",
)


class HumanFormatter(logging.Formatter):
    """One aligned line per event, with structured fields appended."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        message = record.getMessage()
        fields = [
            f"{key}={_safe_value(getattr(record, key))}"
            for key in _EXTRA_FIELDS
            if getattr(record, key, None) is not None
            and not (key == "event" and getattr(record, key) == message)
        ]
        return f"{base} | {' '.join(fields)}" if fields else base


class JsonLinesFormatter(logging.Formatter):
    """Machine-readable file format with stable top-level fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _safe_value(value: Any) -> str:
    text = str(value)
    return f'"{text}"' if " " in text else text


def _build_file_handler() -> RotatingFileHandler | None:
    if not settings.LOG_FILE_ENABLED or settings.ENVIRONMENT.strip().lower() == "test":
        return None
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / settings.LOG_FILE_NAME,
        maxBytes=max(1024, settings.LOG_MAX_BYTES),
        backupCount=max(1, settings.LOG_BACKUP_COUNT),
        encoding="utf-8",
    )
    handler.setFormatter(JsonLinesFormatter())
    return handler


def configure_logging(force: bool = False) -> None:
    """Configure root, Uvicorn and worker logging exactly once.

    Uvicorn's built-in access logger is disabled because the application already
    records method, route, status, latency and request ID. Keeping both produces
    duplicate request lines and makes the terminal harder to scan.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(HumanFormatter())
    root.addHandler(console)
    file_handler = _build_file_handler()
    if file_handler is not None:
        root.addHandler(file_handler)
    root.propagate = False

    # Use the application's handlers and formatting for server lifecycle lines.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True

    # Third-party request/DB debug output is opt-in, not part of normal operation.
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.SQL_ECHO else logging.WARNING
    )
    _CONFIGURED = True
