#!/usr/bin/env python3
"""
CineRank Data Import Script

Idempotent import of external data files into the CineRank database.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

import pandas as pd

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.entities import Movie

# ──────────────────────────────────────────────────────────────────────
# Project configuration
# ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(r"E:\E Drive\Projects\CineRank-Third")
EXTERNAL_DIR = PROJECT_ROOT / "backend" / "data" / "external"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def hash_title(title: str, year: int | None) -> str:
    """Generate a stable title_id from title and year."""
    import hashlib
    key = f"{title}_{year}" if year else title
    return f"title_{hashlib.md5(key.encode()).hexdigest()[:8]}"


def normalize_genres(genre_str) -> str:
    """Ensure genres are pipe-separated."""
    if not genre_str:
        return ""
    if isinstance(genre_str, list):
        return "|".join(genre_str)
    return str(genre_str).replace("/", "|")


def safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def extract_imdb_id(val) -> str | None:
    """Extract tt####### from various IMDB ID formats."""
    if not val:
        return None
    m = re.search(r"tt\d+", str(val))
    return m.group(0) if m else None


# ──────────────────────────────────────────────────────────────────────
# Source: 9000plus.csv - Small file, quick import
# ──────────────────────────────────────────────────────────────────────

def import_9000plus(csv_path: str, db: Session, dry_run: bool = False) -> tuple[int, int]:
    """Import from 9000plus.csv - smaller dataset."""
    print(f"Importing 9000plus.csv")

    if not os.path.exists(csv_path):
        print("  File not found, skipping.")
        return 0, 0

    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8", on_bad_lines="skip")
    print(f"  Rows in file: {len(df)}")

    # Get existing title_ids from DB
    existing_ids = {m.title_id for m in db.query(Movie).all()}
    imported = 0
    skipped = 0

    for i, row in df.iterrows():
        try:
            title = (row.get("Title") or "").strip()
            if not title:
                skipped += 1
                continue

            # Generate title_id
            year_raw = row.get("Release_Date", "").strip()
            year = None
            if year_raw:
                try:
                    year = int(year_raw.split("-")[0])
                except (ValueError, TypeError):
                    pass

            title_id = hash_title(title, year)
            if not title_id.startswith("title_"):
                title_id = f"title_{title_id}"

            # Skip if already exists
            if title_id in existing_ids:
                skipped += 1
                continue

            # Check for duplicate by title (case-insensitive)
            title_lower = title.lower()
            if any(m.title.lower() == title_lower for m in db.query(Movie).all()):
                skipped += 1
                continue

            vote_avg = safe_float(row.get("Vote_Average"))
            vote_count = safe_int(row.get("Vote_Count"))
            popularity = safe_float(row.get("Popularity"))
            genres = normalize_genres(row.get("Genre"))
            overview = (row.get("Overview") or "")[:500]
            imdb_id = row.get("IMDB_ID", "").strip() or None

            movie = Movie(
                title_id=title_id,
                serial_number=safe_int(row.get("serial_number", 0)),
                media_type="movie",
                title=title,
                year=year,
                overview=overview,
                vote_average=vote_avg,
                vote_count=vote_count,
                popularity=popularity,
                genres=genres,
                imdb_id=imdb_id,
                source="9000plus",
                source_domain="9000plus.csv",
            )

            db.add(movie)
            imported += 1
            existing_ids.add(title_id)

            if imported % 5000 == 0:
                if not dry_run:
                    db.commit()
                print(f"  Progress: {imported} imported, {skipped} skipped")

        except Exception as e:
            skipped += 1
            if skipped <= 3:
                print(f"  Error on row {i}: {e}")

    if not dry_run:
        db.commit()

    print(f"  Complete: {imported} imported, {skipped} skipped")
    return imported, skipped


# ──────────────────────────────────────────────────────────────────────
# Source: IMDB media metadata
# ──────────────────────────────────────────────────────────────────────

