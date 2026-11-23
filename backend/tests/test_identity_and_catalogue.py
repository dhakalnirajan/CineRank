import uuid

from app.core.ids import generate_title_id, is_title_id
from app.models.entities import Movie, User, Rating, CatalogueSortIndex, CatalogueState
from app.services.catalogue_service import make_sort_key, rebuild_catalogue_sort_index


def test_title_id_is_prefixed_uuid7_and_unique():
    generated = [generate_title_id() for _ in range(1000)]
    assert len(set(generated)) == len(generated)
    for value in generated:
        assert value.startswith("title_")
        assert len(value) == 42
        assert is_title_id(value)
        assert uuid.UUID(value.removeprefix("title_")).version == 7


def test_sort_key_is_deterministic_and_alphabetical():
    values = ["24 (Time Story)", "2012", "13B: Fear Has a New Address", "13 Reasons Why"]
    assert make_sort_key("Ａ Movie") == make_sort_key("a movie")
    assert sorted(values, key=make_sort_key) == [
        "13 Reasons Why", "13B: Fear Has a New Address", "2012", "24 (Time Story)"
    ]


def test_rebuild_publishes_order_without_rewriting_primary_or_foreign_keys(db_session):
    user = User(username="catalogue-test", external_id="42")
    db_session.add(user)
    titles = [
        Movie(title_id=generate_title_id(), title="24 (Time Story)", sort_key=make_sort_key("24 (Time Story)"), movielens_id=24),
        Movie(title_id=generate_title_id(), title="13B: Fear Has a New Address", sort_key=make_sort_key("13B: Fear Has a New Address"), movielens_id=13),
    ]
    db_session.add_all(titles)
    db_session.flush()
    rating = Rating(user_id=user.id, title_id=titles[0].title_id, rating=4.5, relevance=0.9)
    db_session.add(rating)
    db_session.commit()
    original_ids = {row.title: row.title_id for row in titles}
    original_fk = rating.title_id

    inserted = Movie(title_id=generate_title_id(), title="2012", sort_key=make_sort_key("2012"), movielens_id=2012)
    db_session.add(inserted)
    db_session.commit()
    result = rebuild_catalogue_sort_index(db_session, batch_size=2)

    state = db_session.query(CatalogueState).filter_by(id=1).one()
    rows = (db_session.query(CatalogueSortIndex, Movie)
            .join(Movie, Movie.title_id == CatalogueSortIndex.title_id)
            .filter(CatalogueSortIndex.version_id == state.active_version)
            .order_by(CatalogueSortIndex.sort_order).all())
    assert [movie.title for _index, movie in rows] == [
        "13B: Fear Has a New Address", "2012", "24 (Time Story)"
    ]
    assert {movie.title: movie.title_id for _index, movie in rows if movie.title in original_ids} == original_ids
    assert db_session.query(Rating).one().title_id == original_fk
    assert result["titles"] == 3
