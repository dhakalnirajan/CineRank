#!/usr/bin/env python3
"""Import the privacy-sanitized MovieLens catalogue seed into a migrated DB.

Dry-run is the default. Apply only to an empty catalogue or a catalogue that
already contains every stable title_id from this exact seed. Existing metadata
is never overwritten by this bootstrap importer.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.entities import Movie, TitleSerialSequence
from app.services.catalogue_service import rebuild_catalogue_sort_index

DEFAULT_SEED = ROOT / "data" / "seeds" / "catalogue_movielens.jsonl"
DATETIME_FIELDS = {"created_at", "updated_at"}


def parse_seed(path: Path) -> list[dict]:
    records: list[dict] = []
    seen_ids: set[str] = set()
    seen_serials: set[int] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            title_id = str(row.get("title_id", ""))
            serial = int(row.get("serial_number", 0))
            if not title_id.startswith("title_") or len(title_id) > 42:
                raise ValueError(f"Invalid title_id at line {line_number}")
            if serial < 1 or title_id in seen_ids or serial in seen_serials:
                raise ValueError(f"Duplicate or invalid identity at line {line_number}")
            if row.get("media_type") not in {"movie", "tv"} or not row.get("title"):
                raise ValueError(f"Invalid title metadata at line {line_number}")
            for field in DATETIME_FIELDS:
                value = row.get(field)
                if isinstance(value, str):
                    row[field] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            seen_ids.add(title_id)
            seen_serials.add(serial)
            records.append(row)
    if not records:
        raise ValueError("Catalogue seed is empty")
    return records


def run(seed_path: Path, apply: bool) -> int:
    records = parse_seed(seed_path)
    ids = {row["title_id"] for row in records}
    db = SessionLocal()
    try:
        current_count = int(db.query(func.count(Movie.title_id)).scalar() or 0)
        existing_ids = {
            value for (value,) in db.query(Movie.title_id).filter(Movie.title_id.in_(ids)).all()
        }
        if existing_ids and existing_ids != ids:
            raise RuntimeError(
                "The target catalogue is partially populated with this seed. "
                "Refusing a partial overwrite; inspect the catalogue before proceeding."
            )
        if existing_ids == ids:
            print(f"Already imported: {len(ids)} titles. No changes required.")
            return len(ids)
        if current_count:
            raise RuntimeError(
                f"Target catalogue contains {current_count} unrelated rows. "
                "Seed import is restricted to an empty catalogue."
            )
        max_serial = max(int(row["serial_number"]) for row in records)
        print(f"Validated {len(records)} titles; next serial will be {max_serial + 1}.")
        if not apply:
            print("Dry-run only. Re-run with --apply to import these rows.")
            return len(records)

        batch_size = 500
        for offset in range(0, len(records), batch_size):
            db.bulk_insert_mappings(Movie, records[offset:offset + batch_size])
        sequence = db.query(TitleSerialSequence).filter_by(id=1).first()
        if sequence is None:
            sequence = TitleSerialSequence(id=1, next_value=max_serial + 1)
            db.add(sequence)
        else:
            sequence.next_value = max_serial + 1
        db.commit()
        result = rebuild_catalogue_sort_index(db)
        print(f"Imported {len(records)} titles; catalogue sort index: {result}.")
        return len(records)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--apply", action="store_true", help="Write to the configured DATABASE_URL")
    args = parser.parse_args()
    count = run(args.seed, args.apply)
    print(f"Processed {count} catalogue records.")


if __name__ == "__main__":
    main()
