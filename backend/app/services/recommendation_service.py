"""Stateless recommendation orchestration for horizontally scaled API workers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.cache import get_json as cache_get_json, set_json as cache_set_json
from app.core.metrics import (
    RECOMMENDATION_CACHE_EVENTS,
    RECOMMENDATION_DURATION,
    RECOMMENDATION_INFERENCE_DURATION,
    RECOMMENDATION_ITEM_COUNT,
)
from app.models.entities import CatalogueState, Interaction, Movie, Rating, RecommendationLog, User, UserPreference, Watchlist
from app.ml.release_registry import ProductionModelRegistry
from ranker.production_ranker import Candidate, ProductionRanker, RankedItem
from app.schemas.schemas import RecommendationItem, RecommendationResponse

logger = logging.getLogger("cinerank.service")


class InvalidPageToken(ValueError):
    pass


class RecommendationService:
    def __init__(self):
        self.registry: Optional[ProductionModelRegistry] = None
        self.ranker = ProductionRanker()
        self.is_ready = False
        self._registry_lock = threading.RLock()
        self._active_bundle_id: Optional[str] = None
        self._rows_cache: Dict[Tuple[int, int, Tuple[str, ...], str, int], Tuple[float, Dict[str, Any]]] = {}
        self._cache_lock = threading.RLock()
        self._cache_ttl_seconds = 90.0

    @property
    def models(self) -> Dict[str, bool]:
        ready = self.registry.ready_models if self.registry else set()
        return {name: True for name in sorted(ready)}

    def load_artifacts(self, model_dir: Optional[Path] = None) -> None:
        """Load the v2 immutable release once per process; never fall back to v1 silently."""
        with self._registry_lock:
            try:
                registry = ProductionModelRegistry(model_dir or settings.MODEL_RELEASE_DIR)
            except (FileNotFoundError, ImportError, RuntimeError, ValueError) as exc:
                self.registry = None
                self.is_ready = False
                self._active_bundle_id = None
                logger.error("Model release unavailable at %s: %s", model_dir or settings.MODEL_RELEASE_DIR, exc)
                return
            old = self.registry
            self.registry = registry
            self.ranker = ProductionRanker()
            self.is_ready = bool(registry.ready_models)
            self._active_bundle_id = registry.release_id
            manifest_path = registry.release_dir / "manifest.json"
            try:
                self._release_signature = f"{manifest_path.stat().st_mtime_ns}:{manifest_path.stat().st_size}"
            except OSError:
                self._release_signature = None
            if old is not None:
                try:
                    old.close()
                except Exception:
                    logger.exception("Error closing previous model release")
            logger.info(
                "Model release loaded: release_id=%s models=%s items=%s attention_provider=%s",
                registry.release_id, ",".join(sorted(registry.ready_models)),
                registry.engine.n_items, registry.engine.attention_provider,
            )

    def ensure_latest_bundle(self) -> None:
        """Reload when the configured immutable release manifest has changed on disk."""
        manifest_path = settings.MODEL_RELEASE_DIR / "manifest.json"
        try:
            signature = f"{manifest_path.stat().st_mtime_ns}:{manifest_path.stat().st_size}"
        except OSError:
            return
        if signature != getattr(self, "_release_signature", None):
            with self._registry_lock:
                if signature != getattr(self, "_release_signature", None):
                    self.load_artifacts()
                    self._release_signature = signature

    def _token_sign(self, raw: bytes) -> str:
        return hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()

    def _encode_cursor(self, user_id: int, excluded_title_ids: List[str]) -> str:
        payload = {
            "uid": int(user_id),
            "exclude": sorted(set(map(str, excluded_title_ids))),
            "exp": int(time.time()) + settings.RECOMMENDATION_TOKEN_TTL_SECONDS,
            "bundle": self._active_bundle_id or "unknown",
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        signature = self._token_sign(body.encode())
        return f"{body}.{signature}"

    def _decode_cursor(self, cursor: str, user_id: int) -> List[str]:
        try:
            body, signature = cursor.rsplit(".", 1)
            if not hmac.compare_digest(signature, self._token_sign(body.encode())):
                raise InvalidPageToken("Invalid recommendation cursor signature")
            padded = body + "=" * (-len(body) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
            if int(payload["uid"]) != int(user_id) or int(payload["exp"]) < int(time.time()):
                raise InvalidPageToken("Recommendation cursor expired or belongs to another user")
            expected_bundle = self._active_bundle_id or "unknown"
            if payload.get("bundle") != expected_bundle:
                raise InvalidPageToken("Recommendation model bundle changed; restart pagination")
            return [str(value) for value in payload["exclude"]]
        except InvalidPageToken:
            raise
        except Exception as exc:
            raise InvalidPageToken("Malformed recommendation cursor") from exc

    @staticmethod
    def _content_text(movie: Movie) -> str:
        return f"{movie.title or ''} {(movie.genres or '').replace('|', ' ')}"

    def _user_history(
        self, db: Session, user_id: int
    ) -> Tuple[List[Tuple[int, float]], set[str], set[int]]:
        """Build an ordered provider-ID history from ratings, watchlist and recent events."""
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise LookupError("User not found")

        seen_title_ids: set[str] = set()
        history_by_provider: Dict[int, Tuple[datetime, float]] = {}
        rating_rows = (
            db.query(Rating, Movie)
            .join(Movie, Rating.title_id == Movie.title_id)
            .filter(Rating.user_id == user_id)
            .order_by(Rating.timestamp.asc(), Rating.id.asc())
            .all()
        )
        for rating, movie in rating_rows:
            seen_title_ids.add(movie.title_id)
            if movie.movielens_id is not None:
                stamp = rating.timestamp or datetime.min.replace(tzinfo=timezone.utc)
                history_by_provider[int(movie.movielens_id)] = (stamp, float(rating.rating))

        watch_rows = (
            db.query(Watchlist, Movie)
            .join(Movie, Watchlist.title_id == Movie.title_id)
            .filter(Watchlist.user_id == user_id)
            .order_by(Watchlist.created_at.asc())
            .all()
        )
        for entry, movie in watch_rows:
            seen_title_ids.add(movie.title_id)
            if movie.movielens_id is not None:
                stamp = entry.created_at or datetime.min.replace(tzinfo=timezone.utc)
                previous = history_by_provider.get(int(movie.movielens_id))
                if previous is None or stamp >= previous[0]:
                    history_by_provider[int(movie.movielens_id)] = (stamp, 4.0)

        interaction_signal = {
            "click": 3.5,
            "play": 4.0,
            "complete": 4.5,
            "like": 5.0,
            "dislike": 1.0,
            "skip": 2.0,
        }
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        interaction_rows = (
            db.query(Interaction, Movie)
            .join(Movie, Interaction.title_id == Movie.title_id)
            .filter(
                Interaction.user_id == user_id,
                Interaction.event_type != "impression",
                Interaction.occurred_at >= cutoff,
            )
            .order_by(Interaction.occurred_at.asc(), Interaction.id.asc())
            .all()
        )
        for event, movie in interaction_rows:
            seen_title_ids.add(movie.title_id)
            if movie.movielens_id is None:
                continue
            event_type = str(event.event_type).casefold()
            if event_type == "rating":
                signal = float(event.value)
            else:
                signal = interaction_signal.get(event_type)
            if signal is None or not 0.5 <= signal <= 5.0:
                continue
            stamp = event.occurred_at or datetime.min.replace(tzinfo=timezone.utc)
            provider_id = int(movie.movielens_id)
            previous = history_by_provider.get(provider_id)
            if previous is None or stamp >= previous[0]:
                history_by_provider[provider_id] = (stamp, signal)

        seen_title_ids.update(
            title_id for (title_id,) in db.query(Watchlist.title_id)
            .filter(Watchlist.user_id == user_id).all()
        )
        seen_provider_ids: set[int] = set()
        if seen_title_ids:
            provider_rows = db.query(Movie.movielens_id).filter(
                Movie.title_id.in_(seen_title_ids), Movie.movielens_id.is_not(None)
            ).all()
            seen_provider_ids = {int(value) for (value,) in provider_rows if value is not None}

        history = [
            (provider_id, rating)
            for provider_id, (_stamp, rating) in sorted(
                history_by_provider.items(), key=lambda item: (item[1][0], item[0])
            )
        ]
        return history, seen_title_ids, seen_provider_ids

    def _activity_count(self, db: Session, user_id: int) -> int:
        ratings = db.query(func.count(Rating.id)).filter(Rating.user_id == user_id).scalar() or 0
        watchlist = db.query(func.count(Watchlist.id)).filter(Watchlist.user_id == user_id).scalar() or 0
        interactions = db.query(func.count(Interaction.id)).filter(
            Interaction.user_id == user_id,
            Interaction.event_type != "impression",
        ).scalar() or 0
        return int(ratings) + int(watchlist) + int(interactions)

    def invalidate_user(self, user_id: int) -> None:
        """Drop cached rows after a user changes ratings, watchlist, or interactions."""
        with self._cache_lock:
            for key in [key for key in self._rows_cache if key[0] == int(user_id)]:
                self._rows_cache.pop(key, None)

    @staticmethod
    def _load_preferences(db: Session, user_id: int) -> dict[str, Any]:
        row = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        if row is None:
            return {"preferred": set(), "excluded": set(), "include_adult": False,
                    "min_year": None, "max_runtime": None}
        try:
            preferred = {str(value).casefold() for value in json.loads(row.preferred_genres_json or "[]")}
            excluded = {str(value).casefold() for value in json.loads(row.excluded_genres_json or "[]")}
        except (TypeError, ValueError):
            preferred, excluded = set(), set()
        return {"preferred": preferred, "excluded": excluded,
                "include_adult": bool(row.include_adult),
                "min_year": row.min_year, "max_runtime": row.max_runtime}

    @staticmethod
    def _apply_preferences(candidates: List[Candidate], movies: dict[str, Movie], preferences: dict) -> List[Candidate]:
        preferred = preferences.get("preferred", set())
        excluded = preferences.get("excluded", set())
        min_year = preferences.get("min_year")
        max_runtime = preferences.get("max_runtime")
        include_adult = bool(preferences.get("include_adult", False))
        output = []
        for candidate in candidates:
            movie = movies.get(candidate.title_id)
            if movie is None:
                continue
            genres = {part.strip().casefold() for part in (movie.genres or "").replace(",", "|").split("|") if part.strip()}
            if movie.is_adult and not include_adult:
                continue
            if excluded and genres.intersection(excluded):
                continue
            if min_year is not None and (movie.year is None or movie.year < min_year):
                continue
            if max_runtime is not None and (movie.runtime is None or movie.runtime > max_runtime):
                continue
            score = candidate.score
            if preferred and genres.intersection(preferred):
                score += max(abs(candidate.score) * 0.10, 0.01)
            output.append(Candidate(
                title_id=candidate.title_id, score=score, source=candidate.source,
                genres=candidate.genres, model_index=candidate.model_index,
                source_item_id=candidate.source_item_id,
            ))
        return output

    def _build_candidates(
        self, db: Session, history: List[Tuple[int, float]], seen_title_ids: set[str],
        seen_provider_ids: set[int], excluded_ids: Optional[set[str]] = None,
        pool_size: Optional[int] = None, preferences: Optional[dict] = None,
    ) -> Tuple[List[Candidate], List[Candidate]]:
        if not self.is_ready or self.registry is None:
            raise RuntimeError("No validated CineRank v2 model release is loaded")
        pool_size = pool_size or settings.CANDIDATE_POOL_SIZE
        excluded_ids = excluded_ids or set()

        excluded_provider_ids = set(seen_provider_ids)
        if excluded_ids:
            extra_provider_ids = db.query(Movie.movielens_id).filter(
                Movie.title_id.in_(excluded_ids), Movie.movielens_id.is_not(None)
            ).all()
            excluded_provider_ids.update(int(value) for (value,) in extra_provider_ids if value is not None)

        inference_started = time.perf_counter()
        try:
            prediction = self.registry.recommend_by_provider_ids(
                history,
                k=pool_size,
                exclude_provider_ids=excluded_provider_ids,
            )
        finally:
            RECOMMENDATION_INFERENCE_DURATION.labels("recommend").observe(
                time.perf_counter() - inference_started
            )
        provider_ids = [int(value) for value in prediction.get("provider_ids", [])]
        score_values = [float(value) for value in prediction.get("scores", [])]
        fallback = str(prediction.get("fallback") or "")
        model_source = "popularity" if fallback == "cold_start_popularity" else "hybrid_model"

        matching_rows = (
            db.query(Movie).filter(Movie.movielens_id.in_(set(provider_ids))).all()
            if provider_ids else []
        )
        by_provider = {
            int(movie.movielens_id): movie for movie in matching_rows
            if movie.movielens_id is not None
        }
        candidates: List[Candidate] = []
        for provider_id, score in zip(provider_ids, score_values):
            movie = by_provider.get(provider_id)
            if movie is None or movie.title_id in seen_title_ids or movie.title_id in excluded_ids:
                continue
            candidates.append(Candidate(
                title_id=movie.title_id,
                score=score,
                source=model_source,
                genres=movie.genres or "",
                source_item_id=provider_id,
            ))

        # Popularity is computed from the current CineRank catalogue, not copied
        # from the MovieLens release. This gives cold-start users a useful local feed.
        popular_rows = (
            db.query(Movie)
            .filter(~Movie.title_id.in_(seen_title_ids | excluded_ids) if (seen_title_ids or excluded_ids) else True)
            .order_by(
                Movie.popularity.desc().nullslast(),
                Movie.vote_count.desc().nullslast(),
                Movie.created_at.desc(),
                Movie.title_id.asc(),
            )
            .limit(max(pool_size, 100))
            .all()
        )
        popularity_candidates: List[Candidate] = []
        for movie in popular_rows:
            score = (
                0.60 * math.log1p(max(0.0, float(movie.popularity or 0.0)))
                + 0.25 * max(0.0, float(movie.vote_average or 0.0)) / 10.0
                + 0.15 * math.log1p(max(0, int(movie.vote_count or 0))) / 10.0
            )
            popularity_candidates.append(Candidate(
                title_id=movie.title_id,
                score=score,
                source="catalogue_popularity",
                genres=movie.genres or "",
            ))
        if preferences is not None:
            candidate_movies = {movie.title_id: movie for movie in matching_rows}
            candidate_movies.update({movie.title_id: movie for movie in popular_rows})
            candidates = self._apply_preferences(candidates, candidate_movies, preferences)
            popularity_candidates = self._apply_preferences(popularity_candidates, candidate_movies, preferences)
        return candidates, popularity_candidates

    def _rank_all(self, db: Session, user_id: int, cursor: Optional[str] = None,
                  limit: int = 200) -> Tuple[List[RankedItem], List[RankedItem], List[str]]:
        history, seen_title_ids, seen_provider_ids = self._user_history(db, user_id)
        excluded = set(self._decode_cursor(cursor, user_id)) if cursor else set()
        preferences = self._load_preferences(db, user_id)
        candidates, popularity_candidates = self._build_candidates(
            db, history, seen_title_ids, seen_provider_ids,
            excluded_ids=excluded,
            pool_size=max(settings.CANDIDATE_POOL_SIZE, limit + len(excluded)),
            preferences=preferences,
        )
        rank_started = time.perf_counter()
        ranked = self.ranker.rank(candidates, k=limit + len(excluded), seen=seen_title_ids | excluded)
        popular = self.ranker.rank(
            popularity_candidates, k=limit + len(excluded), seen=seen_title_ids | excluded
        )
        RECOMMENDATION_INFERENCE_DURATION.labels("rank").observe(
            time.perf_counter() - rank_started
        )
        ranked = [item for item in ranked if item.title_id not in excluded]
        popular = [item for item in popular if item.title_id not in excluded]
        return ranked, popular, list(excluded)

    def _to_items(self, db: Session, ranked: List[RankedItem]) -> List[RecommendationItem]:
        ids = list(dict.fromkeys(item.title_id for item in ranked))
        if not ids:
            return []
        rows = db.query(Movie).filter(Movie.title_id.in_(ids)).all()
        by_title_id = {row.title_id: row for row in rows}
        output = []
        for item in ranked:
            movie = by_title_id.get(item.title_id)
            if movie is None:
                continue
            output.append(RecommendationItem(
                title_id=movie.title_id,
                serial_number=movie.serial_number,
                movielens_id=movie.movielens_id,
                tmdb_id=movie.tmdb_id,
                imdb_id=movie.imdb_id,
                media_type=movie.media_type,
                title=movie.title,
                original_title=movie.original_title,
                genres=movie.genres or "",
                year=movie.year,
                overview=movie.overview,
                poster_path=movie.poster_path,
                backdrop_path=movie.backdrop_path,
                popularity=float(movie.popularity or 0.0),
                vote_average=movie.vote_average,
                vote_count=movie.vote_count,
                runtime=movie.runtime,
                directors_json=movie.directors_json,
                cast_json=movie.cast_json,
                is_adult=bool(movie.is_adult),
                source=movie.source or "unknown",
                score=item.final_score,
                reason="rank-fusion; sources=" + "+".join(item.sources),
            ))
        return output

    def recommend_rows(self, db: Session, user_id: int, k: int = 5,
                       genres: Optional[List[str]] = None) -> Dict[str, Any]:
        self.ensure_latest_bundle()
        started = time.perf_counter()
        k = min(max(1, k), settings.MAX_K)
        activity_count = self._activity_count(db, user_id)
        catalogue_version = int(
            db.query(CatalogueState.active_version)
            .filter(CatalogueState.id == 1).scalar() or 0
        )
        preference_row = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        preference_material = {
            "preferred": preference_row.preferred_genres_json if preference_row else "[]",
            "excluded": preference_row.excluded_genres_json if preference_row else "[]",
            "adult": bool(preference_row.include_adult) if preference_row else False,
            "year": preference_row.min_year if preference_row else None,
            "runtime": preference_row.max_runtime if preference_row else None,
        }
        preference_version = hashlib.sha256(
            json.dumps(preference_material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        cache_material = {
            "user": int(user_id), "k": k, "genres": list(genres or []),
            "bundle": str(self._active_bundle_id or "unknown"),
            "activity": activity_count, "catalogue": catalogue_version,
            "preferences": preference_version,
        }
        cache_digest = hashlib.sha256(
            json.dumps(cache_material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        shared_cache_key = f"cinerank:recommendations:v2:{user_id}:{cache_digest}"
        cache_key = (
            int(user_id), k, tuple(genres or []),
            f"{self._active_bundle_id or 'unknown'}:{catalogue_version}:{preference_version}", activity_count,
        )
        now = time.monotonic()
        shared_cached = cache_get_json(shared_cache_key)
        if isinstance(shared_cached, dict):
            RECOMMENDATION_DURATION.labels("shared_cache_hit").observe(
                time.perf_counter() - started
            )
            return {**shared_cached, "generated_at": datetime.now(timezone.utc).isoformat()}
        with self._cache_lock:
            cached = self._rows_cache.get(cache_key)
            if cached and cached[0] > now:
                RECOMMENDATION_CACHE_EVENTS.labels("memory", "hit").inc()
                RECOMMENDATION_DURATION.labels("memory_cache_hit").observe(
                    time.perf_counter() - started
                )
                return {**cached[1], "generated_at": datetime.now(timezone.utc).isoformat()}
            RECOMMENDATION_CACHE_EVENTS.labels("memory", "miss").inc()

        ranked, popular, _ = self._rank_all(db, user_id, limit=max(200, k))
        # Keep the trained order intact. Recent ratings and implicit events are
        # already part of the fold-in history; artificial rotation would weaken it.
        for_you = ranked[:k]
        popular_page = popular[:k]
        recent_rows = (
            db.query(Movie)
            .order_by(Movie.created_at.desc(), Movie.title_id.asc())
            .limit(k)
            .all()
        )
        recent_items = [
            RecommendationItem(
                title_id=movie.title_id,
                serial_number=movie.serial_number,
                movielens_id=movie.movielens_id,
                tmdb_id=movie.tmdb_id,
                imdb_id=movie.imdb_id,
                media_type=movie.media_type,
                title=movie.title,
                original_title=movie.original_title,
                genres=movie.genres or "",
                year=movie.year,
                overview=movie.overview,
                poster_path=movie.poster_path,
                backdrop_path=movie.backdrop_path,
                popularity=float(movie.popularity or 0.0),
                vote_average=movie.vote_average,
                vote_count=movie.vote_count,
                runtime=movie.runtime,
                directors_json=movie.directors_json,
                cast_json=movie.cast_json,
                is_adult=bool(movie.is_adult),
                source=movie.source or "unknown",
                score=0.0,
                reason="recently added to CineRank",
            )
            for movie in recent_rows
        ]
        genre_rows: Dict[str, List[RecommendationItem]] = {}
        if genres:
            for genre in genres:
                wanted = genre.casefold()
                filtered = [row for row in ranked if wanted in row.genres.casefold()]
                key = "genre_" + "_".join(genre.casefold().split())
                genre_rows[key] = self._to_items(db, filtered[:k])

        items = self._to_items(db, for_you)
        try:
            db.add(RecommendationLog(
                user_id=user_id,
                model_name="cinerank-v2-release",
                title_ids_json=json.dumps([item.title_id for item in items]),
                k=len(items),
            ))
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Unable to persist recommendation log")

        next_cursor = self._encode_cursor(user_id, [row.title_id for row in for_you]) if len(ranked) > k else None
        response = {
            "user_id": user_id,
            "model": "cinerank-v2-hybrid",
            "for_you": items,
            "popular": self._to_items(db, popular_page),
            "recently_added": recent_items,
            "genres": genre_rows,
            "next_cursor": next_cursor,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._cache_lock:
            self._rows_cache[cache_key] = (now + self._cache_ttl_seconds, response)
        cache_set_json(
            shared_cache_key,
            jsonable_encoder(response),
            min(self._cache_ttl_seconds, settings.REDIS_CACHE_TTL_SECONDS),
        )
        RECOMMENDATION_ITEM_COUNT.observe(len(items))
        RECOMMENDATION_DURATION.labels("computed").observe(
            time.perf_counter() - started
        )
        return response

    def load_more(self, db: Session, user_id: int, k: int = 5,
                  cursor: Optional[str] = None) -> Dict[str, Any]:
        self.ensure_latest_bundle()
        if not cursor:
            raise InvalidPageToken("A next_cursor from the previous page is required")
        k = min(max(1, k), settings.MAX_K)
        excluded = self._decode_cursor(cursor, user_id)
        ranked, _, _ = self._rank_all(db, user_id, cursor=cursor,
                                      limit=max(200, k + len(excluded)))
        page = ranked[:k]
        all_excluded = excluded + [item.title_id for item in page]
        return {
            "items": self._to_items(db, page),
            "next_cursor": self._encode_cursor(user_id, all_excluded) if len(ranked) > k else None,
        }

    def similar_titles(self, db: Session, movie: Movie, limit: int = 10) -> List[Movie]:
        """Resolve item-to-item neighbours for one catalogue title.

        The trained release provides provider-id neighbours. Catalogue rows are
        hydrated in model order, restricted to the same media type and never
        include the source title. Genre overlap and popularity fill the list when
        the release lacks neighbours or the title has no provider identity.
        """
        limit = min(max(1, int(limit)), settings.MAX_K)
        ordered: List[Movie] = []
        emitted: set[str] = {movie.title_id}

        def add_rows(rows: List[Movie]) -> None:
            for row in rows:
                if len(ordered) >= limit:
                    return
                if row.title_id in emitted:
                    continue
                emitted.add(row.title_id)
                ordered.append(row)

        if self.is_ready and self.registry is not None and movie.movielens_id is not None:
            try:
                inference_started = time.perf_counter()
                result = self.registry.similar_by_provider_id(
                    int(movie.movielens_id),
                    k=limit * 3,
                    exclude_provider_ids=[int(movie.movielens_id)],
                )
                RECOMMENDATION_INFERENCE_DURATION.labels("similar").observe(
                    time.perf_counter() - inference_started
                )
            except Exception:
                logger.exception("Similar-title inference failed for %s", movie.title_id)
                result = {}
            provider_ids = [int(value) for value in result.get("provider_ids", [])]
            if provider_ids:
                rows = (
                    db.query(Movie)
                    .filter(
                        Movie.movielens_id.in_(provider_ids),
                        Movie.media_type == movie.media_type,
                        Movie.is_adult.is_(False),
                    )
                    .all()
                )
                by_provider = {
                    int(row.movielens_id): row for row in rows
                    if row.movielens_id is not None
                }
                add_rows([by_provider[value] for value in provider_ids if value in by_provider])
                if len(ordered) >= limit:
                    return ordered

        source_genres = {
            part.strip().casefold()
            for part in (movie.genres or "").replace(",", "|").split("|")
            if part.strip()
        }
        base_query = db.query(Movie).filter(
            ~Movie.title_id.in_(emitted),
            Movie.media_type == movie.media_type,
            Movie.is_adult.is_(False),
        )
        if source_genres:
            candidates = base_query.filter(
                or_(*[Movie.genres.ilike(f"%{genre}%") for genre in source_genres])
            ).order_by(
                Movie.popularity.desc().nullslast(),
                Movie.vote_count.desc().nullslast(),
                Movie.vote_average.desc().nullslast(),
                Movie.title_id.asc(),
            ).limit(max(limit * 25, 120)).all()
        else:
            candidates = []

        def overlap(row: Movie) -> int:
            row_genres = {
                part.strip().casefold()
                for part in (row.genres or "").replace(",", "|").split("|")
                if part.strip()
            }
            return len(source_genres & row_genres)

        candidates.sort(key=lambda row: (-overlap(row), -float(row.popularity or 0.0),
                                         row.title_id))
        add_rows([row for row in candidates if not source_genres or overlap(row) > 0])

        if len(ordered) < limit:
            popular = (
                base_query.order_by(
                    Movie.popularity.desc().nullslast(),
                    Movie.vote_count.desc().nullslast(),
                    Movie.vote_average.desc().nullslast(),
                    Movie.title_id.asc(),
                ).limit(max(limit * 10, 80)).all()
            )
            add_rows(popular)
        return ordered

    def recommend(self, db: Session, user_id: int, k: int = 10,
                  model_name: str = "hybrid", search_query: Optional[str] = None) -> RecommendationResponse:
        rows = self.recommend_rows(db, user_id, k=k)
        items = rows.get("for_you", [])
        return RecommendationResponse(
            user_id=user_id, model=rows["model"], k=len(items), items=items,
            generated_at=datetime.fromisoformat(rows["generated_at"]),
        )


recommendation_service = RecommendationService()
