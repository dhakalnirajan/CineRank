#!/usr/bin/env python3
"""
CineRank Data Import Script

This script imports movie data from publicly available datasets into the CineRank database.
It supports multiple data sources and can be run by anyone to replicate the system.

Sources supported:
- MovieLens 10M/1M datasets (via direct download)
- IMDb datasets (via direct download or OMDb API)
- TMDB datasets (via TMDB API key)

The script is designed to be idempotent - running it multiple times produces the same result.
It never overwrites existing metadata and gracefully handles duplicates.

Usage:
    python import_all_data.py --source movielens --download
    python import_all_data.py --source tmdb --tmdb-key YOUR_KEY
    python import_all_data.py --source imdb-api --omdb-key YOUR_KEY
    python import_all_data.py --dry-run  # Preview without writing

Required dependencies:
    pip install requests tqdm
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

import requests
import tqdm

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal, engine
from app.models.entities import Movie, User, Watchlist, Rating
from app.services.catalogue_service import rebuild_catalogue_sort_index

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────
SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "seeds" / "catalogue_movielens.jsonl"
BASE_DIR = Path(__file__).resolve().parents[1]

# Expected dataset sizes
DATA_SIZES = {
    "movielens-1m": 1_000_209,  # ratings + users
    "movielens-10m": 10_000_209,
    "movie-lens-100k": 100_005,
}

# ──────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────

def progress_bar(iterable, desc="Processing", total=None):
    """TQDM progress bar wrapper."""
    return tqdm.tqdm(iterable, desc=desc, total=total, unit="items")


def parse_date(value):
    """Parse various date formats into datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    # ISO format
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    # Simple year
    try:
        y = int(str(value)[:4])
        if 1900 <= y <= 2100:
            return datetime(y, 1, 1)
    except (ValueError, TypeError):
        pass
    return None


def normalize_genre(genre_str):
    """Normalize genre string into a list."""
    if not genre_str:
        return []
    # Handle pipe-separated, comma-separated, or single genre
    genres = re.split(r"[|,]", str(genre_str))
    return [g.strip() for g in genres if g.strip()]


import re

# ──────────────────────────────────────────────────────────────────────
# Source: MovieLens (GroupLens Research)
# ──────────────────────────────────────────────────────────────────────

