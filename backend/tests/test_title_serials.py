from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import get_title_by_serial
from app.core.serial_numbers import format_title_serial, parse_title_serial
from app.db.session import Base
from app.models.entities import Movie
from app.schemas.schemas import MovieOut


def test_serial_numbers_are_assigned_and_immutable(db_session):
    first = Movie(title="First title")
    second = Movie(title="Second title")
    db_session.add_all([first, second])
    db_session.commit()

    assert (first.serial_number, second.serial_number) == (1, 2)
    original = first.serial_number
    first.title = "First title updated"
    first.sort_key = "zzzz"
    db_session.commit()
    assert first.serial_number == original


def test_deleted_serial_number_is_not_reused(db_session):
    first = Movie(title="Removed title")
    db_session.add(first)
    db_session.commit()
    removed_serial = first.serial_number
    db_session.delete(first)
    db_session.commit()

    replacement = Movie(title="Replacement title")
    db_session.add(replacement)
    db_session.commit()

    assert replacement.serial_number == removed_serial + 1


def test_concurrent_creation_allocates_unique_serials(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'serials.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(3)

    def create_title(index: int) -> int:
        db = Session()
        try:
            barrier.wait()
            movie = Movie(title=f"Concurrent title {index}")
            db.add(movie)
            db.commit()
            return int(movie.serial_number)
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            serials = list(pool.map(create_title, range(3)))
        assert sorted(serials) == [1, 2, 3]
        assert len(set(serials)) == 3
    finally:
        engine.dispose()


def test_public_serial_format_and_media_scoped_lookup(db_session):
    movie = Movie(title="A film", media_type="movie")
    series = Movie(title="A series", media_type="tv")
    db_session.add_all([movie, series])
    db_session.commit()

    assert format_title_serial(movie.serial_number) == "000001"
    assert parse_title_serial("000001") == 1
    assert MovieOut.model_validate(movie).serial_number == "000001"

    found = get_title_by_serial("movie", "000001", db_session)
    assert found.title_id == movie.title_id

    with pytest.raises(HTTPException) as wrong_type:
        get_title_by_serial("tv", "000001", db_session)
    assert wrong_type.value.status_code == 404

    with pytest.raises(HTTPException) as missing:
        get_title_by_serial("movie", "999999", db_session)
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as invalid:
        get_title_by_serial("movie", "not-a-number", db_session)
    assert invalid.value.status_code == 404
