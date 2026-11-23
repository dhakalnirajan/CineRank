import json

from scripts import import_extended_catalogue as importer


def imdb_row(**overrides):
    values = {
        "id": "tt1234567",
        "title": "A Sourced Film",
        "original_title": "A Sourced Film",
        "type": "movie",
        "year": 2020,
        "end_year": None,
        "rating": 8.1,
        "votes": 2450,
        "runtime": 104,
        "genres": "Drama, Mystery",
        "is_adult": 0,
        "is_animation": 0,
        "poster": "https://images.example/poster.jpg",
        "cast": "First Actor, Second Actor",
        "popularity": None,
    }
    values.update(overrides)
    return values


def test_tvmaze_summary_is_plain_text():
    summary = "<p>A <b>real</b> summary about a show.</p>"
    assert importer.strip_html(summary) == "A real summary about a show."


def test_brightdata_credits_are_parsed_without_internal_identifiers():
    payload = importer.brightdata_payload(
        {
            "presentation": "A sourced synopsis about the film and its characters.",
            "storyline": "A much longer sourced synopsis about the film and its characters.",
            "credit": json.dumps(
                [
                    {
                        "title": "Directors",
                        "names": [
                            {"name": "Ada Director", "link": "https://example/name"},
                            {"name": "Bea Director", "link": "https://example/name"},
                        ],
                    }
                ]
            ),
            "top_cast": json.dumps(
                [{"actor": "Grace Actor", "character": "Pilot", "link": "https://example/name"}]
            ),
        }
    )

    assert payload["overview"] == "A sourced synopsis about the film and its characters."
    assert [person["name"] for person in payload["directors"]] == [
        "Ada Director",
        "Bea Director",
    ]
    assert payload["cast"] == [{"name": "Grace Actor", "character": "Pilot"}]


def test_movie_record_uses_only_sourced_metadata():
    record = importer.build_record(
        imdb_row(),
        "movie",
        {
            "overview": "A sourced synopsis.",
            "directors": [{"name": "Ada Director", "job": "Director"}],
            "cast": [{"name": "Grace Actor", "character": "Pilot"}],
        },
        None,
    )

    assert record is not None
    assert record["overview"] == "A sourced synopsis."
    assert record["media_type"] == "movie"
    assert record["imdb_id"] == "tt1234567"
    assert record["runtime"] == 104
    assert record["source"] == "imdb+imdb-media"
    assert record["popularity"] == 2.45
    assert json.loads(record["cast_json"])[0]["name"] == "Grace Actor"
    assert not record["tmdb_id"] if "tmdb_id" in record else True


def test_tv_record_requires_a_real_summary_and_uses_tvmaze_artwork():
    row = imdb_row(type="tv_series", title="A Sourced Show", runtime=None)
    record = importer.build_record(
        row,
        "tv",
        None,
        {
            "id": 42,
            "url": "https://www.tvmaze.com/shows/42/a-sourced-show",
            "summary": "<p>A sourced show summary.</p>",
            "genres": ["Drama"],
            "averageRuntime": 52,
            "image": {"original": "https://images.example/show.jpg"},
            "network": {"name": "A Network"},
            "language": "English",
            "status": "Ended",
        },
    )

    assert record is not None
    assert record["media_type"] == "tv"
    assert record["overview"] == "A sourced show summary."
    assert record["runtime"] == 52
    assert record["poster_path"] == "https://images.example/show.jpg"
    assert record["source"] == "imdb+tvmaze"
    assert json.loads(record["source_metadata_json"])["tvmaze_id"] == 42
    assert importer.build_record(row, "tv", None, None) is None


def test_duplicate_identity_uses_media_type_title_and_year():
    assert importer.title_key("movie", "The Matrix (1999)", 1999) == (
        "movie",
        "matrix",
        1999,
    )
    assert importer.title_key("tv", "The Matrix", 1999) != importer.title_key(
        "movie", "The Matrix", 1999
    )
