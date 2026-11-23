#!/usr/bin/env python3
"""Add curated films and TV series from public metadata dumps.

Sources:
- ``quantavil/imdb-dataset`` weekly IMDb export: 49K films and 12.8K TV
  series/miniseries with cast, ratings, votes, runtime, genres and posters.
- ``BrightData/IMDb-Media``: storylines, cast and directors for films.
- TVMaze show index: TV summaries, artwork, genres and network data.

The importer never creates a second copy of an existing title. It skips an
IMDb identifier that is already present and an exact normalized title plus year
that already exists for the same media type. A title without a real synopsis is
reported and skipped instead of being added with invented metadata. Dry-run is
the default.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests
from sqlalchemy.orm import Session

from app.core.ids import generate_title_id
from app.core.serial_numbers import allocate_title_serial_numbers
from app.db.session import SessionLocal
from app.models.entities import Movie
from app.services.catalogue_service import make_sort_key, rebuild_catalogue_sort_index
from app.services.title_display import normalize_display_title
from scripts.import_catalogue_metadata import normalize_title

IMDB_TITLES_URL = "https://quantavil.github.io/imdb-dataset/titles.json.gz"
TVMAZE_SHOWS_URL = "https://api.tvmaze.com/shows"
BRIGHTDATA_URL = (
    "https://huggingface.co/datasets/BrightData/IMDb-Media/"
    "resolve/main/IMDB%20media.csv?download=true"
)
IMAGE_BASE = "https://image.tmdb.org/t/p"
TYPE_MAP = {
    "movie": "movie",
    "tv_movie": "movie",
    "tv_series": "tv",
    "tv_miniseries": "tv",
}
USEFUL_FIELDS = ("storyline", "presentation", "top_cast", "credit")


@dataclass
class ImportStats:
    source_rows: int = 0
    source_movies: int = 0
    source_tv: int = 0
    already_in_catalogue: int = 0
    duplicate_title_year: int = 0
    skipped_no_overview: int = 0
    skipped_no_identity: int = 0
    brightdata_rows: int = 0
    tvmaze_rows: int = 0
    candidates: int = 0
    inserted_movies: int = 0
    inserted_tv: int = 0
    fields: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_rows": self.source_rows,
            "source_movies": self.source_movies,
            "source_tv": self.source_tv,
            "already_in_catalogue": self.already_in_catalogue,
            "duplicate_title_year": self.duplicate_title_year,
            "skipped_no_overview": self.skipped_no_overview,
            "skipped_no_identity": self.skipped_no_identity,
            "brightdata_rows": self.brightdata_rows,
            "tvmaze_rows": self.tvmaze_rows,
            "candidates": self.candidates,
            "inserted_movies": self.inserted_movies,
            "inserted_tv": self.inserted_tv,
            "fields": dict(sorted(self.fields.items())),
        }


def clean_text(value: Any, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    if limit is not None and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return text


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", html.unescape(text))
    return clean_text(text)


def clean_storyline(presentation: str | None, storyline: str | None) -> str:
    """Use the concise sourced synopsis and collapse exact duplicated text."""
    short = clean_text(presentation, 2000)
    if len(short) >= 40:
        return short
    text = clean_text(storyline, 2000)
    half = len(text) // 2
    if half >= 80 and text[:half].strip() == text[half:].strip():
        text = text[:half].strip()
    return text


def parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def split_people(value: str | None, limit: int = 12) -> list[dict[str, str | None]]:
    names: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for name in re.split(r",(?![^()]*\))", value or ""):
        cleaned = clean_text(name)
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        names.append({"name": cleaned, "character": None})
        if len(names) >= limit:
            break
    return names


def brightdata_credits(row: dict[str, str]) -> tuple[list[dict[str, str]], list[dict[str, str | None]]]:
    directors: list[dict[str, str]] = []
    cast: list[dict[str, str | None]] = []
    for group in parse_json(row.get("credit"), []):
        if not isinstance(group, dict):
            continue
        title = clean_text(group.get("title")).casefold()
        people = group.get("names") if isinstance(group.get("names"), list) else []
        if title in {"director", "directors"}:
            for person in people:
                if isinstance(person, dict):
                    name = clean_text(person.get("name"))
                    if name and all(item["name"] != name for item in directors):
                        directors.append({"name": name, "job": "Director"})
    for person in parse_json(row.get("top_cast"), []):
        if not isinstance(person, dict):
            continue
        name = clean_text(person.get("actor"))
        if name and all(item["name"] != name for item in cast):
            cast.append({"name": name, "character": clean_text(person.get("character")) or None})
        if len(cast) >= 12:
            break
    return directors, cast


def brightdata_payload(row: dict[str, str]) -> dict[str, Any]:
    directors, cast = brightdata_credits(row)
    return {
        "overview": clean_storyline(row.get("presentation"), row.get("storyline")),
        "directors": directors,
        "cast": cast,
        "media_type": clean_text(row.get("media_type")),
        "release_date": clean_text(row.get("details_release_date")),
    }


def load_existing(db: Session) -> tuple[set[str], set[tuple[str, str, int | None]]]:
    imdb_ids: set[str] = set()
    title_keys: set[tuple[str, str, int | None]] = set()
    for movie in db.query(Movie.imdb_id, Movie.media_type, Movie.title, Movie.year).all():
        imdb_id = clean_text(movie.imdb_id)
        if imdb_id:
            imdb_ids.add(imdb_id)
        key = title_key(movie.media_type, movie.title, movie.year)
        if key[1]:
            title_keys.add(key)
    return imdb_ids, title_keys


def title_key(media_type: str, title: str, year: Any) -> tuple[str, str, int | None]:
    try:
        parsed_year = int(year) if year not in (None, "", "\\N") else None
    except (TypeError, ValueError):
        parsed_year = None
    return media_type, normalize_title(title), parsed_year


def source_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def load_imdb_rows(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    fields = payload.get("fields")
    rows = payload.get("data")
    if not isinstance(fields, list) or not isinstance(rows, list):
        raise ValueError("IMDb export has an unexpected shape")
    return payload.get("stats", {}), [dict(zip(fields, row)) for row in rows]


def scan_brightdata(path: Path, wanted_imdb: set[str]) -> dict[str, dict[str, Any]]:
    """Stream the large film dump and retain only wanted IMDb identifiers."""
    found: dict[str, dict[str, Any]] = {}
    csv.field_size_limit(20_000_000)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            match = re.search(r"/title/(tt\d{7,10})/", row.get("url") or "")
            if not match or match.group(1) not in wanted_imdb:
                continue
            payload = brightdata_payload(row)
            if payload["overview"]:
                found[match.group(1)] = payload
    return found


def _tvmaze_page_path(cache_dir: Path, page: int) -> Path:
    return cache_dir / f"shows-{page:04d}.json"


def _fetch_json(url: str, params: dict[str, Any] | None = None, attempts: int = 5) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=(10, 60),
                headers={"User-Agent": "CineRank/1.0 catalogue metadata importer"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(min(20, 2 ** attempt))
    raise RuntimeError(f"Could not fetch {url}: {last_error}") from last_error


def load_tvmaze_shows(
    cache_dir: Path,
    wanted_imdb: set[str],
    download: bool,
) -> dict[str, dict[str, Any]]:
    """Return the TVMaze index rows whose IMDb identifier is wanted."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    selected: dict[str, dict[str, Any]] = {}
    page = 0
    while True:
        path = _tvmaze_page_path(cache_dir, page)
        if path.is_file():
            shows = json.loads(path.read_text(encoding="utf-8"))
        elif download:
            shows = _fetch_json(TVMAZE_SHOWS_URL, {"page": page})
            if shows is None:
                break
            path.write_text(json.dumps(shows, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.5)
        else:
            if page == 0:
                raise SystemExit(
                    f"TVMaze cache not found at {cache_dir}. Run with --download first."
                )
            break
        if not isinstance(shows, list):
            raise ValueError(f"Unexpected TVMaze page {page}")
        for show in shows:
            if not isinstance(show, dict):
                continue
            imdb_id = clean_text((show.get("externals") or {}).get("imdb"))
            if imdb_id not in wanted_imdb:
                continue
            current = selected.get(imdb_id)
            if current is None or _tvmaze_quality(show) > _tvmaze_quality(current):
                selected[imdb_id] = show
        if not shows:
            break
        page += 1
    return selected


def _tvmaze_quality(show: dict[str, Any]) -> int:
    return sum(
        1
        for key in ("summary", "image", "genres", "rating", "premiered")
        if show.get(key)
    )


def build_record(
    row: dict[str, Any],
    media_type: str,
    brightdata: dict[str, Any] | None,
    tvmaze: dict[str, Any] | None,
) -> dict[str, Any] | None:
    imdb_id = clean_text(row.get("id"))
    if not re.fullmatch(r"tt\d{7,10}", imdb_id):
        return None
    title = clean_text(row.get("title"))
    year = row.get("year")
    if not title or not isinstance(year, int):
        return None

    genres = [
        clean_text(value)
        for value in (row.get("genres") or "").split(",")
        if clean_text(value)
    ]
    if row.get("is_animation") and "Animation" not in genres:
        genres.append("Animation")

    if media_type == "movie":
        overview = (brightdata or {}).get("overview", "")
        cast = (brightdata or {}).get("cast") or split_people(row.get("cast"))
        directors = (brightdata or {}).get("directors") or []
        poster = clean_text(row.get("poster")) or None
        runtime = row.get("runtime")
        source = "imdb+imdb-media"
    else:
        show = tvmaze or {}
        overview = strip_html(show.get("summary"))
        cast = split_people(row.get("cast"))
        directors = []
        image = show.get("image") if isinstance(show.get("image"), dict) else {}
        poster = clean_text(image.get("original") or image.get("medium")) or clean_text(row.get("poster")) or None
        runtime = show.get("averageRuntime") or show.get("runtime") or row.get("runtime")
        show_genres = [clean_text(value) for value in (show.get("genres") or []) if clean_text(value)]
        if show_genres:
            genres = show_genres
            if row.get("is_animation") and "Animation" not in genres:
                genres.append("Animation")
        source = "imdb+tvmaze"

    overview = clean_text(overview, 4000)
    if not overview:
        return None

    try:
        runtime_value = int(runtime) if runtime not in (None, "", "\\N") else None
    except (TypeError, ValueError):
        runtime_value = None
    try:
        votes = int(row.get("votes") or 0)
    except (TypeError, ValueError):
        votes = 0
    try:
        rating = float(row.get("rating")) if row.get("rating") is not None else None
    except (TypeError, ValueError):
        rating = None

    source_url = f"https://www.imdb.com/title/{imdb_id}/"
    metadata = {
        "imdb_id": imdb_id,
        "imdb_type": row.get("type"),
        "end_year": row.get("end_year"),
        "tvmaze_id": (tvmaze or {}).get("id"),
        "tvmaze_url": (tvmaze or {}).get("url"),
        "network": ((tvmaze or {}).get("network") or {}).get("name"),
        "language": (tvmaze or {}).get("language"),
        "status": (tvmaze or {}).get("status"),
    }
    return {
        "media_type": media_type,
        "imdb_id": imdb_id,
        "title": title,
        "original_title": clean_text(row.get("original_title")) or None,
        "sort_key": make_sort_key(title),
        "genres": "|".join(dict.fromkeys(genres))[:1024],
        "year": int(year),
        "overview": overview,
        "poster_path": poster,
        "backdrop_path": None,
        "popularity": votes / 1000.0,
        "vote_average": rating,
        "vote_count": votes or None,
        "runtime": runtime_value,
        "directors_json": json.dumps(directors, ensure_ascii=False) if directors else None,
        "cast_json": json.dumps(cast, ensure_ascii=False) if cast else None,
        "is_adult": bool(row.get("is_adult")),
        "source": source,
        "source_url": source_url,
        "source_url_hash": source_hash(source_url),
        "source_domain": "imdb.com",
        "source_metadata_json": json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    }


def download_sources(paths: dict[str, Path], tvmaze_cache: Path) -> None:
    for url, path in ((IMDB_TITLES_URL, paths["titles"]), (BRIGHTDATA_URL, paths["brightdata"])):
        if path.is_file() and path.stat().st_size > 0:
            print(f"Using existing {path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        print(f"Downloading {url}")
        with requests.get(url, stream=True, timeout=(10, 300)) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temporary.replace(path)
        print(f"Saved {path} ({path.stat().st_size} bytes)")
    # The caller loads the IMDb export before requesting TVMaze pages.
    tvmaze_cache.mkdir(parents=True, exist_ok=True)


def run(args: argparse.Namespace) -> int:
    paths = {
        "titles": Path(args.titles),
        "brightdata": Path(args.brightdata),
    }
    cache_dir = Path(args.tvmaze_cache)
    if not paths["titles"].is_file():
        raise SystemExit(f"IMDb export not found: {paths['titles']}. Run with --download.")
    if not paths["brightdata"].is_file():
        raise SystemExit(f"Film metadata dump not found: {paths['brightdata']}. Run with --download.")

    stats = ImportStats()
    stats_payload, rows = load_imdb_rows(paths["titles"])
    stats.source_rows = len(rows)
    candidates: list[dict[str, Any]] = []
    seen_imdb: set[str] = set()
    for row in rows:
        media_type = TYPE_MAP.get(str(row.get("type") or ""))
        if media_type:
            candidates.append({**row, "_media_type": media_type})
    stats.source_movies = sum(1 for row in candidates if row["_media_type"] == "movie")
    stats.source_tv = sum(1 for row in candidates if row["_media_type"] == "tv")

    db: Session = SessionLocal()
    try:
        existing_imdb, existing_keys = load_existing(db)
        wanted_imdb = {
            clean_text(row.get("id"))
            for row in candidates
            if re.fullmatch(r"tt\d{7,10}", clean_text(row.get("id")))
            and clean_text(row.get("id")) not in existing_imdb
        }
        print(f"Existing catalogue identifiers: {len(existing_imdb)}")
        print(f"Candidates to inspect: {len(wanted_imdb)}")

        brightdata = scan_brightdata(
            paths["brightdata"],
            {row["id"] for row in candidates if row["_media_type"] == "movie"},
        )
        stats.brightdata_rows = len(brightdata)
        tvmaze = load_tvmaze_shows(
            cache_dir,
            {row["id"] for row in candidates if row["_media_type"] == "tv"},
            args.download,
        )
        stats.tvmaze_rows = len(tvmaze)

        records: list[dict[str, Any]] = []
        added_keys: set[tuple[str, str, int | None]] = set(existing_keys)
        for row in candidates:
            imdb_id = clean_text(row.get("id"))
            if not re.fullmatch(r"tt\d{7,10}", imdb_id):
                stats.skipped_no_identity += 1
                continue
            if imdb_id in existing_imdb or imdb_id in seen_imdb:
                stats.already_in_catalogue += 1
                continue
            key = title_key(row["_media_type"], clean_text(row.get("title")), row.get("year"))
            if key[1] and key in added_keys:
                stats.duplicate_title_year += 1
                continue
            record = build_record(
                row,
                row["_media_type"],
                brightdata.get(imdb_id),
                tvmaze.get(imdb_id),
            )
            if record is None:
                stats.skipped_no_overview += 1
                continue
            seen_imdb.add(imdb_id)
            added_keys.add(key)
            records.append(record)

        stats.candidates = len(records)
        stats.inserted_movies = sum(1 for record in records if record["media_type"] == "movie")
        stats.inserted_tv = sum(1 for record in records if record["media_type"] == "tv")
        for record in records:
            stats.fields.update(record.keys())
        print(
            f"Prepared {len(records)} new titles "
            f"({stats.inserted_movies} films, {stats.inserted_tv} series)"
        )

        if args.apply and records:
            serials = allocate_title_serial_numbers(db.connection(), len(records))
            for serial, record in zip(serials, records):
                record["title_id"] = generate_title_id()
                record["serial_number"] = serial
            for start in range(0, len(records), 1000):
                db.bulk_insert_mappings(Movie, records[start:start + 1000])
                db.commit()
                print(f"Inserted {min(start + 1000, len(records))}/{len(records)}")
            sort_result = rebuild_catalogue_sort_index(db)
            print(f"Catalogue sort index published: {sort_result}")

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "applied": bool(args.apply),
            "imdb_stats": stats_payload,
            "imdb_export": str(paths["titles"]),
            "film_dump": str(paths["brightdata"]),
            "tvmaze_cache": str(cache_dir),
            **stats.as_dict(),
        }
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        if not args.apply:
            print("No database changes made. Re-run with --apply to insert the titles.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download the IMDb and film dumps and missing TVMaze pages.")
    parser.add_argument("--apply", action="store_true", help="Insert titles. Without this, dry-run only.")
    parser.add_argument(
        "--titles",
        default=str(ROOT / "data" / "external" / "imdb-titles.json.gz"),
    )
    parser.add_argument(
        "--brightdata",
        default=str(ROOT / "data" / "external" / "imdb-media.csv"),
    )
    parser.add_argument(
        "--tvmaze-cache",
        default=str(ROOT / "data" / "external" / "tvmaze"),
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "data" / "external" / "extended-catalogue-report.json"),
    )
    args = parser.parse_args()
    if args.download:
        download_sources(
            {
                "titles": Path(args.titles),
                "brightdata": Path(args.brightdata),
            },
            Path(args.tvmaze_cache),
        )
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
