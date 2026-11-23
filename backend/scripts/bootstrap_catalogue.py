#!/usr/bin/env python3
"""Safely bootstrap the sanitized MovieLens catalogue into a new database.

An empty database receives the bundled seed. A database with an unrelated
catalogue is left untouched. A partially imported copy of the seed is treated
as an error and requires manual inspection instead of an automatic merge.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.entities import Movie
from scripts.import_catalogue_seed import DEFAULT_SEED, parse_seed, run


def main() -> int:
    records = parse_seed(DEFAULT_SEED)
    seed_ids = {str(row["title_id"]) for row in records}
    db = SessionLocal()
    try:
        current_count = int(db.query(func.count(Movie.title_id)).scalar() or 0)
        existing_seed_ids = {
            str(value)
            for (value,) in db.query(Movie.title_id)
            .filter(Movie.title_id.in_(seed_ids))
            .all()
        }
    finally:
        db.close()

    if current_count == 0:
        print("Catalogue is empty; importing the bundled sanitized seed.")
        run(DEFAULT_SEED, apply=True)
        return 0

    if existing_seed_ids == seed_ids:
        print("Bundled catalogue seed is already present; no changes required.")
        return 0

    if existing_seed_ids:
        raise RuntimeError(
            "The database contains only part of the bundled catalogue seed. "
            "Refusing an automatic partial import; inspect the catalogue first."
        )

    print(
        f"Existing catalogue detected ({current_count} titles); "
        "leaving it unchanged and skipping the bundled seed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
