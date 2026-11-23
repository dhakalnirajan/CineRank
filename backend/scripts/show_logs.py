#!/usr/bin/env python3
"""Print CineRank JSON-lines logs as aligned, readable terminal rows."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def format_entry(entry: dict[str, Any]) -> str:
    timestamp = str(entry.get("timestamp") or "")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        timestamp = parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    level = str(entry.get("level") or "INFO")[:8]
    logger = str(entry.get("logger") or "")[:20]
    message = str(entry.get("message") or "")
    details: list[str] = []
    if entry.get("method") or entry.get("path"):
        details.append(f"{entry.get('method', '')} {entry.get('path', '')}".strip())
    if entry.get("status") is not None:
        details.append(f"status={entry['status']}")
    if entry.get("duration_ms") is not None:
        details.append(f"{entry['duration_ms']}ms")
    if entry.get("request_id"):
        details.append(f"request={entry['request_id']}")
    if entry.get("event") and entry["event"] != message:
        details.append(f"event={entry['event']}")
    for key in ("user_id", "session_id", "scope", "job_name"):
        if entry.get(key) is not None:
            details.append(f"{key}={entry[key]}")
    suffix = f" | {' '.join(details)}" if details else ""
    line = f"{timestamp} | {level:<8} | {logger:<20} | {message}{suffix}"
    if entry.get("exception"):
        line += f"\n{entry['exception']}"
    return line


def run(args: argparse.Namespace) -> int:
    path = Path(args.file or Path(settings.LOG_DIR) / settings.LOG_FILE_NAME)
    if not path.is_file():
        print(f"No log file yet: {path}", file=sys.stderr)
        print("Start the API or worker and make a request, then try again.", file=sys.stderr)
        return 1

    threshold = LEVELS[args.level]
    accepted: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                if args.level == "DEBUG":
                    accepted.append(raw)
                continue
            if LEVELS.get(str(entry.get("level", "INFO")).upper(), 20) < threshold:
                continue
            if args.request_id and entry.get("request_id") != args.request_id:
                continue
            if args.event and entry.get("event") != args.event:
                continue
            accepted.append(format_entry(entry))

    for line in accepted[-args.tail:]:
        print(line)
    if not args.follow:
        return 0

    with path.open(encoding="utf-8", errors="replace") as handle:
        handle.seek(0, 2)
        while True:
            line = handle.readline()
            if not line:
                time.sleep(1)
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if LEVELS.get(str(entry.get("level", "INFO")).upper(), 20) < threshold:
                continue
            if args.request_id and entry.get("request_id") != args.request_id:
                continue
            if args.event and entry.get("event") != args.event:
                continue
            print(format_entry(entry), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Log file path. Defaults to LOG_DIR/LOG_FILE_NAME.")
    parser.add_argument("--tail", type=int, default=50, help="Number of recent rows to print.")
    parser.add_argument("--level", choices=tuple(LEVELS), default="INFO")
    parser.add_argument("--request-id", help="Only rows for one request ID.")
    parser.add_argument("--event", help="Only rows with this structured event name.")
    parser.add_argument("--follow", action="store_true", help="Continue printing new rows.")
    args = parser.parse_args()
    if args.tail < 1:
        parser.error("--tail must be >= 1")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
