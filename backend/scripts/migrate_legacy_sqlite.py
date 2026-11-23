#!/usr/bin/env python3
"""Copy the original integer-key SQLite schema into a new CineRank database.

The source database is opened read-only and is never modified. A new destination
SQLite file is created with the current schema. Movie IDs are replaced by
immutable title_<UUIDv7> primary keys, while MovieLens IDs are retained in the
separate movielens_id column and all known foreign keys are remapped.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.ids import generate_title_id
from app.core.serial_numbers import allocate_title_serial_numbers
from app.db.session import Base
from app.models import entities as _entities  # noqa: F401
from app.models.entities import (
    User, Movie, Rating, SearchLog, RecommendationLog, Watchlist, Interaction,
)
from app.services.catalogue_service import make_sort_key, rebuild_catalogue_sort_index


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                pass
    return None


def _columns(source: sqlite3.Connection, table: str) -> set[str]:
    rows = source.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row[1]) for row in rows}


def _table_exists(source: sqlite3.Connection, table: str) -> bool:
    return source.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _iter_rows(source: sqlite3.Connection, table: str, chunk_size: int = 5000):
    cursor = source.execute(f'SELECT * FROM "{table}"')
    columns = [item[0] for item in cursor.description]
    while True:
        batch = cursor.fetchmany(chunk_size)
        if not batch:
            return
        for row in batch:
            yield dict(zip(columns, row))


def _value(row: dict, key: str, default=None):
    return row[key] if key in row and row[key] is not None else default


def migrate(source_path: Path, destination_path: Path, batch_size: int = 5000) -> dict:
    source_path = source_path.expanduser().resolve()
    destination_path = destination_path.expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path == destination_path:
        raise ValueError("Source and destination must be different files; in-place migration is prohibited")
    if destination_path.exists() and destination_path.stat().st_size > 0:
        raise FileExistsError(f"Destination already exists and is non-empty: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    if not _table_exists(source, "movies") or not _table_exists(source, "users"):
        source.close()
        raise RuntimeError("Source is not a recognised legacy CineRank/Netflix recommender database")

    engine = create_engine(f"sqlite:///{destination_path}", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    report = {"source": str(source_path), "destination": str(destination_path),
              "users": 0, "movies": 0, "ratings": 0, "search_logs": 0,
              "recommendation_logs": 0, "watchlists": 0, "interactions": 0}
    user_ids: set[int] = set()
    old_movie_to_title: dict[int, str] = {}
    movielens_to_title: dict[int, str] = {}
    db = Session()
    try:
        user_columns = _columns(source, "users")
        user_batch = []
        for row in _iter_rows(source, "users", batch_size):
            old_id = int(row["id"])
            user_ids.add(old_id)
            user_batch.append({
                "id": old_id,
                "external_id": _value(row, "external_id"),
                "username": str(_value(row, "username", f"legacy_user_{old_id}"))[:64],
                "email": _value(row, "email"),
                "password_hash": _value(row, "password_hash"),
                "is_active": bool(_value(row, "is_active", 1)),
                "created_at": _parse_datetime(_value(row, "created_at")) or datetime.now(timezone.utc),
            })
            if len(user_batch) >= batch_size:
                db.bulk_insert_mappings(User, user_batch)
                report["users"] += len(user_batch)
                user_batch.clear()
        if user_batch:
            db.bulk_insert_mappings(User, user_batch)
            report["users"] += len(user_batch)
        db.commit()

        movie_columns = _columns(source, "movies")
        movie_batch = []
        for row in _iter_rows(source, "movies", batch_size):
            old_pk = int(row["id"])
            movielens_id = _value(row, "movie_id")
            title = str(_value(row, "title", f"Unknown title {old_pk}"))[:512]
            title_id = generate_title_id()
            old_movie_to_title[old_pk] = title_id
            if movielens_id is not None:
                movielens_to_title[int(movielens_id)] = title_id
            year = _value(row, "year")
            movie_batch.append({
                "title_id": title_id,
                "media_type": "movie",
                "movielens_id": int(movielens_id) if movielens_id is not None else None,
                "title": title,
                "sort_key": make_sort_key(title),
                "genres": str(_value(row, "genres", ""))[:1024],
                "year": int(year) if year is not None else None,
                "overview": _value(row, "overview"),
                "poster_path": _value(row, "poster_path"),
                "popularity": float(_value(row, "popularity", 0.0) or 0.0),
                "source": "legacy_sqlite",
                "created_at": _parse_datetime(_value(row, "created_at")) or datetime.now(timezone.utc),
            })
            if len(movie_batch) >= batch_size:
                serials = allocate_title_serial_numbers(db.connection(), len(movie_batch))
                for mapping, serial in zip(movie_batch, serials):
                    mapping["serial_number"] = serial
                db.bulk_insert_mappings(Movie, movie_batch)
                report["movies"] += len(movie_batch)
                movie_batch.clear()
        if movie_batch:
            serials = allocate_title_serial_numbers(db.connection(), len(movie_batch))
            for mapping, serial in zip(movie_batch, serials):
                mapping["serial_number"] = serial
            db.bulk_insert_mappings(Movie, movie_batch)
            report["movies"] += len(movie_batch)
        db.commit()

        if _table_exists(source, "ratings"):
            rating_columns = _columns(source, "ratings")
            batch = []
            for row in _iter_rows(source, "ratings", batch_size):
                old_movie_pk = int(row.get("movie_id"))
                title_id = old_movie_to_title.get(old_movie_pk)
                user_id = int(row.get("user_id"))
                if title_id is None or user_id not in user_ids:
                    continue
                batch.append({
                    "id": int(row["id"]) if row.get("id") is not None else None,
                    "user_id": user_id, "title_id": title_id,
                    "rating": float(row["rating"]),
                    "relevance": float(_value(row, "relevance", 1.0)),
                    "timestamp": _parse_datetime(_value(row, "timestamp")) or datetime.now(timezone.utc),
                    "is_implicit": bool(_value(row, "is_implicit", 0)),
                })
                if len(batch) >= batch_size:
                    db.bulk_insert_mappings(Rating, batch)
                    report["ratings"] += len(batch)
                    batch.clear()
            if batch:
                db.bulk_insert_mappings(Rating, batch)
                report["ratings"] += len(batch)
            db.commit()

        if _table_exists(source, "search_logs"):
            batch = []
            for row in _iter_rows(source, "search_logs", batch_size):
                user_id = _value(row, "user_id")
                if user_id is not None and int(user_id) not in user_ids:
                    user_id = None
                batch.append({
                    "id": _value(row, "id"), "user_id": user_id,
                    "query": str(_value(row, "query", ""))[:256],
                    "results_count": int(_value(row, "results_count", 0)),
                    "created_at": _parse_datetime(_value(row, "created_at")) or datetime.now(timezone.utc),
                })
                if len(batch) >= batch_size:
                    db.bulk_insert_mappings(SearchLog, batch)
                    report["search_logs"] += len(batch)
                    batch.clear()
            if batch:
                db.bulk_insert_mappings(SearchLog, batch)
                report["search_logs"] += len(batch)
            db.commit()

        if _table_exists(source, "recommendation_logs"):
            batch = []
            cols = _columns(source, "recommendation_logs")
            old_list_col = "movie_ids" if "movie_ids" in cols else "title_ids_json"
            for row in _iter_rows(source, "recommendation_logs", batch_size):
                user_id = int(row["user_id"])
                if user_id not in user_ids:
                    continue
                raw_ids = str(_value(row, old_list_col, ""))
                try:
                    parsed_ids = json.loads(raw_ids) if raw_ids.startswith("[") else [x for x in raw_ids.split(",") if x]
                except ValueError:
                    parsed_ids = [x for x in raw_ids.split(",") if x]
                mapped = []
                for old_id in parsed_ids:
                    try:
                        numeric_id = int(old_id)
                    except (TypeError, ValueError):
                        if str(old_id).startswith("title_"):
                            mapped.append(str(old_id))
                        continue
                    title_id = (movielens_to_title.get(numeric_id)
                                if old_list_col == "movie_ids" else old_movie_to_title.get(numeric_id))
                    if title_id:
                        mapped.append(title_id)
                batch.append({
                    "id": _value(row, "id"), "user_id": user_id,
                    "model_name": str(_value(row, "model_name", "legacy"))[:64],
                    "title_ids_json": json.dumps(mapped),
                    "k": int(_value(row, "k", len(mapped))),
                    "created_at": _parse_datetime(_value(row, "created_at")) or datetime.now(timezone.utc),
                })
                if len(batch) >= batch_size:
                    db.bulk_insert_mappings(RecommendationLog, batch)
                    report["recommendation_logs"] += len(batch)
                    batch.clear()
            if batch:
                db.bulk_insert_mappings(RecommendationLog, batch)
                report["recommendation_logs"] += len(batch)
            db.commit()

        # Optional later-version tables are copied only when their old columns match.
        if _table_exists(source, "watchlists"):
            batch = []
            for row in _iter_rows(source, "watchlists", batch_size):
                title_id = old_movie_to_title.get(int(row.get("movie_id", -1))) or row.get("title_id")
                if title_id and int(row.get("user_id", -1)) in user_ids:
                    batch.append({"id": _value(row, "id"), "user_id": int(row["user_id"]),
                                  "title_id": title_id,
                                  "created_at": _parse_datetime(_value(row, "created_at")) or datetime.now(timezone.utc)})
            if batch:
                db.bulk_insert_mappings(Watchlist, batch)
                report["watchlists"] = len(batch)
                db.commit()

        if _table_exists(source, "interactions"):
            batch = []
            for row in _iter_rows(source, "interactions", batch_size):
                title_id = old_movie_to_title.get(int(row.get("movie_id", -1))) or row.get("title_id")
                if title_id and int(row.get("user_id", -1)) in user_ids:
                    batch.append({"user_id": int(row["user_id"]), "title_id": title_id,
                                  "event_type": str(_value(row, "event_type", "unknown"))[:32],
                                  "value": float(_value(row, "value", 1.0)),
                                  "occurred_at": _parse_datetime(_value(row, "occurred_at")) or datetime.now(timezone.utc),
                                  "metadata_json": _value(row, "metadata_json")})
            if batch:
                db.bulk_insert_mappings(Interaction, batch)
                report["interactions"] = len(batch)
                db.commit()

        if report["movies"]:
            report["catalogue_sort"] = rebuild_catalogue_sort_index(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        source.close()
        engine.dispose()

    # SQLite integrity validation after data writes complete.
    verify = sqlite3.connect(destination_path)
    fk_errors = verify.execute("PRAGMA foreign_key_check").fetchall()
    verify.close()
    if fk_errors:
        raise RuntimeError(f"Foreign-key check failed: {fk_errors[:10]}")
    report["foreign_key_violations"] = 0
    report["note"] = "User password hashes are preserved only if present in source. Users without hashes must reset their password."
    report_path = destination_path.with_suffix(destination_path.suffix + ".migration-report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Existing legacy SQLite database (read-only)")
    parser.add_argument("--destination", required=True, type=Path, help="New destination SQLite database")
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    result = migrate(args.source, args.destination, args.batch_size)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
