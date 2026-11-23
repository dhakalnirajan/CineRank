"""Portable, non-destructive catalogue ordering and atomic version publication."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.entities import Movie, CatalogueState, CatalogueSortIndex


def make_sort_key(title: str) -> str:
    """Return a bounded NFKC/casefold key for binary-collation ordering.

    The stored alphabet is the normalised title text. Runtime ordering applies
    each database dialect's binary collation so e.g. locale-specific collations
    cannot silently reorder digits, punctuation, and non-ASCII letters. Titles
    are already bounded to 512 input characters by the catalogue schema.
    """
    normalized = unicodedata.normalize("NFKC", title or "").casefold().strip()
    return normalized[:512]


def sort_key_expression(db: Session):
    """Apply a deterministic binary collation to the sort-key SQL expression."""
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        return Movie.sort_key.collate("C")
    if dialect in {"mysql", "mariadb"}:
        return Movie.sort_key.collate("utf8mb4_bin")
    if dialect == "sqlite":
        return Movie.sort_key.collate("BINARY")
    if dialect in {"mssql", "sqlserver"}:
        return Movie.sort_key.collate("Latin1_General_100_BIN2")
    if dialect == "oracle":
        return func.nlssort(Movie.sort_key, "NLS_SORT=BINARY")
    return Movie.sort_key


def get_or_create_catalogue_state(db: Session) -> CatalogueState:
    state = db.query(CatalogueState).filter(CatalogueState.id == 1).with_for_update().first()
    if state is None:
        state = CatalogueState(id=1, active_version=0)
        db.add(state)
        db.flush()
    return state


def append_to_active_sort_index(db: Session, title_id: str) -> None:
    """Make a freshly inserted title visible immediately at the active index tail."""
    state = get_or_create_catalogue_state(db)
    if state.active_version <= 0:
        return
    exists = db.query(CatalogueSortIndex).filter_by(
        version_id=state.active_version, title_id=title_id
    ).first()
    if exists:
        return
    # Serialise concurrent appends on the singleton state row before reading MAX.
    db.query(CatalogueState).filter_by(id=1).with_for_update().one()
    last_position = db.query(func.max(CatalogueSortIndex.sort_order)).filter_by(
        version_id=state.active_version
    ).scalar() or 0
    db.add(CatalogueSortIndex(
        version_id=state.active_version, title_id=title_id,
        sort_order=int(last_position) + 1,
    ))


def rebuild_catalogue_sort_index(db: Session, batch_size: int | None = None,
                                 retain_versions: int = 2) -> dict:
    """Build a new index in bounded batches and atomically publish its version.

    On PostgreSQL/MySQL and other engines with row-level ``FOR UPDATE``, a
    dedicated lock session holds the singleton catalogue-state row while a
    second session builds the index. Writers that use ``append_to_active_sort_index``
    wait at that row and then append to the newly published version. SQLite uses
    one ``BEGIN IMMEDIATE`` transaction because it has a database-wide writer
    lock rather than row-level locks. No title primary key or foreign key is ever
    rewritten.
    """
    batch_size = batch_size or settings.CATALOGUE_SORT_BATCH_SIZE
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    dialect = db.get_bind().dialect.name
    # SQLite has a database-wide writer lock; use the caller's session and keep
    # the whole rebuild in one transaction. Other engines support a dedicated
    # lock session plus separately committed batch writer.
    lock_db = db if dialect == "sqlite" else sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
    work_db = lock_db
    separate_writer = False
    try:
        if dialect == "sqlite":
            lock_db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        state = get_or_create_catalogue_state(lock_db)
        active_version = int(state.active_version)

        if dialect != "sqlite":
            # Keep the row lock alive through the whole build, while committing
            # each batch from a separate connection to bound transaction size.
            work_db = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)()
            separate_writer = True

        current_max = work_db.query(func.max(CatalogueSortIndex.version_id)).scalar() or 0
        version = max(int(current_max), active_version) + 1
        work_db.query(CatalogueSortIndex).filter(
            CatalogueSortIndex.version_id > active_version
        ).delete(synchronize_session=False)
        if separate_writer:
            work_db.commit()

        total = int(work_db.query(func.count(Movie.title_id)).scalar() or 0)
        last_key = None
        last_id = None
        position = 0
        sort_key_col = sort_key_expression(work_db)

        while True:
            query = work_db.query(Movie.title_id, Movie.sort_key).order_by(
                sort_key_col.asc(), Movie.title_id.asc()
            )
            if last_key is not None:
                query = query.filter(or_(
                    sort_key_col > last_key,
                    and_(sort_key_col == last_key, Movie.title_id > last_id),
                ))
            rows = query.limit(batch_size).all()
            if not rows:
                break
            mappings = []
            for title_id, key_value in rows:
                position += 1
                mappings.append({
                    "version_id": version,
                    "title_id": title_id,
                    "sort_order": position,
                })
            work_db.bulk_insert_mappings(CatalogueSortIndex, mappings)
            if separate_writer:
                work_db.commit()
            last_id, last_key = rows[-1][0], rows[-1][1]

        if position != total:
            work_db.query(CatalogueSortIndex).filter_by(version_id=version).delete(
                synchronize_session=False
            )
            if separate_writer:
                work_db.commit()
            raise RuntimeError(f"Sort index build mismatch: expected {total}, wrote {position}")

        # Publish only after the complete staging index has passed row-count checks.
        state.active_version = version
        state.published_at = datetime.now(timezone.utc)
        lock_db.commit()
        if separate_writer:
            cutoff = max(1, version - retain_versions + 1)
            work_db.query(CatalogueSortIndex).filter(
                CatalogueSortIndex.version_id < cutoff
            ).delete(synchronize_session=False)
            work_db.commit()
        else:
            cutoff = max(1, version - retain_versions + 1)
            work_db.query(CatalogueSortIndex).filter(
                CatalogueSortIndex.version_id < cutoff
            ).delete(synchronize_session=False)
            work_db.commit()

        db.expire_all()
        return {"version": version, "titles": position,
                "previous_version": active_version}
    except Exception:
        lock_db.rollback()
        if separate_writer:
            work_db.rollback()
        raise
    finally:
        if separate_writer:
            work_db.close()
        if lock_db is not db:
            lock_db.close()
