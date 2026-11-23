# CineRank Production Readiness Report

Date: 2026-11-23
Workspace: local Windows development copy
Scope: source, tests, migrations, CI, deployment assets and local runtime

This report records what was executed. Anything requiring Docker, Redis, PostgreSQL, a browser, a mail provider or a public deployment is marked blocked, not passed. No production certificate, penetration test or capacity guarantee is claimed.

## Resolved in this pass

- Preferences controls had duplicate accessible names for prefer/exclude states. They are now `Prefer <genre>` and `Exclude <genre>`, and the test waits deterministically for persisted state.
- `backend/requirements.txt` was a stale Python 3.14 freeze and `requirements-dev.txt` omitted required test dependencies. Runtime and dev manifests are now layered and consistent.
- Runtime Pillow was capped below the patched major. The constraint is now `Pillow>=13.0,<14.0`.
- `alembic check` reported model/database default drift for `user_preferences`. The ORM now declares the server defaults already created by the existing migration.
- Added cross-user regression tests for watchlist isolation and preference isolation.
- Added real Redis integration tests, PostgreSQL migration CI, Redis service CI and dependency-scan CI.
- Added checksummed PostgreSQL backup/restore scripts with a documented restore drill.
- Added a provisioned Grafana API dashboard for the HTTP metrics that exist.
- Upgraded Vitest to 5.1.1 to remove critical dev-only advisories. All 87 frontend tests still pass.
- Added an API load smoke harness with real percentile output.
- Replaced the For You rank overlay and oversized feedback buttons with a compact feedback footer and separated year/genre metadata.
- Added deterministic irregular 3-10 sided polygon posters, four translucent layers, faster drift, inner morphing and screen blending for merge/separation.
- Added Prometheus metrics for recommendation duration and cache outcomes, shared and memory cache events, inference/ranking duration, item counts, Redis operation failures and database health/readiness failures.
- Added `deploy/prometheus-alerts.yml`, wired it into Prometheus and Compose, and expanded the Grafana dashboard with recommendation cache, latency, inference, Redis and database panels.
- Implemented email verification and password reset with SHA-256-hashed single-use tokens, expiry, one-active-link invalidation, SMTP delivery, generic forgot-password responses, session revocation after reset, and frontend pages for each flow.
- Added migration `c9d0e1f2a3b4` for `users.email_verified_at` and `email_action_tokens`, with schema-guard and model synchronization.

## Verification matrix

| Area | Test executed | Result | Evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| Frontend clean install | `cd frontend && rm -rf node_modules && npm ci` | Passed | Lockfile install completed; audit reported 0 vulnerabilities after Vitest upgrade | First attempt hit a Windows file lock, then passed after clearing generated `node_modules` |
| Frontend type check | `npm run typecheck` | Passed | `tsc --noEmit`, exit 0 | None |
| Frontend lint | `npm run lint` | Passed | ESLint, exit 0 | None |
| Frontend tests | `npx vitest run` | Passed | 15 files, 87 tests | Browser interaction was not exercised |
| Frontend production build | `npm run build` | Passed | Vite build, exit 0 | Bundle size not budget-tested |
| Frontend production dependencies | `npm audit --omit=dev --audit-level=high` | Passed | 0 vulnerabilities | None |
| Frontend full dependency tree | `npm audit --audit-level=high` | Passed | 0 vulnerabilities after Vitest 5.1.1 | None |
| Backend full suite | `cd backend && ./.venv/Scripts/python.exe -m pytest -q` | Passed | 74 passed, 2 skipped, 1 warning | Skips are live-Redis tests; no live Redis here |
| Backend dependency consistency | `pip check` | Passed | No broken requirements | Local Python is 3.14; container uses 3.11 |
| Backend compile | `python -m compileall -q app scripts crawler ranker` | Passed | Exit 0 | None |
| Runtime dependency audit | `pip-audit -r requirements-runtime.txt` | Passed | No known vulnerabilities | Python 3.11 container resolution was not re-audited |
| Empty database migration | `DATABASE_URL=sqlite:///./data/ci_email_verify.db alembic upgrade head` | Passed | Reached `c9d0e1f2a3b4`; schema guard passed | Fresh PostgreSQL migration not executed locally |
| Migration drift | `alembic check` | Passed | `No new upgrade operations detected` | PostgreSQL autogenerate parity covered only in CI definition |
| Existing SQLite upgrade | Existing workspace DB at current head | Passed previously | Catalogue and users retained | Full prior-version upgrade was not repeated in this pass |
| Argon2id and JWT | Existing `tests/test_auth_security.py` | Passed | Included in 67-test suite | No external penetration test |
| Cross-user watchlist | New regression test | Passed | Second account cannot see or delete first account's entry | None |
| Cross-user preferences | New regression test | Passed | Second account still receives empty preferences | None |
| Redis limiter and cache | `pytest tests/test_redis_integration.py` | Skipped | 2 skipped because `CINERANK_TEST_REDIS_URL` is unset | Must run in CI or staging with real Redis |
| PostgreSQL migration | CI job defined | Not executed | `.github/workflows/ci.yml` migration job | Docker and PostgreSQL unavailable locally |
| Docker image builds | Not executed | Blocked | `docker` command unavailable | Requires Docker host |
| Compose runtime | `docker compose config` not executed | Blocked | Compose YAML parsed only | Requires Docker and daemon |
| Nginx 1.28 runtime | Not executed | Blocked | Static configuration reviewed | Requires pinned container |
| Grafana runtime | Not executed | Blocked | Dashboard JSON and provisioning YAML parse | Requires Compose monitoring profile |
| Backup restore drill | Not executed | Blocked | Scripts passed `bash -n`; procedure documented | Requires PostgreSQL and Docker |
| Local load smoke | `python scripts/load_smoke.py --spawn --duration 8 --endpoint-concurrency 2` | Passed with expected 429s | `backend/load-smoke-report.json` | SQLite, one process, one host; not production capacity |
| Browser and accessibility E2E | Not executed | Blocked | No Chrome available | Requires browser runner |
| Email verification and reset | Backend fake-sender tests and frontend page tests | Passed in code | Hash-only tokens, single-use replay rejection, session revocation, generic forgot response, unconfigured `503`; 5 account-recovery UI tests pass | Real SMTP delivery and sender-domain authentication were not executed |
| Alert rules and dashboard config | JSON and YAML parse checks | Passed | 11 Grafana panels parse; Prometheus and Compose rule mounts parse | Prometheus evaluation and Grafana rendering require Docker |
| Persistent audit trail | Not implemented | Open | Security events go to logs | Requires audit table/product decision |
| Public deployment | Not executed | Blocked | No target or credentials | Requires hosting authorization |

