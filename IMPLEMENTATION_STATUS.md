# CineRank Implementation Status

This file distinguishes implemented and executed checks from work that still requires infrastructure or provider access. It is not a claim that the application has been deployed to production.

## Implemented in this project

### Frontend

- React, TypeScript and Vite application architecture retained.
- Protected routes and memory-only access-token handling with HttpOnly refresh-cookie bootstrap.
- Catalogue, canonical title pages, search, genre facets, ratings, watchlist, history and profile flows.
- Dedicated personalized recommendations page uses the authenticated `GET /api/v1/recommendations` route.
- Visible recommendation impressions and explicit like/dislike feedback use the interaction contract.
- User preference page supports preferred/excluded genres, adult-content inclusion, minimum release year and maximum runtime. Prefer and exclude controls have distinct accessible names.
- Preference save invalidates personalized home and recommendation query caches.
- Title pages show ten model-driven similar titles in a scrollable rail that prefetches toward 24 items.
- Home `For you` prefetches the next cursor page about one viewport before the rail end.
- Poster covers use deterministic irregular 3-10 sided polygons with four translucent layers, screen blending, faster drift and reduced-motion-aware shape and text animation.
- API client surfaces `Retry-After` guidance for rate-limited requests.

### Backend and recommendation serving

- FastAPI modular application and versioned multi-model release retained.
- Argon2id password hashing with successful-login migration from legacy scrypt hashes.
- Short-lived JWT access tokens, opaque refresh-token rotation, server-side session revocation and ownership checks.
- Redis-backed atomic sliding-window rate limits across API replicas, with local development fallback and fail-closed production behavior.
- Redis recommendation cache uses user, model release, activity, catalogue and preference versions. PostgreSQL remains authoritative.
- Explicit user preferences have an Alembic migration, schema guard, API service and database range constraints.
- Recommendation serving combines model candidates and catalogue popularity with weighted RRF and genre-aware MMR.
- Item-to-item similar titles use the trained ItemKNN row, content fallback and same-genre catalogue fallback.
- Request IDs, security headers, CORS response-header exposure and Prometheus HTTP request metrics.
- Recommendation cache, duration, item-count, inference, Redis failure and database failure metrics, plus Prometheus alert rules and expanded Grafana panels.
- SMTP email verification and password reset with hashed single-use tokens, expiry, resend controls and session revocation after reset.
- Safe TMDB crawler, provider normalization, job leases and immutable model artifact checks.

### Infrastructure and delivery

- PostgreSQL and authenticated private Redis services in Compose.
- Bounded SQLAlchemy connection pools and documented connection budgeting.
- Nginx 1.28 DNS-aware round-robin upstream for horizontally scaled API replicas.
- Nginx security headers and Content Security Policy.
- Optional Prometheus and Grafana profile with a provisioned API health dashboard and alert rules for availability, errors, readiness, latency, cache, Redis and database failures.
- Checksummed PostgreSQL backup and guarded restore scripts, plus a restore drill procedure.
- GitHub Actions covers backend tests, SQLite migration validation, PostgreSQL migration validation, Redis integration tests, dependency scans, frontend checks, Compose validation and Docker image builds.

## Verification executed in this environment

- Backend: 74 passed, 2 skipped. The skipped tests are the real-Redis tests, which require `CINERANK_TEST_REDIS_URL`.
- Backend full suite includes the legacy portable-model tests after installing declared dev dependencies.
- Python compile and import checks passed.
- Fresh SQLite Alembic upgrade reached `c9d0e1f2a3b4`; the schema guard passed against that fresh database.
- `alembic check` reports no new upgrade operations.
- Frontend: `npm run typecheck`, `npm run lint`, all 87 tests and `npm run build` passed.
- `pip-audit -r backend/requirements-runtime.txt`: no known vulnerabilities.
- `npm audit`: 0 vulnerabilities after upgrading Vitest to 5.1.1; production-only audit is also clean.
- Compose, CI, Prometheus and Grafana provisioning YAML parsed; dashboard JSON parsed; backup and restore scripts passed `bash -n`.
- Live SQLite run loaded all seven model paths and the similar-title endpoint returned ten unique titles for The Matrix, excluding the source.

## Not verified or not implemented

- Docker CLI is unavailable here. Docker image builds, full Compose startup, Nginx 1.28 runtime, replica balancing, Grafana rendering and container health checks were not executed.
- Redis and PostgreSQL services are unavailable here. The provided CI jobs execute Redis integration and PostgreSQL migration checks, but those jobs have not been run in this environment.
- Backup and restore scripts were syntax-checked only. No restore drill has been executed against a real PostgreSQL deployment.
- No load, soak or browser end-to-end tests were executed.
- Email verification and password reset are implemented with hashed single-use tokens and fake-sender tests. Real delivery requires SMTP credentials and a sender domain, which are not configured here.
- Audit events are written to application logs, not a persistent audit table.
- Transactional outbox delivery, separate migration/application database roles, external secret management and TLS ingress remain deployment-specific work.
- Recommendation, cache, inference, Redis and database metrics and alert rules are configured, but no running Prometheus or Grafana instance has evaluated them.

Do not treat these results as proof of a fully deployed production system. Run the container, Redis, PostgreSQL, backup and load checks in staging before release.
