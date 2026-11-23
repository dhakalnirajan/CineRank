#!/usr/bin/env python3
"""Conservatively enrich existing CineRank catalogue rows from TMDB.

Dry-run is the default. The command only applies metadata when --apply is passed,
uses existing TMDB IDs where available, and otherwise requires a high title match
plus a compatible release year. Ambiguous or weak matches are skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import Movie

TMDB_API = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"
YEAR_SUFFIX = re.compile(r"\s*\((\d{4})\)\s*$")


def _normalise_title(value: str) -> str:
    value = YEAR_SUFFIX.sub("", value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    value = re.sub(r"^(the|a|an)\s+", "", value)
    return " ".join(value.split())


def _year(value: Any) -> int | None:
    match = re.match(r"^(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


class TMDBClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": settings.CRAWLER_USER_AGENT})
        if settings.TMDB_READ_ACCESS_TOKEN:
            self.session.headers["Authorization"] = f"Bearer {settings.TMDB_READ_ACCESS_TOKEN}"
        elif settings.TMDB_API_KEY:
            self.session.params = {"api_key": settings.TMDB_API_KEY}
        else:
            raise RuntimeError("Set TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY in backend/.env")

    def get(self, path: str, **params: Any) -> dict:
        url = f"{TMDB_API}/{path.lstrip('/')}"
        response = self.session.get(url, params=params, timeout=(5, 20))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("TMDB returned an unexpected response")
        return payload

    def resolve(self, movie: Movie) -> tuple[dict | None, float, str]:
        media = "tv" if movie.media_type == "tv" else "movie"
        if movie.tmdb_id:
            detail = self.get(f"{media}/{int(movie.tmdb_id)}", append_to_response="credits,external_ids")
            return detail, 1.0, "existing_tmdb_id"

        source_title = movie.title or ""
        match = YEAR_SUFFIX.search(source_title)
        year = int(movie.year) if movie.year else (int(match.group(1)) if match else None)
        query = YEAR_SUFFIX.sub("", source_title).strip()
        search_params = {"query": query, "include_adult": "false"}
        if year:
            search_params["year" if media == "movie" else "first_air_date_year"] = year
        result = self.get(f"search/{media}", **search_params)
        candidates: list[tuple[float, dict]] = []
        target = _normalise_title(query)
        for item in result.get("results", []):
            candidate_title = item.get("title") if media == "movie" else item.get("name")
            original = item.get("original_title") if media == "movie" else item.get("original_name")
            similarity = max(
                SequenceMatcher(None, target, _normalise_title(str(candidate_title or ""))).ratio(),
                SequenceMatcher(None, target, _normalise_title(str(original or ""))).ratio(),
            )
            candidate_year = _year(item.get("release_date") if media == "movie" else item.get("first_air_date"))
            if year and candidate_year and abs(year - candidate_year) > 1:
                continue
            if year and candidate_year is None:
                continue
            if similarity >= (0.90 if year else 0.96):
                candidates.append((similarity, item))
        candidates.sort(key=lambda pair: (-pair[0], int(pair[1].get("id", 0))))
        if not candidates:
            return None, 0.0, "no_confident_match"
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.05:
            return None, candidates[0][0], "ambiguous_match"
        score, selected = candidates[0]
        detail = self.get(f"{media}/{int(selected['id'])}", append_to_response="credits,external_ids")
        return detail, score, "matched_by_title_year"


def metadata_patch(movie: Movie, detail: dict, overwrite: bool) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    poster = detail.get("poster_path")
    backdrop = detail.get("backdrop_path")
    overview = (detail.get("overview") or "").strip()
    genres = [g.get("name") for g in detail.get("genres", []) if isinstance(g, dict) and g.get("name")]
    if poster and (overwrite or not movie.poster_path):
        patch["poster_path"] = f"{IMAGE_BASE}/w500{poster}"
    if backdrop and (overwrite or not movie.backdrop_path):
        patch["backdrop_path"] = f"{IMAGE_BASE}/w1280{backdrop}"
    if overview and (overwrite or not movie.overview):
        patch["overview"] = overview
    if genres and (overwrite or not movie.genres):
        patch["genres"] = "|".join(dict.fromkeys(genres))
    if detail.get("id") and not movie.tmdb_id:
        patch["tmdb_id"] = int(detail["id"])

    runtime = detail.get("runtime")
    if runtime is None:
        runtimes = detail.get("episode_run_time") or []
        runtime = runtimes[0] if runtimes else None
    if runtime and (overwrite or not movie.runtime):
        patch["runtime"] = int(runtime)

    credits = detail.get("credits") or {}
    crew = credits.get("crew") or []
    directors = [
        {"name": person.get("name"), "job": person.get("job")} for person in crew
        if person.get("job") == "Director" and person.get("name")
    ]
    cast = [
        {"name": person.get("name"), "character": person.get("character")} for person in (credits.get("cast") or [])[:12]
        if person.get("name")
    ]
    if directors and (overwrite or not movie.directors_json):
        patch["directors_json"] = json.dumps(directors, ensure_ascii=False)
    if cast and (overwrite or not movie.cast_json):
        patch["cast_json"] = json.dumps(cast, ensure_ascii=False)

    external = detail.get("external_ids") or {}
    imdb_id = detail.get("imdb_id") or external.get("imdb_id")
    if imdb_id and (overwrite or not movie.imdb_id):
        patch["imdb_id"] = str(imdb_id)

    vote_average = detail.get("vote_average")
    vote_count = detail.get("vote_count")
    popularity = detail.get("popularity")
    if vote_average is not None and (overwrite or movie.vote_average is None):
        patch["vote_average"] = float(vote_average)
    if vote_count is not None and (overwrite or movie.vote_count is None):
        patch["vote_count"] = int(vote_count)
    if popularity is not None and (overwrite or not movie.popularity):
        patch["popularity"] = float(popularity)
    return patch


def run(args: argparse.Namespace) -> int:
    client = TMDBClient()
    db: Session = SessionLocal()
    try:
        missing_metadata = (
            Movie.tmdb_id.is_(None)
            | Movie.poster_path.is_(None) | (Movie.poster_path == "")
            | Movie.backdrop_path.is_(None) | (Movie.backdrop_path == "")
            | Movie.overview.is_(None) | (Movie.overview == "")
            | Movie.genres.is_(None) | (Movie.genres == "")
            | Movie.runtime.is_(None)
            | Movie.directors_json.is_(None) | (Movie.directors_json == "")
            | Movie.cast_json.is_(None) | (Movie.cast_json == "")
            | Movie.imdb_id.is_(None) | (Movie.imdb_id == "")
        )
        query = db.query(Movie).filter(missing_metadata)
        if args.media_type != "all":
            query = query.filter(Movie.media_type == args.media_type)
        query = query.order_by(Movie.serial_number.asc())
        if args.limit:
            query = query.limit(args.limit)
        rows = query.all()
        print(f"Rows eligible for enrichment: {len(rows)}")
        updated = skipped = failed = 0
        for index, movie in enumerate(rows, 1):
            try:
                detail, confidence, match_method = client.resolve(movie)
                if detail is None:
                    skipped += 1
                    print(f"SKIP {movie.serial_number} {movie.title!r}: {match_method} ({confidence:.3f})")
                    continue
                patch = metadata_patch(movie, detail, args.overwrite_existing)
                if not patch:
                    skipped += 1
                    continue
                print(f"{'APPLY' if args.apply else 'DRY-RUN'} {movie.serial_number} {movie.title!r}: "
                      f"match={match_method} confidence={confidence:.3f} fields={','.join(sorted(patch))}")
                if args.apply:
                    for field, value in patch.items():
                        setattr(movie, field, value)
                    db.commit()
                updated += 1
                if index % 25 == 0:
                    print(f"Progress {index}/{len(rows)}")
                time.sleep(max(0.1, args.delay))
            except requests.RequestException as exc:
                db.rollback()
                failed += 1
                print(f"ERROR {movie.serial_number} {movie.title!r}: TMDB request failed: {exc}", file=sys.stderr)
                if getattr(exc.response, "status_code", None) == 401:
                    raise RuntimeError("TMDB rejected the configured credentials (HTTP 401)") from exc
                time.sleep(max(1.0, args.delay * 3))
            except Exception as exc:
                db.rollback()
                failed += 1
                print(f"ERROR {movie.serial_number} {movie.title!r}: {exc}", file=sys.stderr)
        print(f"Summary: {'updated' if args.apply else 'would_update'}={updated}, skipped={skipped}, failed={failed}")
        if not args.apply:
            print("No database changes made. Re-run with --apply to persist the previewed updates.")
        return 1 if failed else 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist changes. Without this, the command is dry-run only.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of catalogue rows to inspect (default: 100).")
    parser.add_argument("--media-type", choices=("all", "movie", "tv"), default="all")
    parser.add_argument("--overwrite-existing", action="store_true", help="Allow replacing non-empty metadata fields.")
    parser.add_argument("--delay", type=float, default=0.3, help="Minimum delay between successful requests.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.delay < 0:
        parser.error("--delay must be >= 0")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
