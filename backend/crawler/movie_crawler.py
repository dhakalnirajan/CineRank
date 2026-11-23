"""TMDB movie/TV discovery, rate limiting, metadata enrichment, and idempotent upserts."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

if __package__ in (None, ""):
    # Allow `python crawler/movie_crawler.py` and running from inside crawler/.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ids import generate_title_id
from app.db.session import SessionLocal
from app.models.entities import Movie
from app.services.catalogue_service import make_sort_key, append_to_active_sort_index

logger = logging.getLogger("cinerank.crawler")


class MovieCrawler:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

    def __init__(self, api_key: Optional[str] = None, read_access_token: Optional[str] = None,
                 requests_per_second: Optional[float] = None):
        self.api_key = api_key or settings.TMDB_API_KEY
        self.read_access_token = read_access_token or settings.TMDB_READ_ACCESS_TOKEN
        self.rps = requests_per_second or settings.CRAWLER_REQUESTS_PER_SECOND
        self._last_request = 0.0
        self._throttle_lock = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.CRAWLER_USER_AGENT,
                                     "Accept": "application/json"})
        self.session.max_redirects = max(0, settings.CRAWLER_MAX_REDIRECTS)
        if self.read_access_token:
            self.session.headers["Authorization"] = f"Bearer {self.read_access_token}"
        elif not self.api_key:
            logger.warning("TMDB credentials not configured; crawler is disabled")

    @property
    def enabled(self) -> bool:
        return bool(self.read_access_token or self.api_key)

    def _throttle(self) -> None:
        interval = 1.0 / max(0.1, self.rps)
        with self._throttle_lock:
            delay = interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            self._last_request = time.monotonic()

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        if not self.enabled:
            return None
        query = dict(params or {})
        if not self.read_access_token:
            query["api_key"] = self.api_key
        for attempt in range(settings.CRAWLER_MAX_RETRIES):
            self._throttle()
            try:
                response = self.session.get(
                    f"{self.BASE_URL}{endpoint}", params=query,
                    timeout=(settings.CRAWLER_CONNECT_TIMEOUT, settings.CRAWLER_READ_TIMEOUT),
                    allow_redirects=False,
                )
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        wait = max(1.0, float(retry_after))
                    except ValueError:
                        wait = min(60.0, 2.0 ** attempt)
                    time.sleep(min(120.0, wait) * random.uniform(0.9, 1.1))
                    continue
                if response.status_code in (500, 502, 503, 504):
                    time.sleep(min(30.0, 2.0 ** attempt) * random.uniform(0.8, 1.2))
                    continue
                response.raise_for_status()
                if len(response.content) > settings.CRAWLER_MAX_BODY_BYTES:
                    logger.warning("TMDB response exceeded configured body limit: %s", endpoint)
                    return None
                return response.json()
            except requests.RequestException as exc:
                logger.warning("TMDB request failed (%s/%s): %s", attempt + 1,
                               settings.CRAWLER_MAX_RETRIES, exc)
                if attempt + 1 < settings.CRAWLER_MAX_RETRIES:
                    time.sleep(min(30.0, 2.0 ** attempt) * random.uniform(0.8, 1.2))
        return None

    def _discover_pages(self, media_type: str, pages: int) -> list[dict]:
        today = datetime.now(timezone.utc).date().isoformat()
        if media_type == "movie":
            endpoints = [
                ("/movie/now_playing", {"region": "US"}),
                ("/movie/upcoming", {"region": "US"}),
                ("/discover/movie", {"sort_by": "primary_release_date.desc",
                                     "primary_release_date.lte": today,
                                     "vote_count.gte": settings.CRAWLER_MIN_VOTE_COUNT}),
            ]
        else:
            endpoints = [
                ("/tv/on_the_air", {}),
                ("/tv/airing_today", {}),
                ("/discover/tv", {"sort_by": "first_air_date.desc",
                                   "first_air_date.lte": today,
                                   "vote_count.gte": settings.CRAWLER_MIN_VOTE_COUNT}),
            ]
        found: dict[int, dict] = {}
        for endpoint, common_params in endpoints:
            for page in range(1, max(1, pages) + 1):
                payload = self._get(endpoint, {**common_params, "page": page,
                                                "include_adult": "false"})
                if not payload:
                    break
                for item in payload.get("results", []):
                    item_id = item.get("id")
                    if item_id:
                        found[int(item_id)] = item
                if page >= int(payload.get("total_pages", 1)):
                    break
        return list(found.values())

    def _details(self, media_type: str, tmdb_id: int) -> Optional[dict]:
        plural = "movie" if media_type == "movie" else "tv"
        return self._get(f"/{plural}/{tmdb_id}",
                         {"append_to_response": "credits,external_ids,keywords"})

    def _normalise(self, media_type: str, detail: dict) -> dict:
        title = detail.get("title") if media_type == "movie" else detail.get("name")
        original = detail.get("original_title") if media_type == "movie" else detail.get("original_name")
        date_value = detail.get("release_date") if media_type == "movie" else detail.get("first_air_date")
        year = None
        if date_value and len(date_value) >= 4:
            try:
                year = int(date_value[:4])
            except ValueError:
                pass
        credits = detail.get("credits") or {}
        cast = [c.get("name") for c in credits.get("cast", [])[:12] if c.get("name")]
        directors = [
            c.get("name") for c in credits.get("crew", [])
            if c.get("name") and (c.get("job") == "Director" or c.get("job") == "Executive Producer")
        ][:8]
        return {
            "media_type": media_type,
            "tmdb_id": int(detail["id"]),
            "imdb_id": (detail.get("external_ids") or {}).get("imdb_id"),
            "title": title or original or f"TMDB {detail['id']}",
            "original_title": original,
            "year": year,
            "overview": detail.get("overview") or "",
            "genres": "|".join(g.get("name", "") for g in detail.get("genres", []) if g.get("name")),
            "poster_path": f"{self.IMAGE_BASE}{detail['poster_path']}" if detail.get("poster_path") else None,
            "backdrop_path": f"https://image.tmdb.org/t/p/w1280{detail['backdrop_path']}" if detail.get("backdrop_path") else None,
            "popularity": float(detail.get("popularity") or 0.0),
            "vote_average": float(detail["vote_average"]) if detail.get("vote_average") is not None else None,
            "vote_count": int(detail.get("vote_count") or 0),
            "runtime": ((detail.get("runtime") or (detail.get("episode_run_time") or [None])[0])
                        if media_type == "tv" else detail.get("runtime")),
            "directors_json": json.dumps(directors, ensure_ascii=False),
            "cast_json": json.dumps(cast, ensure_ascii=False),
            "is_adult": bool(detail.get("adult", False)),
            "source": "tmdb",
        }

    def sync_latest(self, db: Session, pages_per_media_type: Optional[int] = None) -> dict:
        counts = {"movies_inserted": 0, "shows_inserted": 0, "updated": 0}
        if self.enabled:
            pages = pages_per_media_type or settings.CRAWLER_PAGES_PER_MEDIA_TYPE
            for media_type in ("movie", "tv"):
                discovery = self._discover_pages(media_type, pages)
                for stub in discovery:
                    tmdb_id = int(stub["id"])
                    detail = self._details(media_type, tmdb_id)
                    if not detail:
                        continue
                    record = self._normalise(media_type, detail)
                    movie = db.query(Movie).filter_by(media_type=media_type, tmdb_id=tmdb_id).first()
                    if movie is None and record.get("imdb_id"):
                        movie = db.query(Movie).filter_by(media_type=media_type, imdb_id=record["imdb_id"]).first()
                    is_new = movie is None
                    if movie is None:
                        movie = Movie(title_id=generate_title_id(), media_type=media_type,
                                      tmdb_id=tmdb_id, title=record["title"],
                                      sort_key=make_sort_key(record["title"]))
                        db.add(movie)
                    for key, value in record.items():
                        if key not in ("media_type", "tmdb_id", "title"):
                            setattr(movie, key, value)
                    movie.media_type = media_type
                    movie.tmdb_id = tmdb_id
                    movie.title = record["title"]
                    movie.sort_key = make_sort_key(movie.title)
                    db.flush()
                    if is_new:
                        append_to_active_sort_index(db, movie.title_id)
                        counts["movies_inserted" if media_type == "movie" else "shows_inserted"] += 1
                    else:
                        counts["updated"] += 1
                db.commit()
                logger.info("TMDB %s sync complete: %d discovered", media_type, len(discovery))
        from crawler.web_discovery import WebDiscoveryCrawler
        web_result = WebDiscoveryCrawler().crawl(db) if settings.WEB_CRAWLER_ENABLED else {"enabled": False}
        counts["web_discovery"] = web_result
        counts["enabled"] = bool(self.enabled or web_result.get("enabled"))
        return counts

    def fetch_movie_by_title(self, title: str, year: Optional[int] = None) -> Optional[dict]:
        params: dict[str, Any] = {"query": title, "include_adult": "false"}
        if year:
            params["year"] = year
        payload = self._get("/search/movie", params)
        hits = (payload or {}).get("results") or []
        if not hits:
            return None
        detail = self._details("movie", int(hits[0]["id"]))
        return self._normalise("movie", detail) if detail else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CineRank TMDB movie/TV crawler.")
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="Discovery pages per media type (defaults to CRAWLER_PAGES_PER_MEDIA_TYPE).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit only the crawl result as JSON.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    crawler = MovieCrawler()
    if not crawler.enabled and not settings.WEB_CRAWLER_ENABLED:
        logging.getLogger("cinerank.crawler").warning(
            "TMDB credentials are not configured and web discovery is disabled; "
            "set TMDB_API_KEY or TMDB_READ_ACCESS_TOKEN in backend/.env to crawl."
        )

    db = SessionLocal()
    try:
        result = crawler.sync_latest(db, pages_per_media_type=args.pages)
    finally:
        db.close()

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("CineRank crawler finished:")
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
