# CineRank technical documentation

This documentation describes the code and operational contracts in this repository. It is intended for backend engineers, data/ML engineers, database administrators, frontend developers, and operators. The root [README](../README.md) is the short entry point; this index links to the detailed implementation notes.

## Architecture and application boundaries

- [System architecture and runtime flows](architecture/overview.md): component responsibilities, process boundaries, request sequence, scheduled jobs, artifact flow, scaling limits, and failure behavior.
- [Service catalogue](architecture/services.md): module-by-module responsibilities, public interfaces, dependencies, and startup modes.
- [Candidate generation and ranker](architecture/ranker.md): algorithm semantics, scoring, source weights, cold-start behavior, and evaluation limitations.

## Data and persistence

- [Relational schema and identity contract](database/schema.md): entities, keys, foreign keys, indexes, lifecycle, and data ownership.
- [Title provenance and integrity audit](data/title-provenance.md): source-to-database title comparison, API consistency, artwork limitation, frontend fallback repair, and rollback.
- [Catalogue ordering and SQL portability](database/sorting.md): immutable title identity, versioned alphabetical indexes, transactions, concurrency, collations, scale, and engine-specific SQL examples.
- [SQL examples](database/sql/): PostgreSQL, MySQL 8+, SQLite, and SQL Server reference scripts. The Python service remains the canonical implementation.

## Machine learning

- [Model algorithms and artifact formats](ml/algorithms.md): training assumptions, input matrices, model families, inference constraints, and serialization.
- [Colab training notebook](ml/colab_training.md): complete standalone training workflow, dataset policy, sampling, temporal holdout, configuration, output bundle, and backend import.
- [Evaluation and 60-day model lifecycle](ml/lifecycle.md): daily Pass@K checks, challenger training, promotion gates, rollback semantics, and metric interpretation.

## Metadata crawling

- [Crawler architecture and operating policy](crawler/crawler.md): TMDB adapter, allow-listed web discovery, robots rules, link/sitemap discovery, structured extraction, safety constraints, retry semantics, and database upserts.

## Integration and operations

- [HTTP API contract](api/endpoints.md): routes, authentication, request/response examples, cursors, error handling, and frontend integration sequence.
- [Getting started](operations/getting_started.md): local installation, migration, Colab/local training, bundle import, API, worker, Docker Compose, and verification commands.
- [Configuration reference](operations/configuration.md): environment variables, defaults, and practical tuning guidance.
- [Deployment and scaling](operations/deployment_scaling.md): database topology, stateless API replicas, HAProxy, worker leases, storage, and operational constraints.
- [Security model and hardening checklist](security.md): authentication, secrets, API boundaries, crawler SSRF controls, artifact integrity, and production controls.
- [Troubleshooting](operations/troubleshooting.md): common startup, migration, crawler, model, training, and deployment failures.

## Change-management rule

When a route, ORM field, setting, model file, crawler policy, job schedule, or promotion metric changes, update the corresponding page in this documentation in the same change. The code, Alembic migration, tests, `.env.example`, API schema, and documentation must describe the same contract. Do not treat a planned component as implemented merely because it appears in a diagram.
