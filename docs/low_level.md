# CineRank - Low Level System Documentation

## Database Schema

### Movie Entity

| Field | Type | Description |
|-------|------|-------------|
| `title_id` | UUID (String, 42 chars) | Sole durable internal identifier |
| `serial_number` | Integer (6 digits) | Permanent public URL identifier |
| `media_type` | String ("movie" or "tv") | distinguishes movies from TV shows |
| `title` | String | Original title as provided by data source |
| `original_title` | String (nullable) | Original title before localization |
| `sort_key` | String | Format: "Title (Year)" for display ordering |
| `year` | Integer (nullable) | Release year |
| `overview` | Text | Plot summary |
| `vote_average` | Float | Average rating (0-10) |
| `vote_count` | Integer | Number of ratings |
| `runtime` | Integer (nullable) | Duration in minutes |
| `popularity` | Float | Popularity score |
| `genres` | String (pipe-separated) | e.g., "Action|Adventure|Science Fiction" |
| `tmdb_id` | Integer (nullable) | TMDB identifier |
| `imdb_id` | String (tt####### format) | IMDB identifier |
| `poster_path` | String (nullable) | TMDB poster path |
| `backdrop_path` | String (nullable) | TMDB backdrop path |
| `budget` | Float (nullable) | Production budget |
| `revenue` | Float (nullable) | Box office revenue |
| `directors_json` | Text (JSON string) | List of directors |
| `cast_json` | Text (JSON string) | List of main cast |
| `is_adult` | Boolean | Flag for adult content |
| `source` | String | Data source identifier |
| `source_domain` | String (nullable) | Source domain name |
| `source_url` | String (nullable) | Source URL |
| `source_url_hash` | String (nullable, unique) | Hash of source URL |
| `source_metadata_json` | Text (nullable) | Additional source metadata |
| `created_at` | DateTime | Server default: now() |
| `updated_at` | DateTime | Server default: now(), onupdate: now() |

### User Entity

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `email` | String (unique) | User email address |
| `password_hash` | String | Argon2id hash |
| `full_name` | String (nullable) | Display name |
| `preferences_json` | Text | JSON-encoded user preferences |
| `created_at` | DateTime | Server default: now() |
| `updated_at` | DateTime | Server default: now(), onupdate: now() |

### Watchlist Entity

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key to users |
| `title_id` | UUID | Foreign key to movies |
| `created_at` | DateTime | When added to watchlist |

### Rating Entity

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key to users |
| `title_id` | UUID | Foreign key to movies |
| `rating` | Integer (1-10) | User rating |
| `created_at` | DateTime | Server default: now() |

### Title Serial Number Sequence

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Sequence identifier (always 1) |
| `next_value` | Integer | Next available serial number |

## API Endpoints

### Authentication

#### `POST /api/v1/auth/token`

- **Method**: POST
- **Content-Type**: `application/x-www-form-urlencoded`
- **Params**: `username`, `password`
- **Success**: `200` with bearer token
- **Failure**: `401` with error detail

#### `GET /api/v1/auth/me`

- **Method**: GET
- **Auth**: Bearer token
- **Success**: `200` with user object
- **Failure**: `401` unauthenticated

### Catalogue

#### `GET /api/v1/home/{user_id}`

- **Method**: GET
- **Auth**: Bearer token required
- **Response**:
  ```json
  {
    "for_you": [{title_id, title}, ...],
    "popular": [{title_id, title}, ...],
    "genres": ["Action", "Adventure", ...],
    "next_cursor": "opaque_signed_cursor",
    "model": "ranking_model_name",
    "generated_at": "ISO_timestamp"
  }
  ```
- **409 Handling**: If sort version changed, reset to page 1 preserving filters

#### `GET /api/v1/watchlist`

- **Method**: GET
- **Auth**: Bearer token required
- **Response**: `[{created_at, title}, ...]` - bare array

#### `GET /api/v1/users/{user_id}/history`

- **Method**: GET
- **Auth**: Bearer token required
- **Response**: User ratings only (not playback history)

#### `GET /api/v1/recommendations`

- **Method**: GET
- **Auth**: Bearer token required
- **Response**: Ranked list of titles with ranking reasons

### User Preferences

#### `GET /api/v1/users/me/preferences`

- **Method**: GET
- **Auth**: Bearer token required
- **Response**:
  ```json
  {
    "preferred_genres": ["Action", "Sci-Fi"],
    "excluded_genres": ["Documentary"],
    "include_adult": false,
    "minimum_year": 1900,
    "maximum_runtime": 300
  }
  ```

#### `PUT /api/v1/users/me/preferences`

- **Method**: PUT
- **Auth**: Bearer token required
- **Same fields as GET**

### Watchlist Mutations

#### `POST /api/v1/watchlist`

- **Method**: POST
- **Auth**: Bearer token required
- **Body**: `{title_id}`
- **Success**: `201` with created watchlist entry
- **Error**: `409` if sort version changed, `401` if unauthenticated

#### `DELETE /api/v1/watchlist/{title_id}`

- **Method**: DELETE
- **Auth**: Bearer token required
- **Success**: `204` No Content

### Error Handling

#### `409 Conflict` (Version Conflict)

- **Meaning**: The sort version changed
- **Action**: Reset to page 1 while preserving active filters
- **Client**: Should refetch first page

#### `401 Unauthorized`

- **Meaning**: Missing or invalid bearer token
- **Action**: Redirect to login, clear session

#### Defensive Parsing

- **genres**: Delimited string, not JSON - parse with `split("|")`
- **directors_json**: JSON string - parse defensively, tolerate malformed values
- **cast_json**: JSON string - parse defensively, tolerate malformed values

## Data Import

### Import Scripts

All import scripts are located in `backend/scripts/` and are idempotent:

1. `import_catalogue_seed.py` - Imports 5,750 seed titles from MovieLens
2. `import_all_data.py` - Imports all external data sources
3. `import_data.py` - Imports 9000plus.csv and imdb-media.csv
4. `import_external.py` - Alternative import script

### Import Process

1. **Read external data files** from `backend/data/external/`
2. **Generate title_id** using hash-based approach from title + year
3. **Check for duplicates** - skip titles already in database
4. **Insert new movies** - serial numbers auto-allocated by trigger
5. **Commit in batches** - 5000 records per commit for performance

### Data Source Formats

#### CSV Files

- **9000plus.csv**: Columns: Release_Date, Title, Overview, Popularity, Vote_Count, Vote_Average, Original_Language, Genre, Poster_Url
- **IMDB Dataset.csv**: Columns include title, rating, runtime, etc.
- **TMDB-IMDB-Movies-Dataset.csv**: Merged identifiers and metadata

#### Parquet Files

- **tv-details.parquet**: 214K TV show records with columns: name, first_air_date, genres, popularity, etc.

#### JSON Files

- **tvmaze/*.json**: TVMaze API response format with name, genres, summary, premiered, etc.

### Serial Number Allocation

- **Format**: 6-digit zero-padded (e.g., "000001")
- **Mechanism**: Transactional counter in `title_serial_sequence` table
- **SQLite**: `INSERT OR IGNORE + UPDATE` pattern
- **PostgreSQL**: `INSERT ... ON CONFLICT ... DO NOTHING` + `FOR UPDATE` locking

## Frontend-Backend Connectivity

### API Client

- **Base URL**: `VITE_API_BASE_URL` (configured as `/api/v1`)
- **Authentication**: Bearer token from `useAuth()` hook
- **Form Login**: `POST /auth/token` with form-encoded data
- **Timeout**: Configurable timeout with cancellation support

### TanStack Query

- **Queries**: `useQuery` for fetching data with automatic caching
- **Mutations**: `useMutation` for creating/updating data
- **Cache Invalidation**: Automatic on related queries
- **Refetching**: Background refetch on window focus, interval-based

### Error States

- **Loading**: Skeleton indicators during data fetch
- **Error**: Calm error messages without architecture leaks
- **Empty**: Styled empty states with action buttons
- **Success**: Conf
