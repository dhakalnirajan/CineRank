import json

from ranker.production_ranker import Candidate, ProductionRanker
from crawler.web_discovery import WebDiscoveryCrawler, _normalise_url


def test_ranker_accepts_cold_start_titles():
    ranked = ProductionRanker().rank([
        Candidate(title_id="title_a", score=0.9, source="als", genres="Drama"),
        Candidate(title_id="title_b", score=0.8, source="content_cold_start", genres="Drama|Mystery"),
        Candidate(title_id="title_c", score=0.6, source="catalogue_popularity", genres="Comedy"),
    ], k=3, seen={"title_a"})
    assert "title_b" in [row.title_id for row in ranked]
    assert "title_a" not in [row.title_id for row in ranked]


def test_url_normalisation_removes_fragment_and_tracking():
    assert _normalise_url("https://example.com/title/abc?utm_source=x&year=2020#cast") == "https://example.com/title/abc?year=2020"
    assert _normalise_url("javascript:alert(1)") is None
    assert _normalise_url("https://user:pass@example.com/x") is None


def test_jsonld_movie_metadata_is_extracted():
    crawler = WebDiscoveryCrawler()
    html = f'''<html><head><script type="application/ld+json">{json.dumps({
        "@context": "https://schema.org", "@type": "Movie",
        "name": "The Example Film", "datePublished": "2025-10-01",
        "genre": ["Drama", "Mystery"], "description": "Structured movie description",
        "sameAs": ["https://www.imdb.com/title/tt1234567/"],
        "director": {"@type": "Person", "name": "A Director"},
    })}</script></head><body><a href="/catalogue/next">Next</a></body></html>'''.encode()
    record, links = crawler._extract_entity(html, "https://movies.example/catalogue/one")
    assert record["title"] == "The Example Film"
    assert record["media_type"] == "movie"
    assert record["year"] == 2025
    assert record["imdb_id"] == "tt1234567"
    assert record["genres"] == "Drama|Mystery"
    assert links == ["https://movies.example/catalogue/next"]


def test_weighted_rrf_uses_rank_positions_not_raw_score_scales():
    ranker = ProductionRanker(source_weights={"source_a": 1.0, "source_b": 1.0}, rrf_constant=10)
    ranked = ranker.rank([
        Candidate("title_a", 100000.0, "source_a", "Drama"),
        Candidate("title_b", 1.0, "source_a", "Comedy"),
        Candidate("title_b", 0.0001, "source_b", "Comedy"),
        Candidate("title_a", -100.0, "source_b", "Drama"),
    ], k=2)
    assert [item.title_id for item in ranked] == ["title_a", "title_b"]
    assert set(ranked[0].sources) == {"source_a", "source_b"}
    assert ranked[0].final_score > 0


def test_ranker_filters_non_finite_scores_and_seen_items_deterministically():
    ranked = ProductionRanker().rank([
        Candidate("seen", 99.0, "als"),
        Candidate("valid_b", 0.5, "als"),
        Candidate("valid_a", 0.5, "als"),
        Candidate("invalid", float("nan"), "als"),
    ], k=5, seen={"seen"})
    assert [item.title_id for item in ranked] == ["valid_a", "valid_b"]


def test_explicit_preferences_filter_adult_excluded_and_unknown_metadata():
    from types import SimpleNamespace
    from app.services.recommendation_service import RecommendationService

    movies = {
        "allowed": SimpleNamespace(title_id="allowed", genres="Drama", is_adult=False, year=2020, runtime=110),
        "excluded": SimpleNamespace(title_id="excluded", genres="Comedy", is_adult=False, year=2020, runtime=100),
        "adult": SimpleNamespace(title_id="adult", genres="Drama", is_adult=True, year=2020, runtime=100),
        "unknown": SimpleNamespace(title_id="unknown", genres="Drama", is_adult=False, year=None, runtime=100),
    }
    candidates = [Candidate(key, 1.0, "hybrid_model", value.genres) for key, value in movies.items()]
    filtered = RecommendationService._apply_preferences(
        candidates, movies, {
            "preferred": {"drama"}, "excluded": {"comedy"},
            "include_adult": False, "min_year": 2000, "max_runtime": 180,
        },
    )
    assert [item.title_id for item in filtered] == ["allowed"]
    assert filtered[0].score == 1.1
