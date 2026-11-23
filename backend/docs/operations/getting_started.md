# Operations Guide

## Process model

Run the API and scheduler as separate processes/containers. The root Compose file is the canonical deployment and runs PostgreSQL, a one-shot Alembic migrator, API, worker and Nginx frontend. Do not use an old backend-only Compose file or let multiple schedulers bypass the database lease.

## Configuration

The exact settings and defaults live in `app/core/config.py`. Keep production secrets outside source control. `SECRET_KEY` and `JWT_SECRET_KEY` must be long, random and independent. Production validation requires a 5 to 15 minute access JWT, Secure and HttpOnly refresh cookie, valid SameSite setting, explicit CORS origins and `REDIS_URL`. Redis is required for shared rate limiting and short-lived response caching. Set a strong `REDIS_PASSWORD` in the root `.env`; the Redis service is private to the internal backend network and has no published host port. `REFRESH_TOKEN_EXPIRE_DAYS` defaults to 30 days and represents a sliding inactivity expiry on successful refresh.

`MODEL_RELEASE_DIR` points to the immutable v2 release directory. `MODEL_INFERENCE_CACHE_SIZE` bounds the inference cache. `TMDB_API_KEY` or `TMDB_READ_ACCESS_TOKEN` enables metadata access. The Compose worker receives outbound egress for scheduled TMDB calls; the API and database remain on the internal service network. `AUTO_CREATE_SCHEMA` must remain false.

## Existing database migration

Back up the database and apply Alembic migrations:

```bash
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
```

The current Alembic head is `d0e1f2a3b4c5`. It merges the profile-avatar and public-serial branches, enforces non-null serial numbers on SQLite and PostgreSQL, adds explicit user preferences, adds email verification plus single-use action tokens, and binds those tokens to the verified address. If the API reports `no such column: users.avatar_url`, the database is behind the ORM schema. Do not delete the database and do not attempt to repair it with `create_all()`. Run the Alembic upgrade.

## Fresh catalogue bootstrap

The project ships a privacy-sanitized JSONL seed with 5,750 catalogue rows and no user accounts or behavioral records. After applying migrations, run:

```bash
python scripts/import_catalogue_seed.py           # dry-run
python scripts/import_catalogue_seed.py --apply
```

The importer inserts only into an empty catalogue, refuses partial/unrelated data and succeeds idempotently if the same exact seed is already present. Do not use it to overwrite an existing production catalogue.

## Model readiness

The API reads and verifies the v2 release once on startup. Inspect:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/models
curl -fsS http://127.0.0.1:8000/api/v1/health/ready
```

`/health/live` is process liveness. `/health/ready` requires database connectivity, Redis connectivity when `REDIS_URL` is configured, and a validated inference bundle. A missing bundle or missing runtime dependency such as ONNX Runtime results in 503 readiness and recommendation responses. This is intentional fail-closed behavior.

The v2 bundle is under `artifacts/models/releases/` with `manifest.json` and `SHA256SUMS`. Check hashes with `sha256sum -c SHA256SUMS` from that directory. The old v1 importer/trainer is not a release activation mechanism for v2.

## Metadata enrichment

For controlled enrichment, configure TMDB credentials then inspect a dry run:

```bash
python scripts/backfill_tmdb_metadata.py --limit 100
python scripts/backfill_tmdb_metadata.py --limit 100 --apply
```

The command prioritizes existing TMDB IDs; otherwise it applies conservative normalized title/year matching and skips ambiguous matches. Existing fields are retained unless `--overwrite-existing` is supplied. Use small limits, inspect logs and comply with TMDB attribution and usage terms.

## Worker semantics

The worker checks for the daily catalogue sync at 12:00 UTC. It acquires a database lease, runs configured catalogue synchronization, rebuilds the sort index and records success/failure. It does not train or promote a new recommendation model. V2 releases are trained and validated offline, then deployed as immutable artifacts. This prevents the legacy v1 trainer from overwriting the active v2 bundle.

The worker needs outbound access to TMDB. In Docker Compose it is attached to the internal backend database network and a separate egress network. The PostgreSQL service is not published to the host.

## Logs

Each API request receives a request ID. Console output uses aligned one-line records. The rotating JSON-lines file at `LOG_DIR/cinerank.log` records timestamp, level, logger, event, request ID, method, path, status, duration and traceback when present. Query strings, credentials, cookies and request bodies are excluded. Include the response `X-Request-ID` when investigating a user-visible error.

```bash
cd backend
python scripts/show_logs.py --tail 100
python scripts/show_logs.py --level WARNING
python scripts/show_logs.py --request-id <id>
python scripts/show_logs.py --follow
```

`LOG_FILE_ENABLED=false` disables the file while keeping console output. `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT` control rotation. In Docker Compose the file is stored in the shared `cinerank-logs` volume at `/app/logs`. Configure central log collection, retention and alerting in the deployment environment.

## Docker

Use root `Dockerfile`, `docker-compose.yml` and `.env.example`. Root README contains the startup sequence. The public HTTP entry point is the web/Nginx container; put a TLS-terminating ingress or managed load balancer in front of it for public use. Nginx uses round-robin DNS-aware upstream balancing across API replicas. Scale the stateless API with `docker compose up -d --scale api=3`; no sticky sessions are needed because sessions are stored in PostgreSQL and rate limits/cache are shared through Redis. Before scaling, budget `SQL_POOL_SIZE` plus `SQL_MAX_OVERFLOW` for every API process and worker against PostgreSQL `max_connections`.

The API exposes Prometheus HTTP metrics at `/metrics` only on the private container network. Nginx denies public access. Start optional local monitoring with `docker compose --profile monitoring up -d prometheus grafana`; Prometheus is bound to `127.0.0.1:9090` and Grafana to `127.0.0.1:3001`. Set a unique `GRAFANA_ADMIN_PASSWORD` in `.env`. The Compose setup is a baseline, not a complete high-availability or disaster-recovery design.

## Remaining operational checks

Before production cutover, verify PostgreSQL migrations, backup/restore, exact ONNX runtime inference, auth refresh rotation in multiple tabs, session revocation, profile/avatar uploads, metadata search and backfill, recommendation latency, concurrency, log collection, HTTPS cookie behavior and browser end-to-end flows. Current project unit tests do not replace those environment-specific checks.

## Initial rate-limit policy

The initial Redis-backed quotas are login 5/minute per IP and account, registration 5/hour per IP and username, refresh 10/minute, search 30/minute, recommendations/home 20/minute, ratings 20/minute, watchlist writes 30/minute, interactions 60/minute and other public reads 240/minute. These are tunable safety defaults, not capacity guarantees. Watch 429 rates and tune with real traffic.
