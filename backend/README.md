# CineRank Backend

CineRank's backend is a FastAPI service. It owns authentication, catalogue data, profile and session management, interactions, watchlists, and the orchestration of the immutable v2 recommendation release. The React frontend consumes the `/api/v1` HTTP contract. It never reads the database or model files directly.

## Architecture and invariants

- `movies.title_id` is the immutable canonical title key. New IDs use `title_<UUIDv7>`.
- `serial_number` is a separate immutable public route identifier.
- `movielens_id`, `tmdb_id` and `imdb_id` are provider identifiers. Provider IDs are mapped to the current database row before any result is returned to the frontend.
- The SQL database is the source of truth for title text, year, genres, overview, artwork, runtime, directors and cast. Missing metadata stays missing until a controlled metadata source fills it.
- The v2 model release is immutable and loaded once per API process. Recommendation routes reject missing or incomplete releases with `503`, while catalogue, search, authentication and profile APIs remain available. Legacy v1 imports must not overwrite the v2 serving release.
- Alembic is the schema authority. `create_all()` is not a migration strategy and startup checks reject stale databases.
- User access JWTs live only in browser memory. The refresh token is opaque, rotated, stored hashed server-side and issued as an HttpOnly cookie.

See the root [`ARCHITECTURE.md`](../ARCHITECTURE.md) for the complete frontend/backend/API/auth/inference/deployment flow.

## Repository map

```text
app/api/          FastAPI routes and auth dependencies
app/core/         Configuration, security, identifiers and limits
app/db/           DB session and schema guard
app/models/       SQLAlchemy entities
app/schemas/      Pydantic API request/response contracts
app/services/     Authentication, catalogue and recommendation services
app/ml/           v2 model release registry and inference adapter
crawler/          TMDB adapter and bounded configured-domain crawler
ranker/           Candidate fusion and final ranking
training/         Offline notebook and model development
scripts/          Catalogue seed, TMDB backfill and maintenance commands
migrations/       Alembic migrations
artifacts/models/releases/ Immutable v2 serving release
 tests/           Backend tests
```

## Local setup

Python 3.11 is recommended for the pinned training/inference stack. `requirements.txt` contains local development and model-training dependencies; `requirements-runtime.txt` is the smaller API/worker image dependency set and deliberately excludes PyTorch, implicit and notebook-only packages.

```bash
cd backend
python -m venv .venv
# Git Bash: source .venv/Scripts/activate
# PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set independent random `SECRET_KEY` and `JWT_SECRET_KEY` values. Never commit `.env`. For a new local SQLite database:

```bash
python -m alembic upgrade head
python scripts/import_catalogue_seed.py --apply
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

For an existing database, back it up and run the Alembic upgrade. Do not delete the database to repair a missing column:

```bash
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
```

Current Alembic head: `d0e1f2a3b4c5`. The migration graph merges the avatar URL and title serial-number branches, enforces non-null serial numbers, adds recommendation preferences, adds email verification plus single-use action tokens, and binds those tokens to the verified address on SQLite and PostgreSQL. The schema guard gives an actionable error if the DB is older than the application models. Redis is used for distributed rate limiting and recommendation caching; production requires `REDIS_URL`.

Email confirmation and password reset require `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`, credentials when the server requires them, and `FRONTEND_BASE_URL` for link generation. Tokens are stored only as SHA-256 hashes and are single-use. The email routes return `503` when SMTP is not configured. Automated tests inject a fake sender; real delivery is not exercised without provider credentials.

## Model serving

The active release is `artifacts/models/releases/`. It is versioned by `manifest.json` and protected by `SHA256SUMS`. The API loads it through `app/ml/release_registry.py`, verifies the file hashes, warms the inference engine and exposes readiness only when the bundle is valid. Install all pinned dependencies including `onnxruntime` before expecting the API to become ready.

Do not point the v1 importer or notebook exporter at the v2 release directory. The scheduled worker intentionally does not perform automatic model promotion. Release upgrades require a new immutable candidate, temporal offline evaluation, checksum/shape/parity checks and explicit activation. See the root architecture document and `docs/ml/algorithms.md`.

## Catalogue metadata

`data/seeds/catalogue_movielens.jsonl` is a privacy-sanitized seed with 5,750 title records. Overviews, directors, cast, artwork, runtime, genres, votes and provider IDs are populated from a downloaded TMDB/IMDb dump with exact MovieLens TMDB-ID matching; see [`docs/operations/catalogue_metadata.md`](docs/operations/catalogue_metadata.md). It does not contain users, password hashes, ratings, sessions or interaction history. `scripts/import_catalogue_seed.py` is dry-run by default, only imports into an empty catalogue, and is idempotent for the exact seed.

MovieLens titles commonly lack overviews, TMDB IDs, artwork and credits. `scripts/backfill_tmdb_metadata.py` is a controlled TMDB enrichment path:

```bash
# Configure TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY in backend/.env.
python scripts/backfill_tmdb_metadata.py --limit 100       # dry-run
python scripts/backfill_tmdb_metadata.py --limit 100 --apply
```

For Docker deployments, invoke the maintenance command through the worker service, which has outbound network access.

The command rejects ambiguous title/year matches and fills missing values only unless `--overwrite-existing` is explicitly selected. No TMDB key or external results are included in the repository. Follow TMDB API and attribution terms.

## Logging

The API and worker use `app/core/logging_config.py`. Terminal output is a single aligned line per event, while `logs/cinerank.log` receives rotating JSON lines with timestamp, level, logger, message and structured request fields. Uvicorn access logging is disabled because the application middleware already records method, path, status, latency and request ID, so request rows are not duplicated.

```bash
python scripts/show_logs.py --tail 100
python scripts/show_logs.py --level WARNING
python scripts/show_logs.py --request-id <id>
python scripts/show_logs.py --follow
```

Use `LOG_FILE_ENABLED=false` for console-only development. `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT` control rotation. Docker Compose stores the file in the shared `cinerank-logs` volume at `/app/logs`.

## Run the worker

```bash
python -m app.worker
```

The worker runs the daily catalogue sync at 12:00 UTC using database-backed leases. The active model is not retrained or promoted by the worker because the legacy v1 trainer is not compatible with the v2 serving release. TMDB synchronization requires outbound network access. In Docker Compose, only the worker receives the dedicated egress network.

## Docker

Use the repository root `Dockerfile` and `docker-compose.yml` as the canonical deployment. The old backend-only Compose layout has been removed to avoid two conflicting deployment definitions. Root Compose runs PostgreSQL, Alembic migration, safe catalogue bootstrap, API, worker and Nginx frontend. The root `python cinerank.py` launcher starts the entire stack from Windows, macOS or Linux; see root README for local setup and production TLS requirements.

## Tests

```bash
python -m compileall -q app scripts
pytest -q
```

The backend test suite uses isolated databases for unit/integration behavior. A pass does not replace production PostgreSQL migration testing, multi-process rate-limit/load tests, exact ONNX runtime validation, a security review, crawler-policy review or browser E2E.

## External data and licensing

MovieLens data is governed by GroupLens terms. TMDB text and artwork are subject to TMDB terms and attribution requirements. Respect source-site terms, robots rules, rate limits, copyright and applicable law when enabling external metadata discovery. Do not infer a repository license if no `LICENSE` file is present.
