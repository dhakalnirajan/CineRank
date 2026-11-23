import json
from pathlib import Path

from scripts import import_catalogue_metadata as importer
from app.models.entities import Movie


def make_movie(**overrides) -> Movie:
    values = {
        "title_id": "title_test_metadata",
        "serial_number": 900001,
        "media_type": "movie",
        "title": "Romance (1999)",
        "year": 1999,
        "genres": "Drama",
    }
    values.update(overrides)
    return Movie(**values)


def test_title_matching_normalizes_years_and_leading_articles():
    assert importer.normalize_title("Matrix, The (1999)") == "matrix"
    assert importer.normalize_title("The Lord of the Rings (2001)") == "lord of the rings"
    assert importer.normalize_title("Amelie") == "amelie"


def test_metadata_patch_fills_missing_fields_without_overwriting():
    movie = make_movie(overview="Existing overview", tmdb_id=1, genres="Drama")
    row = {
        "id": "26338",
        "overview": "A sourced overview.",
        "directors": "Catherine Breillat",
        "cast": "Caroline Ducey, Sagamore Stevenin",
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
        "runtime": "99",
        "genres": "Drama, Romance",
        "tconst": "tt0194314",
        "vote_average": "5.5",
        "vote_count": "100",
        "popularity": "12.5",
    }

    patch = importer.metadata_patch(movie, row, overwrite=False)

    assert "overview" not in patch
    assert "tmdb_id" not in patch
    assert "genres" not in patch
    assert patch["runtime"] == 99
    assert patch["imdb_id"] == "tt0194314"
    assert patch["poster_path"] == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert patch["backdrop_path"] == "https://image.tmdb.org/t/p/w1280/backdrop.jpg"
    assert json.loads(patch["directors_json"]) == [
        {"name": "Catherine Breillat", "job": "Director"}
    ]
    assert [person["name"] for person in json.loads(patch["cast_json"])] == [
        "Caroline Ducey",
        "Sagamore Stevenin",
    ]


def test_overwrite_replaces_existing_fields():
    movie = make_movie(overview="Old", tmdb_id=171982, genres="Drama")
    row = {"id": "26338", "overview": "Correct", "genres": "Drama, Romance"}

    patch = importer.metadata_patch(movie, row, overwrite=True)

    assert patch["overview"] == "Correct"
    assert patch["tmdb_id"] == 26338
    assert patch["genres"] == "Drama|Romance"


def test_year_guard_rejects_a_stale_movie_identity():
    movie = make_movie(year=1999)
    wrong = {"release_date": "2012-10-09"}
    acceptable = {"release_date": "1996-12-16"}

    assert not importer.year_compatible(movie, wrong)
    assert importer.year_compatible(movie, acceptable)


def test_dataset_scan_deduplicates_ids_and_collects_ambiguous_fallbacks(tmp_path: Path):
    dataset = tmp_path / "metadata.csv"
    dataset.write_text(
        "id,title,original_title,release_date,overview,directors,cast,poster_path\n"
        "10,Film One,Film One,1999-01-01,,,,/one.jpg\n"
        "10,Film One,Film One,1999-01-01,Best overview,Director, Actor ,/one.jpg\n"
        "11,Romance,Romance,1999-01-01,First,Director A,Cast A,\n"
        "12,Romance,Romance,1999-01-01,Second,Director B,Cast B,\n",
        encoding="utf-8",
    )

    exact, fallback, count = importer.scan_dataset(
        dataset,
        {10},
        {("romance", 1999)},
    )

    assert count == 4
    assert exact[10]["overview"] == "Best overview"
    assert len(fallback[("romance", 1999)]) == 2
    assert importer._choose_fallback(("romance", 1999), set(), fallback[("romance", 1999)]) is None
