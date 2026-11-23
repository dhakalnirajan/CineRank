#!/usr/bin/env python3
"""
CineRank External Data Import

Imports movie data from external datasets into the CineRank database.
Focuses on adding data from CSV and parquet files while being idempotent.

Usage:
    python import_external.py --source tmdb-imdb   # TMDB-IMDB merged dataset
    python import_external.py --source 9000plus     # 9000plus dataset
    python import_external.py --source imdb-media   # IMDB media metadata
    python import_external.py --source tv-parquet   # TV shows from parquet
    python import_external.py --source all          # All datasets
    python import_external.py --dry-run           # Preview only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.entities import Movie


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]
EXTERNAL_DIR = BASE_DIR / "data" / "external"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def hash_title(title: str, year: int | None) -> str:
    """Generate a stable title_id from title and year."""
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
# Source: TMDB-IMDB-Movies-Dataset.csv
# ──────────────────────────────────────────────────────────────────────

def import_tmdb_imdb(csv_path: str, db: Session, dry_run: bool = False) -> int:
    """Import from TMDB-IMDB-Movies-Dataset.csv."""
    print(f"Importing TMDB-IMDB dataset: {csv_path}")

    if not os.path.exists(csv_path):
        print("  File not found, skipping.")
        return 0

    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8", on_bad_lines="skip")
    print(f"  Rows in file: {len(df)}")

    # Get existing title_ids and IMDB/TMDB IDs
    existing_title_ids = {m.title_id for m in db.query(Movie).all()}
    existing_imdb_ids = {m.imdb_id for m in db.query(Movie).all() if m.imdb_id}
    existing_tmdb_ids = {m.tmdb_id for m in db.query(Movie).all() if m.tmdb_id}

    imported = 0
    skipped = 0

    for i, row in df.iterrows():
        try:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue

            # Check duplicates
            tmdb_id_val = safe_int(row.get("id"))
            imdb_id_val = extract_imdb_id(row.get("tconst"))

            # Skip if already in DB by TMDB ID
            if tmdb_id_val and tmdb_id_val in existing_tmdb_ids:
                skipped += 1
                continue
            # Skip if already in DB by IMDB ID
            if imdb_id_val and imdb_id_val in existing_imdb_ids:
                skipped += 1
                continue
            # Skip if already in DB by title (case-insensitive)
            title_hash = hash_title(title, safe_int(row.get("year")))
            if title_hash in existing_title_ids:
                skipped += 1
                continue

            # Parse fields
            year = safe_int(row.get("year"))
            vote_avg = safe_float(row.get("vote_average"))
            vote_count = safe_int(row.get("vote_count"))
            runtime = safe_int(row.get("runtime"))
            budget = safe_float(row.get("budget"))
            revenue = safe_float(row.get("revenue"))
            overview = (row.get("overview") or "")[:500]
            genres = normalize_genres(row.get("genres"))
            popularity = safe_float(row.get("popularity"))
            poster_path = row.get("poster_path", "").strip() or None
            backdrop_path = row.get("backdrop_path", "").strip() or None
            original_language = row.get("original_language", "").strip() or None

            # Generate title_id
            title_id = title_hash if not title_hash.startswith("title_") else f"title_{title_hash[-8:]}"
            if not title_id.startswith("title_"):
                title_id = f"title_{title_id}"

            # Generate serial_number
            serial = safe_int(row.get("serial_number", 0))

            movie = Movie(
                title_id=title_id,
                serial_number=serial,
                
                title=title,
                original_title=(row.get("original_title") or title)[:512],
                year=year,
                overview=overview,
                vote_average=vote_avg,
                vote_count=vote_count,
                runtime=runtime,
                budget=budget,
                revenue=revenue,
                popularity=popularity,
                genres=genres,
                tmdb_id=tmdb_id_val,
                imdb_id=imdb_id_val,
                
                source="tmdb_imdb_merged",
                source_domain="TMDB-IMDB-Movies-Dataset.csv",
            )

            db.add(movie)
            imported += 1
            existing_title_ids.add(title_id)

            # Commit in batches of 1000
            if imported % 1000 == 0:
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
# Source: 9000plus.csv
# ──────────────────────────────────────────────────────────────────────

def import_9000plus(csv_path: str, db: Session, dry_run: bool = False) -> int:
    """Import from 9000plus.csv."""
    print(f"Importing 9000plus.csv: {csv_path}")

    if not os.path.exists(csv_path):
        print("  File not found, skipping.")
        return 0

    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8", on_bad_lines="skip")
    print(f"  Rows in file: {len(df)}")

    existing_title_ids = {m.title_id for m in db.query(Movie).all()}
    imported = 0
    skipped = 0

    for i, row in df.iterrows():
        try:
            title = (row.get("Title") or "").strip()
            if not title:
                skipped += 1
                continue

            # Skip duplicates
            title_hash = hash_title(title, safe_int(row.get("Release_Date", "").split("-")[0] if row.get("Release_Date") else None))
            if title_hash in existing_title_ids:
                skipped += 1
                continue

            year = safe_int(row.get("Release_Date", "").split("-")[0] if row.get("Release_Date") else None)
            vote_avg = safe_float(row.get("Vote_Average"))
            vote_count = safe_int(row.get("Vote_Count"))
            popularity = safe_float(row.get("Popularity"))
            genres = normalize_genres(row.get("Genre"))
            overview = (row.get("Overview") or "")[:500]
            poster = row.get("Poster_Url", "").strip() or None

            title_id = title_hash if not title_hash.startswith("title_") else f"title_{title_hash[-8:]}"
            if not title_id.startswith("title_"):
                title_id = f"title_{title_id}"

            movie = Movie(
                title_id=title_id,
                serial_number=safe_int(row.get("serial_number", 0)),
                
                title=title,
                year=year,
                overview=overview,
                vote_average=vote_avg,
                vote_count=vote_count,
                popularity=popularity,
                genres=genres,
                imdb_id=row.get("IMDB_ID", "").strip() or None,
                source="9000plus",
                source_domain="9000plus.csv",
            )

            db.add(movie)
            imported += 1
            existing_title_ids.add(title_id)

            if imported % 1000 == 0:
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
# Source: imdb-media.csv
# ──────────────────────────────────────────────────────────────────────

def import_imdb_media(csv_path: str, db: Session, dry_run: bool = False) -> int:
    """Import from imdb-media.csv."""
    print(f"Importing IMDB media metadata: {csv_path}")

    if not os.path.exists(csv_path):
        print("  File not found, skipping.")
        return 0

    # Use DictReader for named columns
    imported = 0
    skipped = 0
    seen_ids = set()

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader):
            try:
                title = (row.get("title", "") or "").strip()
                if not title:
                    skipped += 1
                    continue

                # Skip duplicates
                title_key = hash_title(title, safe_int(row.get("year")))
                if title_key in seen_ids:
                    skipped += 1
                    continue
                seen_ids.add(title_key)

                # Also check DB
                title_id_candidate = title_key if not title_key.startswith("title_") else f"title_{title_key[-8:]}"
                if not title_id_candidate.startswith("title_"):
                    title_id_candidate = f"title_{title_id_candidate}"

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
                    media_type="movie",
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

                # Commit every 5000 rows
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
# Source: tv-details.parquet
# ──────────────────────────────────────────────────────────────────────

def import_tv_parquet(parquet_path: str, db: Session, dry_run: bool = False) -> int:
    """Import TV shows from parquet file."""
    print(f"Importing TV parquet: {parquet_path}")

    if not os.path.exists(parquet_path):
        print("  File not found, skipping.")
        return 0

    df = pd.read_parquet(parquet_path)
    print(f"  Rows in file: {len(df)}")

    imported = 0
    skipped = 0
    existing_titles = {m.title.lower() for m in db.query(Movie).filter(Movie.media_type == "tv").all()}

    for i, row in df.iterrows():
        try:
            title = str(row.get("name", "")).strip()
            if not title:
                skipped += 1
                continue

            # Skip if already in DB
            if title.lower() in existing_titles:
                skipped += 1
                continue

            year = None
            first_air = str(row.get("first_air_date", "") or "").strip()
            if first_air:
                y = re.search(r"\d{4}", first_air)
                if y:
                    year = int(y.group(0))

            genres = normalize_genres(row.get("genres"))
            popularity = safe_float(row.get("popularity"))
            vote_avg = safe_float(row.get("vote_average"))
            vote_count = safe_int(row.get("vote_count"))
            overview = (str(row.get("overview")) or "")[:500] if pd.notna(row.get("overview")) else None

            title_id = hash_title(title, year)
            if not title_id.startswith("title_"):
                title_id = f"title_{title_id}"

            # Skip if title_id already exists
            if db.query(Movie).filter(Movie.title_id == title_id).first():
                skipped += 1
                continue

            movie = Movie(
                title_id=title_id,
                serial_number=0,
                
                title=title,
                year=year,
                overview=overview,
                vote_average=vote_avg,
                vote_count=vote_count,
                popularity=popularity,
                genres=genres,
                imdb_id=None,
                source="tv_parquet",
                source_domain="tv-details.parquet",
                directors_json="[]",
                cast_json="[]",
                is_adult=safe_int(row.get("in_production")) if False else 0,
            )

            db.add(movie)
            imported += 1
            existing_titles.add(title.lower())

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
# Main
# ──────────────────────────────────────────────────────────────────────

def import_all_data(dry_run: bool = False) -> None:
    """Import all external data sources."""
    print("=" * 60)
    print("CINEHANK EXTERNAL DATA IMPORT")
    print("=" * 60)
    print()

    db = SessionLocal()

    try:
        existing = db.query(Movie).count()
        print(f"Existing movies in DB: {existing}")

        sources = {
            "tmdb-imdb": import_tmdb_imdb,
            "9000plus": import_9000plus,
            "imdb-media": import_imdb_media,
            "tv-parquet": import_tv_parquet,
        }

        total_imported = 0
        total_skipped = 0

        for source_name, import_func in sources.items():
            print(f"\n--- {source_name} ---")
            imported, skipped = import_func(
                str(EXTERNAL_DIR / {"tmdb-imdb": "TMDB-IMDB-Movies-Dataset.csv",
                                    "9000plus": "9000plus.csv",
                                    "imdb-media": "imdb-media.csv",
                                    "tv-parquet": "tv-details.parquet"}[source_name]),
                db,
                dry_run=dry_run,
            )
            total_imported += imported
            total_skipped += skipped

        final_count = db.query(Movie).count()
        print(f"\n=== SUMMARY ===")
        print(f"Before: {existing} movies")
        print(f"After:  {final_count} movies")
        print(f"New:    {final_count - existing} movies")
        print(f"Skipped (duplicates): {total_skipped}")
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
        description="CineRank External Data Import Script"
    )
    parser.add_argument(
        "--source",
        choices=["all", "tmdb-imdb", "9000plus", "imdb-media", "tv-parquet"],
        default="all",
        help="Data source to import",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview only, do not write to database",
    )
    args = parser.parse_args()

    if args.source == "all":
        import_all_data(dry_run=args.dry_run)
    else:
        # Single source import
        db = SessionLocal()
        source_map = {
            "tmdb-imdb": import_tmdb_imdb,
            "9000plus": import_9000plus,
            "imdb-media": import_imdb_media,
            "tv-parquet": import_tv_parquet,
        }
        func = source_map[args.source]
        csv_map = {
            "tmdb-imdb": "TMDB-IMDB-Movies-Dataset.csv",
            "9000plus": "9000plus.csv",
            "imdb-media": "imdb-media.csv",
            "tv-parquet": "tv-details.parquet",
        }

        csv_path = EXTERNAL_DIR / csv_map[args.source]
        imported, skipped = func(str(csv_path), db, dry_run=args.dry_run)
        db.close()

    print("\nDone.")


if __name__ == "__main__":
    main()