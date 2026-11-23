from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.ids import generate_title_id
from app.core.serial_numbers import format_title_serial
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import Movie
from app.schemas.schemas import HistoryItem, MovieOut, RecommendationItem
from app.services.catalogue_service import make_sort_key
from app.services.recommendation_service import RecommendationService
from ranker.production_ranker import RankedItem
from app.services.title_display import normalize_display_title

# Exact strings supplied by MovieLens. Leading punctuation, commas, parentheses,
# and release years are part of the provider title, not display decoration.
TITLE_CASES = [
    "'burbs, The (1989)",
    "(500) Days of Summer (2009)",
    "*batteries not included (1987)",
    "...And Justice for All (1979)",
    "10 (1979)",
    "10 Cloverfield Lane (2016)",
    "10 Things I Hate About You (1999)",
    "10,000 BC (2008)",
    "101 Dalmatians (1996)",
    "101 Dalmatians (One Hundred and One Dalmatians) (1961)",
    "2012 (2009)",
    "Amélie (2001)",
]


@pytest.fixture()
def api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def seed_catalogue(SessionFactory) -> dict[str, Movie]:
    db = SessionFactory()
    try:
        movies = {}
        for index, title in enumerate(TITLE_CASES, start=1):
            movie = Movie(
                title_id=generate_title_id(),
                serial_number=index,
                media_type="movie",
                movielens_id=10_000 + index,
                title=title,
                sort_key=make_sort_key(title),
                genres="Drama",
                year=2000,
                source="movielens",
            )
            db.add(movie)
            movies[title] = movie
        db.commit()
        for movie in movies.values():
            db.refresh(movie)
        return movies
    finally:
        db.close()


def test_library_articles_are_normalized_for_display_only():
    assert normalize_display_title("Matrix, The (1999)") == "The Matrix"
    assert normalize_display_title("The Matrix (1999)") == "The Matrix"
    assert normalize_display_title("'burbs, The (1989)") == "The 'burbs"
    assert normalize_display_title("10,000 BC (2008)") == "10,000 BC"
    assert normalize_display_title("Amélie (2001)") == "Amélie"


def test_exact_titles_survive_storage_and_sort_key_generation(db_session):
    for title in TITLE_CASES:
        movie = Movie(
            title_id=generate_title_id(),
            serial_number=len(db_session.new) + 1,
            media_type="movie",
            movielens_id=20_000 + len(db_session.new),
            title=title,
            sort_key=make_sort_key(title),
            source="movielens",
        )
        db_session.add(movie)
    db_session.commit()

    stored = {movie.title for movie in db_session.query(Movie).all()}
    assert stored == set(TITLE_CASES)
    for movie in db_session.query(Movie).all():
        assert movie.title in TITLE_CASES
        assert movie.sort_key == make_sort_key(movie.title)


