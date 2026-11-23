# Backend Architecture Overview

The root [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) is the canonical end-to-end architecture document. It describes frontend/backend boundaries, the API contract, canonical title identities, session security, request-to-inference flow, model release validation, Docker network topology, metadata backfill and operational limitations.

The backend is a FastAPI application split into routes, core security/configuration, SQLAlchemy entities, Pydantic schemas, services and an ML release adapter. A separate worker handles catalogue synchronization. PostgreSQL is the intended Compose deployment database; SQLite remains supported for local development and tests.

Key invariants:

- `title_id` is the canonical immutable CineRank title key.
- `serial_number` is the stable public title route key.
- Provider IDs are only used to resolve model and metadata sources.
- Database records are the authoritative catalogue metadata source for API responses.
- All database schema changes are Alembic migrations.
- The active recommendation release is immutable v2 and is not replaced by legacy v1 automation.
- Access JWTs are memory-only in the browser; refresh credentials are opaque, rotated and HttpOnly-cookie based.

See also `../database/schema.md`, `../api/endpoints.md` and `../operations/getting_started.md` for specialized contracts.