def import_imdb_media(csv_path: str, db: Session, dry_run: bool = False) -> tuple[int, int]:
    """Import from imdb-media.csv."""
    print(f"Importing IMDB media metadata")

    if not os.path.exists(csv_path):
        print("  File not found, skipping.")
        return 0, 0

    imported = 0
    skipped = 0

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader):
            try:
                title = (row.get("title", "") or "").strip()
                if not title:
                    skipped += 1
                    continue

                # Generate title_id
                title_key = hash_title(title, safe_int(row.get("year")))
                title_id_candidate = title_key if not title_key.startswith("title_") else f"title_{title_key[-8:]}"

                # Skip if already in DB
                if db.query(Movie).filter(Movie.title_id == title_id_candidate).first():
                    skipped += 1
                    continue

                imdb_id = extract_imdb_id(row.get("imdb_id"))
                popularity = safe_float(row.get("popularity"))
                genres = normalize_genres(row.get("genres"))
                overview = (row.get("storyline") or row.get("overview") or "")[:500]
                year = None
                rel_date = (row.get("details_release_date") or "").strip()
                if rel_date:
                    y = re.search(r"\d{4}", rel_date)
                    if y:
                        year = int(y.group(0))

                budget = row.get("budget", "").strip() or None

                movie = Movie(
                    title_id=title_id_candidate,
                    serial_number=0,
                    media_type=(row.get("media_type", "movie") or "movie").strip(),
                    title=title,
                    year=year,
                    overview=overview,
                    vote_average=safe_float(row.get("imdb_rating")),
                    vote_count=safe_int(row.get("imdb_rating_count")),
                    popularity=popularity,
                    genres=genres,
                    imdb_id=imdb_id,
                    source="imdb_media",
                    source_domain="imdb-media.csv",
                    directors_json="[]",
                    cast_json="[]",
                    is_adult=safe_int(row.get("is_adult")) if row.get("is_adult") else 0,
                )

                db.add(movie)
                imported += 1

                if imported % 5000 == 0:
                    if not dry_run:
                        db.commit()
                    print(f"  Progress: {imported} imported, {skipped} skipped")

            except Exception as e:
                skipped += 1
                if skipped <= 5:
                    print(f"  Error on row {i}: {e}")

    if not dry_run:
        db.commit()

    print(f"  Complete: {imported} imported, {skipped} skipped")
    return imported, skipped


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def import_all(dry_run: bool = False) -> None:
    """Import all external data sources."""
    print("=" * 60)
    print("CINEHANK DATA IMPORT")
    print("=" * 60)
    print()

    db = SessionLocal()

    try:
        existing = db.query(Movie).count()
        print(f"Existing movies in DB: {existing}")

        # Import 9000plus first (smaller file)
        print("\n--- 9000plus.csv ---")
        csv_9000 = str(EXTERNAL_DIR / "9000plus.csv")
        if os.path.exists(csv_9000):
            imported, skipped = import_9000plus(csv_9000, db, dry_run=dry_run)
        else:
            imported, skipped = 0, 0
            print("  File not found")

        # Import IMDB media
        print("\n--- imdb-media.csv ---")
        csv_imdb = str(EXTERNAL_DIR / "imdb-media.csv")
        if os.path.exists(csv_imdb):
            imported2, skipped2 = import_imdb_media(csv_imdb, db, dry_run=dry_run)
        else:
            imported2, skipped2 = 0, 0
            print("  File not found")

        total_imported = imported + imported2
        total_skipped = skipped + skipped2

        final_count = db.query(Movie).count()
        print(f"\n=== SUMMARY ===")
        print(f"Before: {existing} movies")
        print(f"After:  {final_count} movies")
        print(f"New:    {final_count - existing} movies")
        print(f"Skipped: {total_skipped} (duplicates or errors)")
        print("=" * 60)

    except Exception as e:
        print(f"\nImport failed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CineRank Data Import Script"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview only, do not write to database",
    )
    args = parser.parse_args()

    import_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()