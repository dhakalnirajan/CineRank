from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, event, false, func,
)
from sqlalchemy.orm import relationship, synonym

ID_TYPE = BigInteger().with_variant(Integer, "sqlite")

from app.core.ids import generate_title_id
from app.core.serial_numbers import allocate_title_serial_numbers
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(64), unique=True, index=True, nullable=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(254), unique=True, index=True, nullable=True)
    password_hash = Column(String(512), nullable=True)
    avatar_url = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    ratings = relationship("Rating", back_populates="user", cascade="all, delete-orphan")
    watchlist_entries = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    search_logs = relationship("SearchLog", back_populates="user")
    recommendation_logs = relationship("RecommendationLog", back_populates="user")
    interactions = relationship("Interaction", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    email_tokens = relationship("EmailActionToken", back_populates="user", cascade="all, delete-orphan")


class EmailActionToken(Base):
    """Single-use, hashed email verification or password reset token."""
    __tablename__ = "email_action_tokens"
    __table_args__ = (
        Index("ix_email_action_tokens_user_purpose", "user_id", "purpose", "used_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = Column(String(24), nullable=False)
    email = Column(String(254), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="email_tokens")


class UserPreference(Base):
    """Explicit recommendation controls owned by one account."""
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("min_year IS NULL OR min_year BETWEEN 1888 AND 2100", name="ck_user_preferences_min_year"),
        CheckConstraint("max_runtime IS NULL OR max_runtime BETWEEN 30 AND 600", name="ck_user_preferences_max_runtime"),
    )

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    preferred_genres_json = Column(Text, nullable=False, default="[]", server_default="[]")
    excluded_genres_json = Column(Text, nullable=False, default="[]", server_default="[]")
    include_adult = Column(Boolean, nullable=False, default=False, server_default=false())
    min_year = Column(Integer, nullable=True)
    max_runtime = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User")


class UserSession(Base):
    """Revocable refresh session. Only the SHA-256 hash of the refresh token is stored."""
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_active", "user_id", "revoked_at", "expires_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    user_agent = Column(String(255), nullable=True)

    user = relationship("User", back_populates="sessions")


class TitleSerialSequence(Base):
    """Single-row transactional counter for public title serial numbers."""
    __tablename__ = "title_serial_sequence"

    id = Column(Integer, primary_key=True, default=1)
    next_value = Column(Integer, nullable=False, default=1)


class Movie(Base):
    """Movie/show catalogue row. ``title_id`` is immutable for its lifetime."""
    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint("media_type", "tmdb_id", name="uq_movies_media_tmdb"),
        Index("ix_movies_type_year", "media_type", "year"),
        Index("ix_movies_sort_key_title_id", "sort_key", "title_id"),
    )

    title_id = Column(String(42), primary_key=True, default=generate_title_id)
    # Backwards-compatible attribute alias for older internal code. The DB PK is title_id.
    id = synonym("title_id")
    serial_number = Column(Integer, nullable=False, unique=True, index=True)
    media_type = Column(String(8), nullable=False, default="movie", index=True)
    tmdb_id = Column(Integer, nullable=True)
    movielens_id = Column(Integer, nullable=True, unique=True, index=True)
    imdb_id = Column(String(24), nullable=True, index=True)
    title = Column(String(512), nullable=False, index=True)
    original_title = Column(String(512), nullable=True)
    sort_key = Column(String(512), nullable=False, default="", index=False)
    genres = Column(String(1024), nullable=False, default="")
    year = Column(Integer, nullable=True)
    overview = Column(Text, nullable=True)
    poster_path = Column(String(1024), nullable=True)
    backdrop_path = Column(String(1024), nullable=True)
    popularity = Column(Float, nullable=False, default=0.0)
    vote_average = Column(Float, nullable=True)
    vote_count = Column(Integer, nullable=True)
    runtime = Column(Integer, nullable=True)
    directors_json = Column(Text, nullable=True)
    cast_json = Column(Text, nullable=True)
    is_adult = Column(Boolean, nullable=False, default=False)
    source = Column(String(32), nullable=False, default="unknown")
    source_url = Column(String(2048), nullable=True)
    source_url_hash = Column(String(64), nullable=True, unique=True, index=True)
    source_domain = Column(String(255), nullable=True, index=True)
    source_metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Legacy adapter aliases; public APIs should use title_id/movielens_id explicitly.
    movie_id = synonym("movielens_id")
    ratings = relationship("Rating", back_populates="movie")


@event.listens_for(Movie, "before_insert")
def _assign_title_serial_number(_mapper, connection, target: Movie) -> None:
    """Allocate a public number for every ORM-created title."""
    if target.serial_number is None:
        target.serial_number = allocate_title_serial_numbers(connection, 1)[0]


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "title_id", name="uq_ratings_user_title"),
        Index("ix_ratings_user_timestamp", "user_id", "timestamp"),
    )

    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title_id = Column(String(42), ForeignKey("movies.title_id", ondelete="CASCADE"), nullable=False, index=True)
    movie_id = synonym("title_id")
    rating = Column(Float, nullable=False)
    relevance = Column(Float, nullable=False, default=1.0)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_implicit = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")