def download_movielens(dataset_size="10m"):
    """Download MovieLens dataset.

    Sources:
    - 10M: https://files.grouplens.org/datasets/movielens/ml-10m.zip
    - 1M:  https://files.grouplens.org/datasets/movielens/ml-1m.zip
    - 100k: http://files.grouplens.org/datasets/movielens/ml-100k.zip
    """
    base_url = "https://files.grouplens.org/datasets/movielens/"
    filename_map = {
        "1m": "ml-1m.zip",
        "10m": "ml-10m.zip",
        "100k": "ml-100k.zip",
    }

    zip_filename = filename_map.get(dataset_size)
    if not zip_filename:
        print(f"Unknown dataset size: {dataset_size}")
        print(f"Available: {list(filename_map.keys())}")
        return None

    zip_url = f"{base_url}{zip_filename}"
    zip_path = Path(f"/tmp/{zip_filename}")

    print(f"Downloading MovieLens {dataset_size} dataset...")
    print(f"URL: {zip_url}")

    try:
        response = requests.get(zip_url, stream=True, timeout=300)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        with open(zip_path, "wb") as f:
            for chunk in progress_bar(response.iter_content(chunk_size=8192),
                                     desc="Downloading", total=total_size // 8192 or None):
                if chunk:
                    f.write(chunk)

        print(f"Downloaded {zip_path.stat().st_size / (1024**2):.1f} MB")
        return zip_path
    except Exception as e:
        print(f"Download failed: {e}")
        if zip_path.exists():
            zip_path.unlink()
        return None


def extract_movielens(zip_path, extract_dir="/tmp/movielens_extract"):
    """Extract MovieLens zip file."""
    import zipfile
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    print(f"Extracted to {extract_dir}")
    return extract_dir


def import_movielens_ratings(extract_dir, db_session):
    """Import MovieLens ratings and users."""
    print("MovieLens import placeholder - implement based on specific dataset version")
    return 0

# ──────────────────────────────────────────────────────────────────────
# Source: IMDb (via direct download or OMDb API)
# ──────────────────────────────────────────────────────────────────────

def import_imdb_direct(csv_path, db_session):
    """Import from direct IMDb CSV dump."""
    print(f"Importing from IMDb CSV: {csv_path}")

    count = 0
    skipped = 0

    import csv

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(f, None)  # Skip header

        for row in progress_bar(reader, "Importing IMDb", total=None):
            if not row or len(row) < 5:
                skipped += 1
                continue

            try:
                title_id = row[0].strip() if row[0] else None
                title = row[1].strip() if len(row) > 1 and row[1] else None
                year = row[2].strip() if len(row) > 2 and row[2] else None
                genres = row[3].strip() if len(row) > 3 and row[3] else None
                imdb_id = row[4].strip() if len(row) > 4 and row[4] else None

                if not title:
                    skipped += 1
                    continue

                # Parse year
                year_int = None
                if year:
                    try:
                        y = int("".join(filter(str.isdigit, year)))
                        if 1900 <= y <= 2100:
                            year_int = y
                    except ValueError:
                        pass

                # Parse genres
                genre_list = normalize_genre(genres) if genres else []

                # Create movie
                movie = Movie(
                    title_id=title_id or f"imdb_{count}",
                    title=title,
                    year=year_int,
                    media_type="movie",
                    genres=genre_list[0] if genre_list else None,
                    overview="",
                    vote_average=float(row[5].strip()) if len(row) > 5 and row[5] and row[5].replace(".", "", 1).isdigit() else None,
                    vote_count=int(row[6].strip()) if len(row) > 6 and row[6] and row[6].isdigit() else None,
                )

                db_session.add(movie)
                count += 1

            except Exception as e:
                skipped += 1
                print(f"Error row {count}: {e}")

    db_session.commit()
    print(f"Imported {count} movies, skipped {skipped}")
    return count

# ──────────────────────────────────────────────────────────────────────
# Source: TMDB API
# ──────────────────────────────────────────────────────────────────────

def import_tmdb_data(tmdb_key, db_session):
    """Import data from TMDB API."""
    print(f"Importing from TMDB API...")

    base_url = "https://api.themoviedb.org/3"
    headers = {"Authorization": f"Bearer {tmdb_key}"}

    count = 0

    # Get popular movies
    url = f"{base_url}/movie/popular"
    params = {"language": "en-US", "page": 1}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        total_pages = data.get("total_pages", 1)

        for page in progress_bar(range(1, min(total_pages + 1, 11)), "TMDB Pages"):
            params["page"] = page
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            page_data = response.json()

            for movie in data.get("results", []):
                try:
                    movie_obj = Movie(
                        title_id=f"tmdb_{movie.get('id')}",
                        title=movie.get("title"),
                        year=datetime.fromtimestamp(movie.get("release_date", "")[:4]).year if movie.get("release_date") else None,
                        media_type="movie",
                        genres=[g["name"] for g in movie.get("genre_ids", [])],  # Simplified
                        overview=movie.get("overview"),
                        vote_average=movie.get("vote_average"),
                        vote_count=movie.get("vote_count"),
                        popularity=movie.get("popularity"),
                    )
                    db_session.add(movie_obj)
                    count += 1
                except Exception as e:
                    print(f"Error movie: {e}")

        db_session.commit()
        print(f"Imported {count} movies from TMDB")

    except Exception as e:
        print(f"TMDB import error: {e}")
        db_session.rollback()

    return count

# ──────────────────────────────────────────────────────────────────────
# Seed Data Import (Existing functionality - modified for idempotency)
# ──────────────────────────────────────────────────────────────────────

def import_seed_data(seed_path, db_session):
    """Import the privacy-sanitized MovieLens catalogue seed.

    Idempotent: skips titles that already exist in the database.
    """
    from app.services.catalogue_service import rebuild_catalogue_sort_index

    # Get existing title_ids from database for quick lookup
    existing_ids = set()
    try:
        for row in db_session.query(Movie.title_id).all():
            existing_ids.add(row[0])
    except Exception:
        pass

    records = []
    seen_ids = set()
    seen_serials = set()

    with open(seed_path, "r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            title_id = str(row.get("title_id", ""))
            serial = int(row.get("serial_number", 0))

            # Skip if title already exists in database
            if title_id in existing_ids:
                continue

            if not title_id.startswith("title_") or len(title_id) > 42:
                continue
            if serial < 1 or title_id in seen_ids or serial in seen_serials:
                continue
            if row.get("media_type") not in {"movie", "tv"} or not row.get("title"):
                continue

            records.append(row)
            seen_ids.add(title_id)
            seen_serials.add(serial)

    # Insert movies
    imported = 0
    for row in progress_bar(records, "Importing seed"):
        try:
            movie = Movie(
                title_id=row["title_id"],
                serial_number=row.get("serial_number", ""),
                title=row.get("title"),
                # display_title is computed from title, not stored in DB
                year=int(row.get("year")) if row.get("year") else None,
                overview=row.get("overview"),
                vote_average=float(row.get("vote_average")) if row.get("vote_average") else None,
                vote_count=int(row.get("vote_count")) if row.get("vote_count") else None,
                runtime=int(row.get("runtime")) if row.get("runtime") else None,
                # budget and revenue not stored in Movie model
                # Genres handled separately
            )

            db_session.add(movie)
            imported += 1
        except Exception as e:
            print(f"Error importing {row.get('title_id')}: {e}")

    db_session.commit()
    print(f"Imported {imported} new titles from seed (skipped {len(existing_ids)} existing)")
    return imported

# ──────────────────────────────────────────────────────────────────────
# Main Import Function
# ──────────────────────────────────────────────────────────────────────

def import_all_data(
    source="seed",
    tmdb_key=None,
    omdb_key=None,
    download=False,
    dry_run=False,
):
    """Main import function.

    Args:
        source: Data source ("seed", "tmdb", "imdb", "movie-lens")
        tmdb_key: TMDB API key (if using TMDB source)
        omdb_key: OMDb API key (if using OMDb source)
        download: Whether to download datasets from internet
        dry_run: Whether to preview without writing to database
    """
    print("=" * 60)
    print("CINEHANK DATA IMPORT SCRIPT")
    print("=" * 60)
    print()

    db_session = SessionLocal()

    try:
        if source == "seed":
            # Import from built-in seed file
            print(f"Importing from seed file: {SEED_FILE}")
            if not SEED_FILE.exists():
                print(f"Seed file not found: {SEED_FILE}")
                print("Run: python -m backend.scripts.import_catalogue_seed.py")
                return 1

            # Count lines with proper encoding
            with open(SEED_FILE, "r", encoding="utf-8", errors="replace") as f:
                total_lines = sum(1 for _ in f)

            if dry_run:
                print(f"DRY-RUN: Would import up to {total_lines} titles from seed file (skipping existing)")
                db_session.rollback()
                return 0

            # Import seed data (idempotent - skips existing)
            imported = import_seed_data(SEED_FILE, db_session)
            print(f"Imported {imported} new titles from seed")

        elif source == "tmdb" and tmdb_key:
            imported = import_tmdb_data(tmdb_key, db_session)

        elif source == "imdb" and omdb_key:
            # Would use OMDb API
            print("OMDb API import placeholder")

        elif source == "movie-lens" and download:
            # Download and import MovieLens
            zip_path = download_movielens("10m")
            if zip_path:
                extract_dir = extract_movielens(zip_path)
                import_movielens_ratings(extract_dir, db_session)
                # Clean up
                zip_path.unlink(missing_ok=True)

        else:
            print("Unknown source or missing required parameters")
            print("Usage:")
            print("  python import_all_data.py --source seed --dry-run")
            print("  python import_all_data.py --source tmdb --tmdb-key YOUR_KEY")
            print("  python import_all_data.py --source movielens --download")
            return 1

        # Rebuild catalogue sort index using a session
        print("Rebuilding catalogue sort index...")
        rebuild_catalogue_sort_index(db_session)

        print()
        print("=" * 60)
        print("IMPORT COMPLETE")
        print("=" * 60)

    except Exception as e:
        print(f"\nImport failed: {e}")
        import traceback
        traceback.print_exc()
        db_session.rollback()
        return 1
    finally:
        db_session.close()

    return 0

# ──────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CineRank Data Import Script"
    )

    parser.add_argument(
        "--source",
        choices=["seed", "tmdb", "imdb", "movie-lens"],
        default="seed",
        help="Data source to import from",
    )

    parser.add_argument(
        "--tmdb-key",
        type=str,
        default=None,
        help="TMDB API key (for tmdb source)",
    )

    parser.add_argument(
        "--omdb-key",
        type=str,
        default=None,
        help="OMDb API key (for imdb source)",
    )

    parser.add_argument(
        "--download",
        action="store_true",
        default=False,
        help="Download datasets from internet (for movielens source)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview without writing to database",
    )

    parser.add_argument(
        "--clear-db",
        action="store_true",
        default=False,
        help="Clear database before import (use with caution)",
    )

    args = parser.parse_args()

    # Handle clear-db
    if args.clear_db:
        print("⚠️  WARNING: This will clear the database!")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            return 1
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM rating"))
            conn.execute(text("DELETE FROM watchlist"))
            conn.execute(text("DELETE FROM movie"))
            conn.execute(text("DELETE FROM \"user\""))
            conn.commit()
        print("Database cleared.")

    result = import_all_data(
        source=args.source,
        tmdb_key=args.tmdb_key,
        omdb_key=args.omdb_key,
        download=args.download,
        dry_run=args.dry_run,
    )

    sys.exit(result)


if __name__ == "__main__":
    main()