## Local load smoke results

Command:

```bash
cd backend
./.venv/Scripts/python.exe scripts/load_smoke.py --spawn --duration 8 --endpoint-concurrency 2 --json-out load-smoke-report.json
```

Environment: one Uvicorn process, SQLite catalogue with 5,750 titles, all model artifacts loaded, 14 total concurrent workers, local loopback. The rate limiter is active. 429 responses are counted separately from server errors.

| Endpoint | Requests | 5xx/transport errors | 429 | Throughput rps | p50 ms | p95 ms | p99 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| health | 138 | 0 | 0 | 17.25 | 44.56 | 432.54 | 688.46 |
| ready | 133 | 0 | 0 | 16.62 | 45.30 | 470.71 | 602.82 |
| catalogue | 123 | 0 | 0 | 15.38 | 49.17 | 306.95 | 1626.24 |
| facets | 86 | 0 | 0 | 10.75 | 68.41 | 257.30 | 4009.53 |
| search | 89 | 0 | 59 | 11.12 | 84.50 | 633.83 | 1550.65 |
| recommendations | 65 | 0 | 45 | 8.12 | 81.25 | 356.99 | 4061.52 |
| watchlist | 98 | 0 | 68 | 12.25 | 67.67 | 493.35 | 1403.10 |

Interpretation:

- No server errors or transport failures occurred.
- The per-user and per-IP limits intentionally capped search, recommendations and watchlist after 30 successful requests per minute, which also caps the measured throughput.
- The long p99 tails on facets and recommendations show SQLite and single-process contention. They are not PostgreSQL capacity numbers.
- An earlier run with cold new users produced approximately 13 second recommendation responses and six client timeouts on SQLite. That is a real local cold-start bottleneck that must be profiled against PostgreSQL before release.
- Single-instance versus multi-instance scaling was not tested because Docker is unavailable.

## CI pipeline

`.github/workflows/ci.yml` now defines:

1. Backend compile, SQLite migration upgrade, `alembic check`, and the full pytest suite.
2. PostgreSQL 16 service migration from an empty database, current revision check, drift check and schema guard.
3. Redis 7.4 service integration tests for atomic limits and cache TTL.
4. Frontend lockfile install, typecheck, lint, tests and production build.
5. Dependency vulnerability scans with pip-audit and npm audit.
6. Compose configuration validation.
7. API and web Docker image builds.

The workflow itself was not run on GitHub. YAML parsing passed locally.

## Operational assets

- `deploy/backup_postgres.sh`: checksummed custom-format dump with retention.
- `deploy/restore_postgres.sh`: checksum verification and explicit restore confirmation.
- `deploy/BACKUP_RESTORE.md`: restore drill, encryption guidance and RPO/RTO measurement rules.
- `deploy/grafana-dashboards.yml` and `deploy/dashboards/cinerank-api.json`: provisioned HTTP health dashboard.
- `backend/scripts/load_smoke.py`: reproducible local load harness.

## Explicit blockers and required inputs

| Blocker | Required to clear it |
| --- | --- |
| Docker image and Compose runtime validation | Docker Engine on the build host |
| Nginx 1.28 and replica balancing | Pinned Nginx container and multiple API replicas |
| Redis integration execution | Reachable test Redis, or the CI service job |
| PostgreSQL migration and restore drill | Reachable PostgreSQL and docker compose database service |
| Production capacity and pool sizing | Staging deployment, PostgreSQL, realistic traffic profile |
| Browser accessibility and visual E2E | Chrome or Playwright browser installation |
| Email verification and reset | Mail provider account, sender domain, API credentials |
| Public release | Authorized hosting target, TLS ingress, secrets manager |

## Residual risks

- Recommendation p99 latency and cold-start behavior are not characterized on PostgreSQL.
- Alert rules and dashboard panels are configured but have not been evaluated by a running Prometheus or Grafana instance.
- Email delivery depends on an external SMTP provider and sender-domain configuration; no live message delivery was verified.
- Security events are logged but not persisted in an audit table.
- Backups are not encrypted by the scripts themselves; encryption and off-host storage are operator responsibilities.
- No independent penetration test or load test at production scale has been performed.
- RPO/RTO are not fixed until a restore drill measures the real deployment.
