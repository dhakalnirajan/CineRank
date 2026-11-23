import json
import logging

from app.core.logging_config import HumanFormatter, JsonLinesFormatter
from scripts.show_logs import format_entry


def test_human_formatter_keeps_request_fields_on_one_line():
    record = logging.LogRecord(
        "cinerank.access",
        logging.INFO,
        __file__,
        1,
        "request_complete",
        (),
        None,
    )
    record.event = "request_complete"
    record.request_id = "abc123"
    record.method = "GET"
    record.path = "/api/v1/movies"
    record.status = 200
    record.duration_ms = 6.22

    line = HumanFormatter().format(record)

    assert "cinerank.access" in line
    assert "request_complete" in line
    assert "request_id=abc123" in line
    assert "method=GET" in line
    assert "status=200" in line
    assert "duration_ms=6.22" in line


def test_json_formatter_writes_stable_machine_readable_fields():
    record = logging.LogRecord(
        "cinerank.access",
        logging.INFO,
        __file__,
        1,
        "request_complete",
        (),
        None,
    )
    record.event = "request_complete"
    record.request_id = "abc123"
    record.method = "GET"
    record.path = "/api/v1/movies"
    record.status = 200
    record.duration_ms = 6.22

    payload = json.loads(JsonLinesFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "cinerank.access"
    assert payload["event"] == "request_complete"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/movies"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 6.22
    assert payload["timestamp"].endswith("+00:00")


def test_show_logs_formats_access_rows_for_scanning():
    line = format_entry(
        {
            "timestamp": "2026-11-23T22:17:45.123456+00:00",
            "level": "INFO",
            "logger": "cinerank.access",
            "message": "request_complete",
            "method": "GET",
            "path": "/api/v1/watchlist",
            "status": 200,
            "duration_ms": 8.21,
            "request_id": "d467c38a",
        }
    )

    assert line.startswith("2026-11-23 22:17:45 | INFO")
    assert "GET /api/v1/watchlist" in line
    assert "status=200" in line
    assert "8.21ms" in line
    assert "request=d467c38a" in line
