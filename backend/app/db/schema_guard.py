"""Fail-fast validation for the database schema required by this application.

Schema changes are deployed with Alembic, never by ORM create_all in a running
API/worker process. This catches a stale local database before login handlers
start returning opaque 500 responses.
"""
from __future__ import annotations

from sqlalchemy import Engine, inspect
from sqlalchemy.exc import SQLAlchemyError

_REQUIRED_COLUMNS = {
    "users": {"id", "username", "password_hash", "avatar_url", "email_verified_at"},
    "user_sessions": {"id", "user_id", "refresh_token_hash", "expires_at", "revoked_at"},
    "email_action_tokens": {"id", "user_id", "purpose", "email", "token_hash", "expires_at", "used_at"},
    "user_preferences": {"user_id", "preferred_genres_json", "excluded_genres_json", "include_adult", "updated_at"},
    "movies": {"title_id", "serial_number", "movielens_id", "tmdb_id"},
}


def validate_database_schema(engine: Engine) -> None:
    """Raise an actionable error when the configured database is behind migrations."""
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        missing: list[str] = []
        for table, expected_columns in _REQUIRED_COLUMNS.items():
            if table not in tables:
                missing.append(f"missing table {table}")
                continue
            actual_columns = {column["name"] for column in inspector.get_columns(table)}
            missing.extend(
                f"missing column {table}.{column}"
                for column in sorted(expected_columns - actual_columns)
            )
    except SQLAlchemyError as exc:
        raise RuntimeError(
            "CineRank could not inspect DATABASE_URL. Check that the configured "
            "database exists and is accessible before starting the API/worker."
        ) from exc

    if missing:
        details = "; ".join(missing)
        raise RuntimeError(
            "CineRank database schema is behind the application models: "
            f"{details}. From the backend directory, run `python -m alembic upgrade head` "
            "against the same DATABASE_URL used by the API, then restart the service. "
            "Do not delete or recreate the database; the migration preserves existing data."
        )
