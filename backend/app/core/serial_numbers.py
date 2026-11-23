"""Permanent public title numbers backed by a transactional counter."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

SERIAL_NUMBER_WIDTH = 6


def format_title_serial(value: int | str) -> str:
    """Return the canonical zero-padded public serial number."""
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid title serial number") from exc
    if number < 1:
        raise ValueError("Invalid title serial number")
    return f"{number:0{SERIAL_NUMBER_WIDTH}d}"


def parse_title_serial(value: str) -> int:
    """Parse a public serial number without accepting signs or decimals."""
    if not value or not value.isdigit() or len(value) > 12:
        raise ValueError("Invalid title serial number")
    number = int(value)
    if number < 1:
        raise ValueError("Invalid title serial number")
    return number


def allocate_title_serial_numbers(connection: Connection, count: int = 1) -> list[int]:
    """Allocate one or more numbers atomically.

    SQLite serializes the write itself. PostgreSQL and MySQL lock the counter
    row for the current transaction.
    """
    if count < 1:
        return []
    dialect = connection.dialect.name

    if dialect == "sqlite":
        connection.execute(text(
            "INSERT OR IGNORE INTO title_serial_sequence (id, next_value) VALUES (1, 1)"
        ))
        connection.execute(
            text("UPDATE title_serial_sequence SET next_value = next_value + :count WHERE id = 1"),
            {"count": count},
        )
        next_value = int(connection.execute(
            text("SELECT next_value FROM title_serial_sequence WHERE id = 1")
        ).scalar_one())
        start = next_value - count
    else:
        if dialect == "postgresql":
            connection.execute(text(
                "INSERT INTO title_serial_sequence (id, next_value) VALUES (1, 1) "
                "ON CONFLICT (id) DO NOTHING"
            ))
        elif dialect == "mysql":
            connection.execute(text(
                "INSERT IGNORE INTO title_serial_sequence (id, next_value) VALUES (1, 1)"
            ))
        else:
            exists = connection.execute(text(
                "SELECT 1 FROM title_serial_sequence WHERE id = 1"
            )).scalar_one_or_none()
            if exists is None:
                connection.execute(text(
                    "INSERT INTO title_serial_sequence (id, next_value) VALUES (1, 1)"
                ))
        current = int(connection.execute(text(
            "SELECT next_value FROM title_serial_sequence WHERE id = 1 FOR UPDATE"
        )).scalar_one())
        connection.execute(
            text("UPDATE title_serial_sequence SET next_value = :next_value WHERE id = 1"),
            {"next_value": current + count},
        )
        start = current

    return list(range(start, start + count))
