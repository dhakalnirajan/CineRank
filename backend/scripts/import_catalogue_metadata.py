#!/usr/bin/env python3
"""Enrich existing CineRank catalogue rows from a public TMDB/IMDb dump.

Matching is exact by MovieLens `links.csv` TMDB ID. Catalogue rows without a
TMDB link fall back only to a unique normalized title plus exact release year.
The command is dry-run by default and never creates new catalogue identities.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.entities import Movie
from app.services.title_display import normalize_display_title

LINKS_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
DATASET_URL = (
    "https://huggingface.co/datasets/HenryWaltson/TMDB-IMDB-Movies-Dataset/"
    "resolve/main/TMDB%20%20IMDB%20Movies%20Dataset.csv?download=true"
)
IMAGE_BASE = "https://image.tmdb.org/t/p"
YEAR_SUFFIX = re.compile(r"\s*\((\d{4})\)\s*$")
USEFUL_FIELDS = (
    "overview", "directors", "writers", "cast", "poster_path", "backdrop_path",
    "runtime", "genres", "tconst", "vote_average", "vote_count", "popularity",
)


@dataclass
class ImportStats:
    catalogue_rows: int = 0
    linked_rows: int = 0
    unlinked_rows: int = 0
    dataset_rows: int = 0
    exact_matches: int = 0
    fallback_matches: int = 0
    ambiguous_fallback: int = 0
    duplicate_tmdb: int = 0
    updated: int = 0
    skipped_no_data: int = 0
    fields: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "catalogue_rows": self.catalogue_rows,
            "linked_rows": self.linked_rows,
            "unlinked_rows": self.unlinked_rows,
            "dataset_rows": self.dataset_rows,
            "exact_matches": self.exact_matches,
            "fallback_matches": self.fallback_matches,
            "ambiguous_fallback": self.ambiguous_fallback,
            "duplicate_tmdb": self.duplicate_tmdb,
            "updated": self.updated,
            "skipped_no_data": self.skipped_no_data,
            "fields": dict(sorted(self.fields.items())),
        }


def normalize_title(value: str) -> str:
    value = normalize_display_title(value or "")
    value = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    value = re.sub(r"^(the|a|an)\s+", "", value)
    return " ".join(value.split())


def release_year(value: str | None) -> int | None:
    match = re.match(r"^(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


def parse_tmdb_id(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def split_people(value: str | None, limit: int | None = None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for name in (value or "").split(","):
        cleaned = " ".join(name.strip().split())
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        names.append(cleaned)
        if limit is not None and len(names) >= limit:
            break
    return names


def image_url(value: str | None) -> str | None:
    path = (value or "").strip()
    if not path:
        return None
    if path.startswith(("https://", "http://")):
        return path
    return f"{IMAGE_BASE}/w500{path if path.startswith('/') else '/' + path}"


def backdrop_url(value: str | None) -> str | None:
    path = (value or "").strip()
    if not path:
        return None
    if path.startswith(("https://", "http://")):
        return path
    return f"{IMAGE_BASE}/w1280{path if path.startswith('/') else '/' + path}"


def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None and number >= 0 else None


def row_score(row: dict[str, str]) -> int:
    return sum(1 for key in USEFUL_FIELDS if (row.get(key) or "").strip())


def metadata_patch(movie: Movie, row: dict[str, str], overwrite: bool) -> dict[str, Any]:
    patch: dict[str, Any] = {}

    def fill(column: str, value: Any) -> None:
        if value in (None, "", [], {}):
            return
        if overwrite or getattr(movie, column) in (None, ""):
            patch[column] = value

    tmdb_id = parse_tmdb_id(row.get("id"))
    if tmdb_id and (overwrite or movie.tmdb_id is None):
        patch["tmdb_id"] = tmdb_id

    fill("overview", " ".join((row.get("overview") or "").split()) or None)
    fill("poster_path", image_url(row.get("poster_path")))
    fill("backdrop_path", backdrop_url(row.get("backdrop_path")))
    fill("runtime", _int(row.get("runtime")))
    fill("vote_average", _float(row.get("vote_average")))
    fill("vote_count", _int(row.get("vote_count")))
    fill("popularity", _float(row.get("popularity")))

    genres = [name.strip() for name in (row.get("genres") or "").split(",") if name.strip()]
    fill("genres", "|".join(dict.fromkeys(genres)) or None)

    director_names = split_people(row.get("directors"))
    if director_names:
        fill(
            "directors_json",
            json.dumps(
                [{"name": name, "job": "Director"} for name in director_names],
                ensure_ascii=False,
            ),
        )
    cast_names = split_people(row.get("cast"), limit=12)
    if cast_names:
        fill(
            "cast_json",
            json.dumps(
                [{"name": name, "character": None} for name in cast_names],
                ensure_ascii=False,
            ),
        )

    tconst = (row.get("tconst") or "").strip()
    if re.fullmatch(r"tt\d{7,10}", tconst):
        fill("imdb_id", tconst)
    return patch


def load_movielens_links(zip_path: Path) -> dict[int, int]:
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("ml-latest-small/links.csv") as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"))
            return {
                int(row["movieId"]): int(row["tmdbId"])
                for row in reader
                if row.get("movieId") and row.get("tmdbId")
            }


def scan_dataset(
    path: Path,
    target_ids: set[int],
    fallback_keys: set[tuple[str, int]],
) -> tuple[dict[int, dict[str, str]], dict[tuple[str, int], list[dict[str, str]]], int]:
    exact: dict[int, dict[str, str]] = {}
    fallback: dict[tuple[str, int], list[dict[str, str]]] = {}
    seen = 0
    csv.field_size_limit(20_000_000)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            seen += 1
            tmdb_id = parse_tmdb_id(row.get("id"))
            if tmdb_id in target_ids:
                current = exact.get(tmdb_id)
                if current is None or row_score(row) > row_score(current):
                    exact[tmdb_id] = row
            if fallback_keys:
                year = release_year(row.get("release_date"))
                for candidate_title in (row.get("title"), row.get("original_title")):
                    key = (normalize_title(candidate_title or ""), year) if year else None
                    if key and key in fallback_keys:
                        bucket = fallback.setdefault(key, [])
                        if all(parse_tmdb_id(item.get("id")) != tmdb_id for item in bucket):
                            bucket.append(row)
    return exact, fallback, seen


def _choose_fallback(
    key: tuple[str, int],
    used_tmdb_ids: set[int],
    candidates: list[dict[str, str]],
) -> int | None:
    if len(candidates) != 1:
        return None
    candidate_id = parse_tmdb_id(candidates[0].get("id"))
    if candidate_id is None or candidate_id in used_tmdb_ids:
        return None
    return candidate_id


def year_compatible(movie: Movie, row: dict[str, str], tolerance: int = 3) -> bool:
    """Reject linked IDs whose release years cannot describe the same film."""
    dataset_year = release_year(row.get("release_date"))
    if movie.year is None or dataset_year is None:
        return True
    return abs(int(movie.year) - dataset_year) <= tolerance


def run(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset)
    links_path = Path(args.links)
    if not dataset_path.is_file():
        raise SystemExit(f"Dataset not found: {dataset_path}. Download it with --download.")
    if not links_path.is_file():
        raise SystemExit(f"MovieLens links archive not found: {links_path}. Download it with --download.")

    links = load_movielens_links(links_path)
    db: Session = SessionLocal()
    stats = ImportStats()
    try:
        movies = db.query(Movie).order_by(Movie.serial_number.asc()).all()
        stats.catalogue_rows = len(movies)
        tmdb_owner: dict[int, Movie] = {}
        unlinked: list[Movie] = []
        for movie in movies:
            tmdb_id = links.get(int(movie.movielens_id)) if movie.movielens_id is not None else None
            if tmdb_id and tmdb_id not in tmdb_owner:
                tmdb_owner[tmdb_id] = movie
                stats.linked_rows += 1
            elif tmdb_id:
                stats.duplicate_tmdb += 1
            else:
                unlinked.append(movie)
        stats.unlinked_rows = len(unlinked)

        fallback_keys = {
            (normalize_title(movie.title), int(movie.year))
            for movie in movies
            if movie.year is not None and normalize_title(movie.title)
        }
        exact_rows, fallback_candidates, stats.dataset_rows = scan_dataset(
            dataset_path, set(tmdb_owner), fallback_keys
        )

        updates: list[tuple[Movie, dict[str, str], str]] = []
        unmatched = list(unlinked)
        for tmdb_id, movie in tmdb_owner.items():
            row = exact_rows.get(tmdb_id)
            if row is not None and year_compatible(movie, row):
                updates.append((movie, row, "tmdb_id"))
            else:
                # A stale or incorrect MovieLens link must not inject another film.
                unmatched.append(movie)
        stats.exact_matches = sum(1 for _movie, _row, method in updates if method == "tmdb_id")

        fallback_by_key: dict[tuple[str, int], list[Movie]] = {}
        for movie in unmatched:
            if movie.year is None:
                continue
            key = (normalize_title(movie.title), int(movie.year))
            if key[0]:
                fallback_by_key.setdefault(key, []).append(movie)
        used_tmdb = {tmdb_id for tmdb_id, movie in tmdb_owner.items() if any(m is movie for m, _r, _x in updates)}
        for key, bucket in fallback_by_key.items():
            if len(bucket) != 1:
                continue
            candidate_id = _choose_fallback(key, used_tmdb, fallback_candidates.get(key, []))
            if candidate_id is None:
                if fallback_candidates.get(key):
                    stats.ambiguous_fallback += 1
                continue
            row = next(
                (item for item in fallback_candidates[key] if parse_tmdb_id(item.get("id")) == candidate_id),
                None,
            )
            if row is not None:
                updates.append((bucket[0], row, "title_year"))
                used_tmdb.add(candidate_id)
        stats.fallback_matches = sum(1 for _movie, _row, method in updates if method == "title_year")

        for movie, row, method in updates:
            patch = metadata_patch(movie, row, args.overwrite_existing)
            if not patch:
                stats.skipped_no_data += 1
                continue
            stats.fields.update(patch.keys())
            if args.apply:
                for field_name, value in patch.items():
                    setattr(movie, field_name, value)
            stats.updated += 1
            if stats.updated <= 5 or stats.updated % 500 == 0:
                print(
                    f"{'APPLY' if args.apply else 'DRY-RUN'} {movie.serial_number} "
                    f"{movie.title!r} method={method} fields={','.join(sorted(patch))}"
                )

        if args.apply:
            db.commit()
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "applied": bool(args.apply),
            "dataset": str(dataset_path),
            "links": str(links_path),
            **stats.as_dict(),
        }
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        if not args.apply:
            print("No database changes made. Re-run with --apply to persist the metadata.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def download_sources(destination: Path) -> tuple[Path, Path]:
    import requests

    destination.mkdir(parents=True, exist_ok=True)
    dataset_path = destination / "TMDB-IMDB-Movies-Dataset.csv"
    links_path = destination / "ml-latest-small.zip"
    for url, path in ((DATASET_URL, dataset_path), (LINKS_URL, links_path)):
        if path.is_file() and path.stat().st_size > 0:
            print(f"Using existing {path} ({path.stat().st_size} bytes)")
            continue
        temporary = path.with_suffix(path.suffix + ".part")
        with requests.get(url, stream=True, timeout=(10, 180)) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temporary.replace(path)
        print(f"Downloaded {path} ({path.stat().st_size} bytes)")
    return dataset_path, links_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download the public dataset and MovieLens links first.")
    parser.add_argument("--apply", action="store_true", help="Persist metadata. Without this, dry-run only.")
    parser.add_argument("--overwrite-existing", action="store_true", help="Replace existing non-empty metadata.")
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "data" / "external" / "TMDB-IMDB-Movies-Dataset.csv"),
    )
    parser.add_argument(
        "--links",
        default=str(ROOT / "data" / "external" / "ml-latest-small.zip"),
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "data" / "external" / "metadata-import-report.json"),
    )
    args = parser.parse_args()
    if args.download:
        args.dataset, args.links = map(str, download_sources(ROOT / "data" / "external"))
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
