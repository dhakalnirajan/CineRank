# CineRank

<p align="center">
    <img src="./icon.png" alt="CineRank logo" />
</p>

CineRank is a movie and television discovery application backed by a FastAPI catalogue and a versioned recommendation-serving layer. The frontend is a React, TypeScript and Vite single-page application. The supported deployment is a set of separate containers built from the repository's root `Dockerfile`: Nginx frontend, FastAPI API, background worker, one-shot Alembic migrator and PostgreSQL.


## Repository layout

```text
CineRank/
├── AGENTS.md
├── ARCHITECTURE.md
├── IMPLEMENTATION_STATUS.md   Implemented scope, verification and remaining deployment work
├── PRODUCTION_READINESS.md   Executed checks, load results, blockers and residual risks
├── Dockerfile                 Multi-target production image definition
├── docker-compose.yml         Canonical local/production starting point
├── cinerank.py                Cross-platform full-stack launcher
├── .env.example               Runtime variable template, no real secrets
├── deploy/nginx.conf          Same-origin API/media proxy and SPA fallback
├── backend/
│   ├── app/                   FastAPI routes, auth, DB, inference, services
│   ├── artifacts/models/releases/ Immutable v2 model release and checksums
│   ├── crawler/                Bounded TMDB and configured metadata crawler
│   ├── data/seeds/             Privacy-sanitized catalogue bootstrap seed
│   ├── migrations/             Alembic schema history
│   ├── scripts/                Safe bootstrap, seed import, TMDB backfill and maintenance
│   ├── requirements-runtime.txt Slim API/worker container dependencies
│   ├── training/               Offline training and model development
│   └── tests/                  Backend tests
└── frontend/
    ├── src/                    React pages, API client, auth and components
    ├── tests/                  Frontend unit/component tests
    └── DESIGN.md               UI system and interaction decisions
```

## Capabilities

- Catalogue, title detail, search, genre facets, ratings, interaction history and watchlist are served from the backend database.
- User profiles support username, email and password updates, profile-photo upload, active-session listing and session revocation. Passwords use Argon2id; existing scrypt hashes are upgraded after successful login.
- Email confirmation and password reset use single-use hashed links delivered through configured SMTP. Password reset revokes all sessions, and changed email addresses become unverified.
- Users can set preferred/excluded genres, adult-content inclusion, minimum release year and maximum runtime. The recommendation service applies those preferences during candidate selection.
- Redis provides distributed IP/user/account rate limits and short-lived personalized recommendation caching. PostgreSQL remains authoritative.
- Browser access JWTs are held in memory. Refresh credentials are opaque, rotated, hashed in the database, and delivered through an HttpOnly cookie.
- The home feed includes personalized `for_you`, catalogue popularity, recently added titles and genre rows. Interaction and rating changes invalidate the user's recommendation cache.
- Inference returns provider item IDs and ranking scores only. The API resolves each provider ID to the canonical `Movie` database row and returns the complete available catalogue record: canonical/public IDs, title/original title, separate year, genres, overview, poster/backdrop, runtime, ratings/counts, directors, cast, adult-content flag, source IDs and ranking metadata. The frontend does not trust model output as movie metadata or perform a second title lookup for the home hero.
- Navbar search queries the catalogue API and opens an accessible result dialog with loading, empty and error states.
- A 2.8-second, once-per-session red-ribbon intro resolves the mark before the CineRank wordmark. Branded page loaders and skeleton states follow it.
- Movie display titles are normalized independently of the raw stored title. Release year remains separate metadata and is not appended to the visible title.
- Catalogue metadata can be populated from a downloaded TMDB/IMDb dump using exact MovieLens TMDB links, with conservative unique title/year fallback. The importer fills overviews, directors, cast, artwork, runtime, genres, votes and provider IDs without creating duplicate titles. See `backend/docs/operations/catalogue_metadata.md`.
- API request logs include request ID, method, route, status and latency. Tokens, cookies, query values and request bodies are not logged. Terminal output is aligned and single-line; `backend/logs/cinerank.log` keeps rotating JSON lines for filtering and debugging. Use `cd backend && python scripts/show_logs.py --tail 100` to read it.

## Local development

### Backend

```bash
cd backend
python -m venv .venv
# Windows Git Bash: source .venv/Scripts/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt  # runtime only
# Full test suite and legacy portable-model tests:
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -m alembic upgrade head
python scripts/import_catalogue_seed.py --apply
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Set `SECRET_KEY` and `JWT_SECRET_KEY` to independent random values in `backend/.env`. For production Compose, also set strong independent `POSTGRES_PASSWORD` and `REDIS_PASSWORD` values in the root `.env`. The sample values are placeholders. A fresh DB needs Alembic migrations and the sanitized catalogue seed. Existing databases should be upgraded in place. Never delete the database to fix a missing column.

### Frontend

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000/api/v1` in `frontend/.env`. Vite values are public browser configuration. Never place database credentials, TMDB credentials or token-signing keys in a `VITE_` variable.