class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title_id = Column(String(42), ForeignKey("movies.title_id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)  # impression, click, play, complete, like
    value = Column(Float, nullable=False, default=1.0)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    metadata_json = Column(Text, nullable=True)
    user = relationship("User", back_populates="interactions")


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "title_id", name="uq_watchlist_user_title"),)
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title_id = Column(String(42), ForeignKey("movies.title_id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user = relationship("User", back_populates="watchlist_entries")


class SearchLog(Base):
    __tablename__ = "search_logs"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    query = Column(String(256), nullable=False)
    results_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user = relationship("User", back_populates="search_logs")


class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model_name = Column(String(64), nullable=False)
    title_ids_json = Column(Text, nullable=False)
    k = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user = relationship("User", back_populates="recommendation_logs")


class CatalogueState(Base):
    __tablename__ = "catalogue_state"
    id = Column(Integer, primary_key=True, default=1)
    active_version = Column(BigInteger, nullable=False, default=0)
    published_at = Column(DateTime(timezone=True), nullable=True)


class CatalogueSortIndex(Base):
    """Versioned position index. Rebuilds never mutate title IDs or FK values."""
    __tablename__ = "catalogue_sort_index"
    __table_args__ = (
        UniqueConstraint("version_id", "sort_order", name="uq_catalogue_version_order"),
        Index("ix_catalogue_version_order", "version_id", "sort_order"),
    )
    version_id = Column(BigInteger, primary_key=True)
    title_id = Column(String(42), ForeignKey("movies.title_id", ondelete="CASCADE"), primary_key=True)
    sort_order = Column(BigInteger, nullable=False)


class JobLease(Base):
    __tablename__ = "job_leases"
    job_name = Column(String(100), primary_key=True)
    owner_token = Column(String(64), nullable=False)
    lease_expires_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class JobRun(Base):
    __tablename__ = "job_runs"
    job_name = Column(String(100), primary_key=True)
    last_success_date = Column(Date, nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_date = Column(Date, nullable=True)
    last_status = Column(String(16), nullable=False, default="never")
    last_error = Column(Text, nullable=True)


class CrawlFrontier(Base):
    __tablename__ = "crawl_frontier"
    url_hash = Column(String(64), primary_key=True)
    url = Column(String(2048), nullable=False)
    domain = Column(String(255), nullable=False, index=True)
    depth = Column(Integer, nullable=False, default=0)
    priority = Column(Integer, nullable=False, default=100, index=True)
    state = Column(String(16), nullable=False, default="queued", index=True)
    discovered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    next_crawl_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(Text, nullable=True)


class CrawledPage(Base):
    __tablename__ = "crawled_pages"
    url_hash = Column(String(64), primary_key=True)
    url = Column(String(2048), nullable=False)
    etag = Column(String(512), nullable=True)
    last_modified = Column(String(512), nullable=True)
    content_sha256 = Column(String(64), nullable=True)
    status_code = Column(Integer, nullable=True)
    last_crawled_at = Column(DateTime(timezone=True), nullable=True)
    last_changed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)


class ModelBenchmark(Base):
    __tablename__ = "model_benchmarks"
    __table_args__ = (UniqueConstraint("bundle_id", "model_name", "catalogue_version", name="uq_model_benchmark_bundle_model_catalogue"),)
    id = Column(ID_TYPE, primary_key=True, autoincrement=True)
    bundle_id = Column(String(128), nullable=False, index=True)
    model_name = Column(String(64), nullable=False)
    catalogue_version = Column(BigInteger, nullable=False, default=0)
    evaluated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sample_users = Column(Integer, nullable=False, default=0)
    metrics_json = Column(Text, nullable=False)
    passed = Column(Boolean, nullable=False, default=False)
    reason = Column(Text, nullable=True)
