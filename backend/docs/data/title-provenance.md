# Title provenance and integrity audit

## Scope

This audit traced the ten reported titles from the active MovieLens bundle through import, SQLite storage, API serialization, and frontend rendering. It also checked every catalogue row, not only the reported titles.

The reported strings were:

- `'burbs, The (1989)`
- `(500) Days of Summer (2009)`
- `*batteries not included (1987)`
- `...And Justice for All (1979)`
- `10 (1979)`
- `10 Cloverfield Lane (2016)`
- `10 Things I Hate About You (1999)`
- `10,000 BC (2008)`
- `101 Dalmatians (1996)`
- `101 Dalmatians (One Hundred and One Dalmatians) (1961)`

## Result

The catalogue data is not corrupted. All ten strings are legitimate MovieLens title conventions and are stored exactly as supplied. No title was repaired or rewritten.

The visible fragments such as `*NArtwork unavailable`, `.JArtwork unavailable`, and `1DArtwork unavailable` came from the frontend poster fallback. `Poster` derived initials from the title, including leading punctuation, and placed a screen-reader-only `Artwork unavailable` label in the same container. Text extraction therefore concatenated the decorative initials and the fallback label. The database, API, and title fields were not involved.

## Source and storage comparison

The active bundle catalogue is `backend/artifacts/models/bundles/c0d9706377e4d05408f8f74c9d38a60a/catalogue.csv`. It has the columns `movielens_id`, `title`, `genres`, `year`, and `media_type`. It has no poster column.

Comparison against `backend/data/cinerank.db`:

- 5,750 database rows and 5,750 source rows.
- 0 rows missing from the source.
- 0 field mismatches for title, year, media type, or genres.
- 5,750 distinct `title_id` values and 5,750 distinct MovieLens IDs.
- 0 null or empty titles.
- 0 orphan rating, watchlist, or interaction rows.

The importer in `backend/scripts/import_colab_bundle.py` reads `title` directly. `backend/app/services/catalogue_service.py` computes a separate `sort_key`; it does not mutate the display title. No migration or enrichment path rewrote these titles.

| Title | MovieLens ID | Serial | Database | API detail | Search | Catalogue |
| --- | ---: | ---: | --- | --- | --- | --- |
| `'burbs, The (1989)` | 2072 | 1306 | Exact | Exact | Exact | Exact |
| `(500) Days of Summer (2009)` | 69757 | 4424 | Exact | Exact | Exact | Exact |
| `*batteries not included (1987)` | 8169 | 3491 | Exact | Exact | Exact | Exact |
| `...And Justice for All (1979)` | 3420 | 2100 | Exact | Exact | Exact | Exact |
| `10 (1979)` | 6658 | 3190 | Exact | Exact | Exact | Exact |
| `10 Cloverfield Lane (2016)` | 152077 | 5310 | Exact | Exact | Exact | Exact |
| `10 Things I Hate About You (1999)` | 2572 | 1639 | Exact | Exact | Exact | Exact |
| `10,000 BC (2008)` | 58293 | 4216 | Exact | Exact | Exact | Exact |
| `101 Dalmatians (1996)` | 1367 | 904 | Exact | Exact | Exact | Exact |
| `101 Dalmatians (One Hundred and One Dalmatians) (1961)` | 2085 | 1316 | Exact | Exact | Exact | Exact |

The API comparison used `/titles/{media_type}/{serial_number}`, `/search`, and `/movies`. Detail responses returned the stored `title_id`; search and catalogue responses returned the same exact title string.

## Frontend repair

`frontend/src/components/media/Poster.tsx` now renders a deterministic typographic poster when artwork is missing. It shows the normalized display title, release year, and primary genre over a dark red-to-amber gradient mesh, with a separate `Artwork unavailable` accessible label. It does not derive initials and it does not append fallback text to the title. The card title remains a separate heading, and its link label contains only the title and year.

This fixes the concatenation at its source without changing provider titles or removing meaningful punctuation.

## Artwork availability

All 5,750 rows have `poster_path = NULL`, and the imported catalogue has no artwork URLs. The API therefore returns `null`, and the frontend correctly renders the typographic poster. This is missing source metadata, not a rendering or serialization bug.

Actual covers require an artwork source with an absolute URL in `poster_path` or `backdrop_path`. The TMDB crawler already normalizes poster and backdrop URLs when credentials and provider matches are available. It cannot invent a cover for a row without matching metadata. Until enrichment is run, the typographic poster is the expected state.

## Visible identity and metadata

The UI does not display `serial_number`, `title_id`, MovieLens IDs, TMDB IDs, or provider source names. Serial numbers remain in canonical routes and API lookups. Provider IDs remain in API responses for integration use.

The API exposes a computed `display_title` that moves a trailing library article to the front, so `Matrix, The (1999)` renders as `The Matrix` while the year is rendered separately. The stored `title` remains unchanged. Cards render only the display title, year, and one genre pill. Title pages separate year and media type from wrapping genre chips. No middle-dot separator is used.

## Tests

Backend regression coverage is in `backend/tests/test_title_integrity.py`:

- exact storage of all reported titles, a numeric title, and a Unicode title;
- sort-key generation does not rewrite titles;
- catalogue, search, and detail endpoints return the same exact title and identity;
- response, recommendation, and history schemas preserve the title.

Frontend regression coverage in `frontend/tests/components.test.tsx` and `frontend/tests/pages.test.tsx` checks:

- every reported title renders exactly as a separate heading;
- missing artwork exposes a separate `Artwork unavailable` accessible label;
- fallback text is not concatenated with the title;
- serial numbers, provider source text, and middle-dot separators are absent from visible metadata;
- genres render as separate links or chips.

## Repair and rollback

No data repair was applied. No `title_id`, provider ID, serial number, rating, watchlist, interaction, or history row was changed. The only changes are presentation behavior, tests, and documentation.

Because there is no data migration, rollback consists of reverting the frontend, schema presentation field, and documentation changes. Do not revert to title-derived poster initials, because that reintroduces the concatenation defect. Do not replace the stored `title` with `display_title`; display normalization must remain presentation-only.