def test_catalogue_search_and_detail_return_the_same_exact_title(api):
    client, SessionFactory = api
    movies = seed_catalogue(SessionFactory)

    catalogue = client.get("/api/v1/movies", params={"limit": 100}).json()
    catalogue_titles = {item["title"] for item in catalogue["items"]}
    assert catalogue_titles == set(TITLE_CASES)

    for title, movie in movies.items():
        detail = client.get(f"/api/v1/titles/movie/{movie.serial_number:06d}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["title"] == title
        assert body["display_title"] == normalize_display_title(title)
        assert body["title_id"] == movie.title_id
        assert body["serial_number"] == format_title_serial(movie.serial_number)

        search = client.get("/api/v1/search", params={"q": title, "limit": 100})
        assert search.status_code == 200
        search_titles = [item["title"] for item in search.json()["results"]]
        assert search_titles == [title]


def test_title_payload_preserves_catalogue_metadata(api):
    client, SessionFactory = api
    db = SessionFactory()
    try:
        movie = Movie(
            title_id=generate_title_id(),
            serial_number=9001,
            media_type="movie",
            tmdb_id=424242,
            title="Metadata Probe (2024)",
            sort_key=make_sort_key("Metadata Probe (2024)"),
            genres="Drama|Mystery",
            year=2024,
            overview="A title used to verify catalogue metadata transport.",
            runtime=112,
            directors_json='[{"name": "Ava Director", "job": "Director"}]',
            cast_json='[{"name": "Lead Actor", "character": "Detective"}]',
            source="tmdb",
        )
        db.add(movie)
        db.commit()
        db.refresh(movie)
    finally:
        db.close()

    expected = {
        "title": "Metadata Probe (2024)",
        "display_title": "Metadata Probe",
        "year": 2024,
        "genres": "Drama|Mystery",
        "overview": "A title used to verify catalogue metadata transport.",
        "runtime": 112,
        "directors_json": '[{"name": "Ava Director", "job": "Director"}]',
        "cast_json": '[{"name": "Lead Actor", "character": "Detective"}]',
        "serial_number": "009001",
    }

    detail = client.get("/api/v1/titles/movie/009001")
    assert detail.status_code == 200
    assert {key: detail.json()[key] for key in expected} == expected

    catalogue = client.get("/api/v1/movies", params={"limit": 10})
    assert catalogue.status_code == 200
    item = next(entry for entry in catalogue.json()["items"] if entry["serial_number"] == "009001")
    assert {key: item[key] for key in expected} == expected

    search = client.get("/api/v1/search", params={"q": "Metadata Probe", "limit": 10})
    assert search.status_code == 200
    result = next(entry for entry in search.json()["results"] if entry["serial_number"] == "009001")
    assert {key: result[key] for key in expected} == expected


def test_catalogue_facets_report_available_media_and_genres(api):
    client, SessionFactory = api
    seed_catalogue(SessionFactory)

    response = client.get("/api/v1/catalogue/facets")
    assert response.status_code == 200
    body = response.json()
    assert body["media_types"] == [{"value": "movie", "count": len(TITLE_CASES)}]
    assert body["genres"][0] == {"value": "Drama", "count": len(TITLE_CASES)}
    assert all(entry["value"] != "Series" for entry in body["media_types"])


def test_response_and_history_schemas_do_not_rewrite_titles(api):
    _client, SessionFactory = api
    movies = seed_catalogue(SessionFactory)
    movie = movies["...And Justice for All (1979)"]

    out = MovieOut.model_validate(movie)
    assert out.title == "...And Justice for All (1979)"
    assert out.display_title == "...And Justice for All"
    assert out.serial_number == "000004"

    recommendation = RecommendationItem(
        title_id=movie.title_id,
        serial_number=movie.serial_number,
        media_type=movie.media_type,
        title=movie.title,
        genres=movie.genres,
        year=movie.year,
        poster_path=movie.poster_path,
        score=0.9,
    )
    history = HistoryItem(
        title_id=movie.title_id,
        serial_number=movie.serial_number,
        media_type=movie.media_type,
        title=movie.title,
        rating=4.5,
        timestamp=datetime.now(timezone.utc),
    )
    assert recommendation.title == movie.title
    assert recommendation.display_title == "...And Justice for All"
    assert history.title == movie.title
    assert history.display_title == "...And Justice for All"



def test_model_recommendations_are_hydrated_with_full_catalogue_metadata(api):
    _client, SessionFactory = api
    db = SessionFactory()
    try:
        movie = Movie(
            title_id=generate_title_id(),
            serial_number=9001,
            movielens_id=99123,
            tmdb_id=603,
            imdb_id="tt0133093",
            media_type="movie",
            title="The Matrix (1999)",
            original_title="The Matrix",
            genres="Action|Sci-Fi",
            year=1999,
            overview="A computer hacker learns the nature of his reality.",
            poster_path="/matrix-poster.jpg",
            backdrop_path="/matrix-backdrop.jpg",
            popularity=84.5,
            vote_average=8.2,
            vote_count=24000,
            runtime=136,
            directors_json='[{"name":"Lana Wachowski"},{"name":"Lilly Wachowski"}]',
            cast_json='[{"name":"Keanu Reeves","character":"Neo"}]',
            is_adult=False,
            source="tmdb",
        )
        db.add(movie)
        db.commit()

        service = RecommendationService()
        items = service._to_items(
            db,
            [RankedItem(
                title_id=movie.title_id,
                final_score=0.91,
                sources=["attention", "content"],
                genres=movie.genres,
            )],
        )

        assert len(items) == 1
        item = items[0]
        assert item.title_id == movie.title_id
        assert item.serial_number == "009001"
        assert item.tmdb_id == 603
        assert item.imdb_id == "tt0133093"
        assert item.original_title == "The Matrix"
        assert item.is_adult is False
        assert item.overview == movie.overview
        assert item.backdrop_path == movie.backdrop_path
        assert item.runtime == 136
        assert item.directors_json == movie.directors_json
        assert item.cast_json == movie.cast_json
        assert item.vote_average == 8.2
        assert item.vote_count == 24000
        assert item.score == pytest.approx(0.91)
        assert item.display_title == "The Matrix"
    finally:
        db.close()

def test_search_count_is_total_even_when_results_are_limited(api):
    client, SessionFactory = api
    db = SessionFactory()
    try:
        db.add_all([
            Movie(title=f"Matrix selection {index}", genres="Sci-Fi", popularity=10 - index)
            for index in range(3)
        ])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/search", params={"q": "Matrix", "limit": 1})

    assert response.status_code == 200
    assert response.json()["count"] == 3
    assert len(response.json()["results"]) == 1


def test_similar_titles_route_returns_hydrated_catalogue_rows(api, monkeypatch):
    client, SessionFactory = api
    movies = seed_catalogue(SessionFactory)
    source = movies["'burbs, The (1989)"]
    neighbours = [
        movie for movie in movies.values() if movie.title_id != source.title_id
    ][:10]

    from app.services.recommendation_service import recommendation_service

    monkeypatch.setattr(
        recommendation_service,
        "similar_titles",
        lambda db, movie, limit: neighbours[:limit],
    )

    response = client.get(
        f"/api/v1/titles/movie/{format_title_serial(source.serial_number)}/similar",
        params={"limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title_id"] == source.title_id
    assert payload["model"] == "itemknn-content"
    assert [item["title_id"] for item in payload["items"]] == [
        movie.title_id for movie in neighbours
    ]
    assert all("display_title" in item for item in payload["items"])


def test_similar_titles_route_rejects_unknown_serial(api):
    client, _ = api
    response = client.get("/api/v1/titles/movie/999999/similar")
    assert response.status_code == 404


def test_click_interactions_enter_recommendation_history(db_session):
    from app.models.entities import Interaction, User

    user = User(username="clicker", password_hash="unused", is_active=True)
    movie = Movie(
        title_id=generate_title_id(),
        serial_number=1,
        media_type="movie",
        movielens_id=2571,
        title="Matrix, The (1999)",
        sort_key=make_sort_key("Matrix, The (1999)"),
        genres="Action|Sci-Fi|Thriller",
        year=1999,
        source="movielens",
    )
    db_session.add_all([user, movie])
    db_session.commit()
    db_session.add(Interaction(
        user_id=user.id, title_id=movie.title_id, event_type="click", value=1.0,
    ))
    db_session.commit()

    history, seen_title_ids, seen_provider_ids = RecommendationService()._user_history(
        db_session, user.id
    )

    assert (2571, 3.5) in history
    assert movie.title_id in seen_title_ids
    assert 2571 in seen_provider_ids
