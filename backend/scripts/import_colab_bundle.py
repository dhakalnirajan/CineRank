#!/usr/bin/env python3
"""Verify a Colab artifact bundle, import its training sample, and atomically activate it."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects import postgresql, sqlite, mysql

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.ids import generate_title_id
from app.core.serial_numbers import allocate_title_serial_numbers
from app.db.session import Base, SessionLocal, engine
from app.models.entities import Movie, User, Rating, JobRun
from app.services.catalogue_service import make_sort_key, rebuild_catalogue_sort_index

REQUIRED_FILES = {
    "manifest.json", "SHA256SUMS", "id-maps-v1.json", "catalogue.csv",
    "ratings_sample.csv", "holdout_sample.csv", "rec-pop-v1.npz",
    "rec-content-v1.npz", "rec-content-v1-meta.json", "rec-itemknn-v1.npz",
    "rec-als-v1.npz", "rec-bpr-v1.npz", "rec-attn-v1.pt", "rec-hybrid-v1.json",
    "train-mat-v1.npz", "relevance-mat-v1.npz",
}


def verify_bundle(bundle_dir: Path) -> dict:
    missing = sorted(name for name in REQUIRED_FILES if not (bundle_dir / name).is_file())
    if missing:
        raise ValueError("Bundle is missing required files: " + ", ".join(missing))
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("bundle_format") != "cinerank-portable-v1":
        raise ValueError("Unsupported bundle format")
    bundle_id = str(manifest.get("bundle_id", ""))
    if not bundle_id or any(ch not in "0123456789abcdef-" for ch in bundle_id.lower()):
        raise ValueError("Invalid or missing bundle_id")
    seen = set()
    for line in (bundle_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, filename = line.split(None, 1)
        filename = filename.strip()
        if Path(filename).name != filename or filename in seen:
            raise ValueError(f"Unsafe or duplicate checksum filename: {filename}")
        seen.add(filename)
        path = bundle_dir / filename
        if not path.is_file():
            raise ValueError(f"Missing bundle file: {filename}")
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != digest:
            raise ValueError(f"SHA-256 mismatch: {filename}")
    required_payload = REQUIRED_FILES - {"SHA256SUMS"}
    if required_payload - seen:
        raise ValueError("Checksum manifest does not cover all required files")

    # The bundle ID is a deterministic digest of all payload files, excluding
    # the manifest and checksum file themselves. Recompute it rather than
    # trusting a self-declared ID in an otherwise checksum-valid manifest.
    bundle_parts = []
    for filename in sorted(name for name in seen if name not in {"manifest.json", "SHA256SUMS"}):
        payload_digest = hashlib.sha256((bundle_dir / filename).read_bytes()).digest()
        bundle_parts.append(filename.encode() + b"\0" + payload_digest)
    computed_id = hashlib.sha256(b"".join(bundle_parts)).hexdigest()[:32]
    if computed_id != bundle_id:
        raise ValueError("bundle_id does not match the content-addressed payload")

    id_maps = json.loads((bundle_dir / "id-maps-v1.json").read_text(encoding="utf-8"))
    if len(id_maps.get("idx_to_source_user_id", [])) != int(manifest.get("n_users", -1)):
        raise ValueError("User ID map length does not match manifest n_users")
    if len(id_maps.get("idx_to_movielens_movie_id", [])) != int(manifest.get("n_items", -1)):
        raise ValueError("Movie ID map length does not match manifest n_items")
    return manifest


def extract_bundle(path: Path, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        root = target.resolve()
        for item in archive.infolist():
            resolved = (target / item.filename).resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError(f"Unsafe archive path: {item.filename}")
        archive.extractall(target)
    candidates = list(target.rglob("manifest.json"))
    if len(candidates) != 1:
        raise ValueError("Expected exactly one manifest.json in bundle")
    return candidates[0].parent


def import_catalogue(db, bundle_dir: Path, batch_size: int = 2000) -> dict:
    inserted = updated = 0
    for chunk in pd.read_csv(bundle_dir / "catalogue.csv", chunksize=batch_size):
        source_ids = [int(x) for x in chunk["movielens_id"].tolist()]
        existing_rows = db.query(Movie).filter(Movie.movielens_id.in_(source_ids)).all()
        existing = {int(row.movielens_id): row for row in existing_rows}
        records = []
        for row in chunk.to_dict("records"):
            source_id = int(row["movielens_id"])
            title = str(row["title"])
            year = None if pd.isna(row.get("year")) else int(row["year"])
            genres = "" if pd.isna(row.get("genres")) else str(row.get("genres", ""))
            current = existing.get(source_id)
            if current:
                # The title primary key is deliberately not updated.
                current.title = title
                current.sort_key = make_sort_key(title)
                current.genres = genres
                current.year = year
                current.media_type = "movie"
                if current.source == "unknown":
                    current.source = "movielens"
                updated += 1
            else:
                records.append({
                    "title_id": generate_title_id(),
                    "media_type": "movie",
                    "movielens_id": source_id,
                    "title": title,
                    "sort_key": make_sort_key(title),
                    "genres": genres,
                    "year": year,
                    "source": "movielens",
                })
                inserted += 1
        if records:
            serials = allocate_title_serial_numbers(db.connection(), len(records))
            for record, serial in zip(records, serials):
                record["serial_number"] = serial
            db.bulk_insert_mappings(Movie, records)
        db.commit()
    print(f"Catalogue imported: {inserted:,} inserted, {updated:,} updated")
    return {"inserted": inserted, "updated": updated}


def import_users(db, bundle_dir: Path, batch_size: int = 5000) -> dict[int, int]:
    maps = json.loads((bundle_dir / "id-maps-v1.json").read_text(encoding="utf-8"))
    source_ids = [int(x) for x in maps["idx_to_source_user_id"]]
    source_strings = [str(x) for x in source_ids]
    existing_rows = db.query(User).filter(User.external_id.in_(source_strings)).all()
    user_map = {int(row.external_id): row.id for row in existing_rows}
    known_names = {row[0] for row in db.query(User.username).all()}
    pending = []
    for source_id in source_ids:
        if source_id in user_map:
            continue
        username = f"ml_{source_id}"
        if username in known_names:
            username = f"mluser_{source_id}"
        known_names.add(username)
        pending.append({
            "external_id": str(source_id), "username": username,
            "email": None, "is_active": True,
        })
    for start in range(0, len(pending), batch_size):
        db.bulk_insert_mappings(User, pending[start:start + batch_size])
        db.commit()
    rows = db.query(User).filter(User.external_id.in_(source_strings)).all()
    user_map = {int(row.external_id): int(row.id) for row in rows}
    if len(user_map) != len(source_ids):
        raise RuntimeError("Some MovieLens users were not inserted/read back")
    print(f"Users available: {len(user_map):,}")
    return user_map


def insert_rating_batch(db, mappings: list[dict]) -> None:
    if not mappings:
        return
    dialect = db.bind.dialect.name
    if dialect == "sqlite":
        # SQLite caps bound variables per statement (32,766 on current builds).
        # Six columns per rating means a 10,000-row sample chunk exceeds that cap.
        sqlite_rows_per_statement = 5_000
        for start in range(0, len(mappings), sqlite_rows_per_statement):
            chunk = mappings[start:start + sqlite_rows_per_statement]
            statement = sqlite.insert(Rating).values(chunk).on_conflict_do_nothing(
                index_elements=["user_id", "title_id"])
            db.execute(statement)
    elif dialect == "postgresql":
        statement = postgresql.insert(Rating).values(mappings).on_conflict_do_nothing(
            index_elements=["user_id", "title_id"])
        db.execute(statement)
    elif dialect == "mysql":
        statement = mysql.insert(Rating).values(mappings).on_duplicate_key_update(
            title_id=mysql.insert(Rating).inserted.title_id)
        db.execute(statement)
    else:
        # SQL-standard portable fallback: chunked existence query + savepoint retry.
        user_ids = sorted({row["user_id"] for row in mappings})
        existing = set()
        for start in range(0, len(user_ids), 250):
            users = user_ids[start:start + 250]
            rows = db.query(Rating.user_id, Rating.title_id).filter(Rating.user_id.in_(users)).all()
            existing.update((int(user), str(title)) for user, title in rows)
        fresh = [row for row in mappings if (row["user_id"], row["title_id"]) not in existing]
        if fresh:
            try:
                with db.begin_nested():
                    db.bulk_insert_mappings(Rating, fresh)
            except Exception:
                # A concurrent importer may have inserted the same key after the read.
                for record in fresh:
                    try:
                        with db.begin_nested():
                            db.add(Rating(**record))
                            db.flush()
                    except Exception:
                        continue


def import_ratings(db, bundle_dir: Path, user_map: dict[int, int], batch_size: int = 10_000) -> int:
    catalogue_ids = {
        int(row.movielens_id): str(row.title_id)
        for row in db.query(Movie.movielens_id, Movie.title_id).filter(Movie.movielens_id.is_not(None)).all()
    }
    processed = 0
    for chunk in pd.read_csv(bundle_dir / "ratings_sample.csv", chunksize=batch_size):
        mappings = []
        for row in chunk.itertuples(index=False):
            user_id = user_map.get(int(row.source_user_id))
            title_id = catalogue_ids.get(int(row.movielens_id))
            if user_id is None or title_id is None:
                continue
            mappings.append({
                "user_id": user_id, "title_id": title_id,
                "rating": float(row.rating), "relevance": float(row.relevance),
                "timestamp": pd.to_datetime(int(row.timestamp), unit="s", utc=True).to_pydatetime(),
                "is_implicit": False,
            })
        insert_rating_batch(db, mappings)
        db.commit()
        processed += len(mappings)
    print(f"Training ratings processed (duplicate-safe): {processed:,}")
    return processed


def install_active_bundle(bundle_dir: Path, manifest: dict) -> Path:
    base = settings.MODEL_DIR
    bundles_dir = base / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    bundle_id = manifest["bundle_id"]
    destination = bundles_dir / bundle_id
    if destination.exists():
        existing_manifest = destination / "manifest.json"
        if not existing_manifest.is_file() or json.loads(existing_manifest.read_text()).get("bundle_id") != bundle_id:
            raise RuntimeError("A different model bundle already occupies this bundle_id directory")
    else:
        staging = bundles_dir / f".{bundle_id}.staging"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(bundle_dir, staging)
        staging.replace(destination)
    pointer_tmp = base / "ACTIVE_BUNDLE.tmp"
    pointer_tmp.write_text(bundle_id, encoding="utf-8")
    pointer_tmp.replace(base / "ACTIVE_BUNDLE")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--skip-ratings", action="store_true")
    parser.add_argument("--skip-catalogue-sort", action="store_true")
    args = parser.parse_args()
    if not args.bundle.is_file():
        raise FileNotFoundError(args.bundle)

    if settings.AUTO_CREATE_SCHEMA:
        Base.metadata.create_all(bind=engine)
    else:
        # Production schema must be managed with `alembic upgrade head`.
        from sqlalchemy import inspect
        if not inspect(engine).has_table("movies"):
            raise RuntimeError("Database schema is missing; run `alembic upgrade head` first")
    with tempfile.TemporaryDirectory(prefix="cinerank-import-") as temp:
        bundle_dir = extract_bundle(args.bundle, Path(temp))
        manifest = verify_bundle(bundle_dir)
        print("Verified bundle:", manifest["bundle_id"],
              f"{manifest.get('n_users')} users / {manifest.get('n_items')} items")
        db = SessionLocal()
        try:
            import_catalogue(db, bundle_dir)
            user_map = import_users(db, bundle_dir)
            if not args.skip_ratings:
                import_ratings(db, bundle_dir, user_map)
            if not args.skip_catalogue_sort:
                print("Published catalogue ordering:", rebuild_catalogue_sort_index(db))
            # An imported trained bundle starts the 60-day challenger clock.
            run = db.query(JobRun).filter_by(job_name="model_refresh_60d").first()
            if run is None:
                run = JobRun(job_name="model_refresh_60d")
                db.add(run)
            now = datetime.now(timezone.utc)
            run.last_success_date = now.date()
            run.last_success_at = now
            run.last_status = "success"
            run.last_error = None
            db.commit()
        finally:
            db.close()
        installed = install_active_bundle(bundle_dir, manifest)
    print("Installed active model bundle:", installed)
    print("The API workers detect ACTIVE_BUNDLE changes and reload on the next recommendation request.")


if __name__ == "__main__":
    main()