### Existing SQLite database migration

Run these commands from `backend/` after taking a normal file backup:

```bash
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
```

The current single head is `d0e1f2a3b4c5`. The migration chain merges the avatar URL and permanent title serial-number branches, enforces non-null serial numbers, adds user recommendation preferences, adds email verification plus single-use action tokens, and binds verification tokens to the address they were issued for on SQLite as well as PostgreSQL. These migrations preserve users, ratings, watchlists and interaction history. The startup schema guard intentionally fails with a migration instruction instead of silently attempting `create_all()`.

## Docker deployment

The root Dockerfile contains independent `api` and `web` targets. The API target installs a minimal runtime dependency set for FastAPI, PostgreSQL, the TMDB worker and ONNX inference; notebook/training dependencies such as PyTorch, implicit and pandas are kept out of the production API image. Compose also runs PostgreSQL, Redis, a one-shot Alembic migration, a safe catalogue bootstrap, FastAPI, a worker and Nginx. Redis provides shared rate limits and short-lived recommendation caching; PostgreSQL remains authoritative. Nginx serves the production frontend build and proxies `/api/v1/` and `/media/` to FastAPI on the same origin. Its DNS-aware upstream balances across stateless API replicas; use `docker compose up -d --scale api=3` when capacity warrants it.

For local development, the root launcher is the single entry point on Windows, macOS and Linux. It creates a local `.env` with independent random secrets when none exists, validates Compose configuration, builds the images, runs migrations and safe catalogue bootstrap, then starts the whole stack:

```bash
python cinerank.py
```

Open `http://localhost:8080`. Optional monitoring can be started with `docker compose --profile monitoring up -d prometheus grafana`. Prometheus is available on `http://localhost:9090` and Grafana on `http://localhost:3001` (username `admin`, password from `GRAFANA_ADMIN_PASSWORD` in `.env`). API metrics are scraped over the private Docker network; `/metrics` is not exposed through Nginx.

Useful commands are:

```bash
python cinerank.py status
python cinerank.py logs
python cinerank.py logs api
python cinerank.py rebuild
python cinerank.py down
```

`down` preserves named PostgreSQL and media volumes. It does not delete application data. The default local environment uses HTTP-compatible cookies for localhost only. Do not expose that mode to the public internet.

For production, configure the root `.env` from `.env.example` with independent strong secrets, `ENVIRONMENT=production`, `AUTH_COOKIE_SECURE=true`, a real HTTPS origin, explicit `CORS_ORIGINS`, a production database password, `FRONTEND_BASE_URL`, and SMTP sender credentials for verification and password reset. The application reports `503` on those email routes when SMTP is not configured. Then run `docker compose config` and `docker compose up --build -d` behind a TLS-terminating ingress. Never commit `.env`.

On an empty database, `catalogue-bootstrap` imports the bundled sanitized 5,750-title seed after migrations. On an unrelated already-populated production catalogue, it skips the seed rather than overwriting existing titles. A partial collision with the seed fails startup for manual review. The standalone `scripts/import_catalogue_seed.py` remains dry-run by default. The API healthcheck uses liveness rather than model readiness, so login, profile, search and catalogue APIs can start even while a model release is being repaired; recommendation endpoints independently return `503` until a validated release is ready.

The API and PostgreSQL are not published directly to the host. Nginx is the public entry point. The database network is internal; the worker additionally has outbound egress for scheduled metadata synchronization. User uploads and PostgreSQL data use named volumes. The image runs application processes as a non-root user.

For a public production deployment, terminate TLS at a managed load balancer or a hardened HTTPS ingress in front of the web container. Set `AUTH_COOKIE_SECURE=true`, explicit `CORS_ORIGINS`, strong independent secrets and a production domain. Configure backups, monitoring, log retention, resource limits and an external secret manager. The included Compose file is a production-oriented baseline, not a replacement for an environment-specific infrastructure review.

## Catalogue metadata backfill

The handoff intentionally excludes the local live SQLite database, user accounts, password hashes, ratings, watchlists, sessions, request logs and private training-run directories. The source catalogue seed contains 5,750 catalogue records with their stable CineRank IDs and available provider mappings; it excludes user and behavioral data. Many MovieLens titles do not include overview, poster, director, cast or TMDB IDs, so those fields remain nullable until enriched.

