# Catalogue Metadata Enrichment

CineRank stores overviews, directors, cast, artwork, runtime, ratings and provider IDs in the existing `movies` table. The catalogue remains keyed by immutable `title_id`; enrichment never rewrites title identity, serial numbers, raw provider titles or user data.

## Sources

| Source | File | Purpose |
| --- | --- | --- |
| GroupLens MovieLens latest-small | `ml-latest-small.zip` from `https://files.grouplens.org/datasets/movielens/ml-latest-small.zip` | Authoritative `movieId` to TMDB ID links |
| Hugging Face `HenryWaltson/TMDB-IMDB-Movies-Dataset` | `TMDB  IMDB Movies Dataset.csv` | Overview, directors, cast, artwork, runtime, genres, votes, TMDB ID and IMDb ID |

The downloaded copies are stored under `backend/data/external/`, which is excluded from version control. Recorded checksums for this pass:

```text
TMDB-IMDB-Movies-Dataset.csv 277738301 bytes
sha256 da825d814096de90374cc7e10c4c8ad0911baee0b01e420d5f57ff2184e48a25

ml-latest-small.zip 978202 bytes
sha256 696d65a3dfceac7c45750ad32df2c259311949efec81f0f144fdfb91ebc9e436
```

Review the original dataset and MovieLens terms before redistributing either file. The external dump is not part of the application image or repository. TMDB-derived metadata should retain the attribution required by the source terms.

## Matching and duplicate policy

1. Match by exact TMDB ID from MovieLens `links.csv` first.
2. Reject an exact link when both release years differ by more than three years. This catches stale links that point to a different film.
3. For unlinked or rejected rows, accept only one normalized title plus exact release year and exactly one dataset candidate. Ambiguous candidates are skipped.
4. Deduplicate dataset rows by TMDB ID, keeping the row with the most populated metadata fields.
5. Never create a second catalogue row for an existing title. The importer enriches existing rows only.
6. A dataset TMDB ID is assigned to one catalogue row. If duplicate ownership is detected, the row is not applied.

One legitimate same-title/year pair remains in the catalogue: the 2005 films `War of the Worlds` with TMDB IDs 74 and 34812. They are distinct films with separate IMDb records, so they are not data duplicates.

## Fields written

- `overview`
- `directors_json` as `[{"name": "...", "job": "Director"}]`
- `cast_json` as up to 12 `{"name": "...", "character": null}` entries
- `poster_path` and `backdrop_path` as HTTPS TMDB image URLs
- `runtime`, `genres`, `vote_average`, `vote_count`, `popularity`
- `tmdb_id` and `imdb_id`

`genres`, title text and identities already present in the MovieLens seed are not changed unless `--overwrite-existing` is explicitly passed. The default run fills only empty fields.

## Commands

From `backend/`:

```bash
# Download both public sources into data/external/
python scripts/import_catalogue_metadata.py --download

# Inspect matches without writing
python scripts/import_catalogue_metadata.py

# Apply missing metadata
python scripts/import_catalogue_metadata.py --apply

# Repair or replace populated fields from the same verified sources
python scripts/import_catalogue_metadata.py --apply --overwrite-existing
```

The command writes `data/external/metadata-import-report.json` with match counts and field totals.

## Result of the 2026-11-23 pass

| Metric | Result |
| --- | ---: |
| Catalogue rows | 5,750 |
| Dataset rows scanned | 434,803 |
| MovieLens TMDB links | 5,369 |
| Exact TMDB-ID matches accepted | 5,343 |
| Unique title/year fallback matches | 314 |
| Ambiguous fallbacks skipped | 12 |
| Rows enriched | 5,657 |
| Rows still without overview | 93 |
| Duplicate TMDB owners | 0 |
| Overviews stored | 5,657 |
| Directors stored | 5,657 |
| Cast stored | 5,650 |
| Posters stored | 5,655 |
| Backdrops stored | 5,646 |

The unmatched remainder has no reliable TMDB or unique title/year match in the downloaded sources. They are left empty rather than filled with guessed metadata.

## Frontend presentation

The existing title page already reads the verified response fields and renders:

- Overview text, with an explicit empty state.
- Direction names from `directors_json`.
- Up to 12 cast names from `cast_json`.
- External rating and vote count, release year, runtime and media type.
- Poster and backdrop with the existing typographic artwork fallback.

No second metadata request and no client-side enrichment are performed. The API remains the source of truth.