Configure `TMDB_READ_ACCESS_TOKEN` or `TMDB_API_KEY` in the root `.env` when using Docker, or in `backend/.env` for direct local backend development. Inspect candidates without writing:

```bash
cd backend
python scripts/backfill_tmdb_metadata.py --limit 100
```

Only after reviewing the dry-run output, apply a small batch:

```bash
python scripts/backfill_tmdb_metadata.py --limit 100 --apply
```

With Docker Compose, the worker has outbound TMDB access. Run the same command through the root launcher:

```bash
python cinerank.py backfill --limit 100
python cinerank.py backfill --limit 100 --apply
```

The command uses direct TMDB IDs where present. Otherwise it uses normalized title/year matching, a strict similarity threshold and ambiguity rejection. It fills missing metadata by default and does not overwrite existing fields. Use `--overwrite-existing` only as a separate, reviewed maintenance operation. Respect TMDB attribution, image and API terms. The repository does not ship a TMDB key and no real TMDB backfill is performed during build.

## Verification

Executed in this workspace: 79 backend tests passed with 2 live-Redis tests skipped, a fresh SQLite migration reached `d0e1f2a3b4c5`, `alembic check` reported no drift, all 87 frontend tests passed, and typecheck, lint and production build passed. Both `pip-audit -r backend/requirements-runtime.txt` and `npm audit` reported no known vulnerabilities.

Backend checks:

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m compileall -q app scripts crawler ranker
python -m alembic upgrade head
python -m alembic check
pytest -q
```

Live Redis integration checks run only with an explicit disposable Redis URL:

```bash
CINERANK_TEST_REDIS_URL=redis://127.0.0.1:6379/15 pytest tests/test_redis_integration.py -q
```

Frontend checks:

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npm audit --omit=dev --audit-level=high
```

Local load smoke:

```bash
cd backend
./.venv/Scripts/python.exe scripts/load_smoke.py --spawn --duration 8 --endpoint-concurrency 2
```

Also run `docker compose config`, build both Docker targets, verify `/api/v1/health/ready`, sign in, test refresh rotation and session revocation, and exercise a recommendation request against the exact deployed model runtime before release. A green unit suite is not an end-to-end production sign-off. See `PRODUCTION_READINESS.md` for the full executed matrix and blockers.

## Known operational constraints

- The included v2 model release is immutable and checksum-verified. The current worker deliberately does not promote bundles from the legacy v1 trainer. Model upgrades require offline temporal evaluation, artifact validation and controlled deployment.
- Docker CLI was unavailable in this execution environment, so Docker image builds, Compose startup, Nginx 1.28 routing, replica balancing and the backup restore drill were not executed. Compose and provisioning YAML were parsed, and the backup/restore scripts were syntax-checked only.
- PostgreSQL and Redis services were unavailable locally. PostgreSQL migration validation and live Redis integration are defined as CI jobs but were not executed in this workspace. The PostgreSQL migration job has not run yet.
- Recommendation p99 latency and cold start were measured only on one local SQLite process. An earlier local run showed approximately 13 second cold-start responses and timeouts under concentrated load. Profile against PostgreSQL and multiple replicas before release.
- Email verification and password reset are implemented, but real delivery was not tested because no SMTP provider, credentials or sender domain were configured.
- Prometheus now exposes recommendation, cache, inference, database and Redis metrics, with alert rules and dashboard panels. No running Prometheus or Grafana instance evaluated them here. A persistent audit-log export remains outstanding.
- The provisioned Grafana dashboard renders only after the optional monitoring profile is started with Docker. Its runtime rendering was not verified here.
- No browser end-to-end, accessibility audit, formal penetration test or production-scale load test was performed.
- Browser autoplay policy can block intro audio until the user has interacted with the page. Sound is enabled by default in the intro code, but browser policy has the final say.
- There is no media playback or streaming service. Interaction events are recommendation signals, not actual video playback.

## Documentation

- `ARCHITECTURE.md`: end-to-end system architecture and runtime request flows.
- `PRODUCTION_READINESS.md`: executed test matrix, local load results, blockers and residual risks.
- `IMPLEMENTATION_STATUS.md`: implemented scope versus unverified or blocked work.
- `frontend/DESIGN.md`: visual system, component rules, poster motion, intro and loaders.
- `backend/README.md`: backend development, migrations, model serving and security.
- `backend/docs/`: API, database, ML and operational details.
- `deploy/BACKUP_RESTORE.md`: backup, restore and recovery drill procedure.
- `AGENTS.md`: codebase conventions and agent-facing maintenance instructions.
