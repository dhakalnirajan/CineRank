# CineRank Agent Instructions

CineRank is a movie and television recommendation product.

- `backend/`: Authority for catalogue data, identity, authentication, recommendations, and persistence.
- `frontend/`: Authority for presentation, navigation, interaction, and client-side UX.

---

## 1. Supervisor & Sub-Agent Operating Protocol

You are the **Supervisor Agent**. You never write code, edit files, or run build mutations directly. You plan, delegate to specialized sub-agents, verify their output, and maintain the Work Queue.

### Delegation & Context Hygiene

- **Isolate Context:** Spawn sub-agents with narrow, self-contained scopes (exact file paths, target contracts, and acceptance criteria) so your supervisor context stays clean.
- **Single-Pass Inspection:** Instruct sub-agents to list every required file first, read them in one batch, apply all edits cleanly, and run verification once.
- **Zero Guessing:** If a requirement, schema, or route is ambiguous, instruct a read-only sub-agent to inspect the codebase (`ARCHITECTURE.md`, `routes.py`, `schemas.py`) or ask the user before making changes.
- **Accountability:** You own every line produced by sub-agents. Reject and re-delegate sub-agent work that violates any rule in this file.

### Work Queue Discipline (FIFO)

- **Strict Queue Order:** Treat all work as a strict FIFO queue. Append new user requests, tweaks, or bug fixes to the bottom of the **Work Queue** table. Never break queue order to prioritize a new correction.
- **Completion Gate:** Do not stop until 100% of queued items are `Complete` with recorded verification proof. Never rewrite or delete completed historical rows.
- **No Apologies, Fix Instruction Gaps:** Never apologize when a mistake happens. Diagnose which missing, vague, or conflicting rule in `AGENTS.md` allowed the mistake, and propose a concrete patch to this file.
- **YAGNI & Scope Control:** Calibrate engineering effort to the current milestone. Never expand scope or add abstractions without explicit permission, though you should suggest high-value scope improvements when relevant.

---

## 2. Verification & Execution Commands

A task is **not complete** until a sub-agent runs the relevant checks and returns clean exit codes. Never claim a feature works without verification output.

### Frontend (`frontend/`)

- Typecheck: `npm run typecheck`
- Lint: `npm run lint`
- Unit & Component Tests: `npm test` (or `npx vitest run`)
- Production Build: `npm run build`

### Backend (`backend/`)

- Test Suite: `pytest`
- Migrations: Verify schema upgrades cleanly without data loss before marking migration tasks complete.

### Failure Recovery Protocol

- **Never Hack Tests to Pass:** If a test fails, fix the implementation or update tests only when the underlying requirement explicitly changed.
- **3-Strike Escalation:** If a sub-agent fails to resolve a build or test error after 3 attempts, halt execution, summarize the exact root cause and stack trace, and ask for direction.

---

## 3. Progressive Disclosure (Canonical References)

Read these files on demand before touching their respective domains:

- `ARCHITECTURE.md`: System boundaries, auth flows, security rules, and verified backend discrepancies. Required reading before any API or integration edit.
- `frontend/DESIGN.md`: Color tokens, spacing, typography scale, and component patterns. Required reading before any UI or CSS edit.

---

## 4. Engineering & Security Guardrails

### Code & Architecture

- **Strict TypeScript:** Never use `any` without a documented, justified reason.
- **Modularity:** Prefer small, focused modules and components over premature abstractions. Avoid duplicated business logic and unnecessary global state.
- **Clean Deliverables:** Leave zero TODOs, dead code, placeholder screens, mock features, or arbitrary network timeouts in completed work.
- **Dependency Discipline:** Do not install new packages without an explicit, justified need.
- **Doc Sync:** Update `ARCHITECTURE.md`, `frontend/DESIGN.md`, or `AGENTS.md` in the same task whenever contracts, tokens, or workflows change.

### Security & Failure Handling

- **Secrets:** Never hardcode secrets or place sensitive keys in `VITE_*` browser environment variables.
- **Auth Boundary:** The frontend is never an authorization boundary; the backend enforces ownership.
- **Explicit States:** Handle loading, empty, error, and success states explicitly. Never swallow errors or mask failures behind generic success messages.

---

## 5. Verified Backend Contracts (Non-Negotiable)

Never invent API fields, routes, or backend behavior, and never silently alter backend contracts.

1. **Title Identity:** `title_id` (42 characters) is the sole durable internal identifier. `serial_number` is the permanent public URL identifier, formatted as six-digit text. Public title URLs use `/{media_type}/{serial_number}/`; API mutations, foreign keys, React keys, and relationships use `title_id`. Never substitute MovieLens, TMDB, IMDb, serial numbers, or positional IDs for internal title identity. Never render `title_id`, `serial_number`, provider IDs, provider names, or database values in visible UI text or labels. Preserve the raw provider `title`; use the computed `display_title` for presentation so library-style articles such as `Matrix, The (1999)` appear as `The Matrix (1999)` without rewriting stored data.
2. **Base Path:** `/api/v1`, configured exclusively via `VITE_API_BASE_URL`.
3. **Authentication:** Login uses form-encoded `POST /auth/token` (not JSON).
4. **Pagination & Cursors:** Catalogue pages use opaque signed cursors. Never construct, decode, or mutate them.
5. **Version Conflicts (`409`):** A catalogue `409` means the sort version changed. Reset to page 1 while preserving active filters.
6. **Defensive Parsing:** `genres` is a delimited string (not JSON). `directors_json` and `cast_json` are JSON strings; parse defensively and tolerate malformed values.
7. **Recommendations:** Scores are ranking values, not probabilities or percentages. Display only the exact `reason` string returned by the API. New clients call `GET /recommendations`; identity comes from the bearer token. `/recommend/{user_id}` is compatibility-only.
8. **Cold-Start Titles:** Do not filter out titles lacking a MovieLens ID; they are valid recommendations.
9. **No Fake Playback:** The backend logs interaction events only; it does not stream media. Never fabricate video players.
10. **User Preferences:** `GET/PUT /users/me/preferences` is the only supported explicit recommendation-preference contract. Preferred/excluded genres, adult inclusion, minimum year and maximum runtime are persisted by the backend. The frontend must not apply a second recommendation ranking.
11. **Verified Endpoint Shapes:**
    - `GET /watchlist` returns a bare array of `{created_at, title}`.
    - `GET /home/{user_id}` returns `{for_you, popular, genres, next_cursor, model, generated_at}`.
    - `GET /users/{user_id}/history` returns user ratings only, not playback history.

---

## 6. UI, Typography & Copywriting Rules

### Visual & Typography Constraints

- **Zero Em/En Dashes:** Never use em dash or en dash characters anywhere: not in UI copy, code, comments, commit messages, or markdown files. Use hyphens (`-`), commas, colons, or periods instead.
- **No Middle Dots:** Never use the middle-dot character (U+00B7) as a UI separator. Use separate elements, spacing, wrapping, or a CSS divider instead. This does not apply to middle dots that are part of provider title data.
- **No Internal Identifiers:** Never display internal IDs, serial numbers, provider IDs, provider source names, or database values in visible UI copy, metadata rows, or accessible labels. IDs may appear in URLs, route parameters, request payloads, component keys, and action handlers only.
- **Metadata Hierarchy:** Keep structural metadata (year, media type, runtime) separate from genres. Render genres as distinct chips or a separate wrapping group. Never build a long separator-delimited metadata string.
- **Artwork Fallback:** A missing-artwork placeholder may be an intentional typographic poster with the display title, year, and primary genre. Never derive initials or concatenate fallback fragments with the title. Keep the fallback accessible label separate from the visible title and use a deliberate gradient or surface treatment rather than a broken-image icon.
- **No AI Pills:** Never generate decorative "AI-powered" badges, pills, or sparkles.
- **Accessibility:** Use semantic HTML and keyboard-accessible interaction patterns.

### Consumer UI Copywriting

Write concise, human-centered copy for an end-user consumer product. Never write like developer documentation or system specs.

#### Strict Prohibitions

- **Zero Architecture Leaks:** Never mention internal mechanics in user-facing text. Banned terms: *backend, frontend, API, endpoint, server, database, browser, client-side, sort index, payload, cache, query*.
- **No Developer Error Messages:** Never instruct users to check servers, APIs, consoles, or network logs (e.g., never write *"Check that the API is running"*).
- **No Redundant Labels:** Never repeat the same noun or verb across adjacent headings, subheadings, and placeholders (e.g., avoid *"Search > Find a title > Search the catalogue > Search films"*).
- **No Meta-Explanations:** Do not write sentences explaining obvious UI behavior (e.g., omit *"Results update as you type"*, *"Filters are available"*, or *"Ordered alphabetically by sort index"*).

#### Tone & Formatting Standards

- **Show, Don't Tell:** Let UI controls (`Sort: A-Z`, filter pills, search inputs) communicate behavior visually instead of adding explanatory paragraphs.
- **Outcome-Focused:** Frame headlines around user value (*"Find your next favorite film"*) rather than system mechanics.
- **Scannable & Minimal:** Keep headings to 3-6 words, subheadings under 15 words, and button labels to 1-3 words.
- **Calm Error & Empty States:** Keep messages blame-free and actionable (e.g., *"Couldn't load titles right now. Please try again."* + `[Retry]`).
- **Context-Aware Navigation:** Hide authenticated links (`Watchlist`, `Profile`) when logged out to keep navigation uncluttered.

#### Copy Examples

- **Bad:** *"Alphabetical catalogue pages served by the backend. Filters and search are available without an account."*
- **Good:** *"Browse the Catalogue"* (paired with visible filter/sort controls).
- **Bad:** *"We could not reach the CineRank service. Check that the API is running."*
- **Good:** *"Couldn't load titles right now. Try again in a moment."*

---

## 7. Critical Review Checklist (Run Before Marking Complete)

Before marking any Work Queue item `Complete`, verify:

1. All acceptance criteria are met with concrete command output.
2. Zero em/en dashes or banned architecture terms exist in modified files (`grep` check recommended).
3. No unnecessary abstractions or scope creep were introduced; if complexity crept in, simplify before closing and propose a workflow improvement.
4. The Work Queue table below is updated with verification results.

---

## 8. Advanced Agentic Orchestration & Execution

### Parallel vs. Sequential Sub-Agent Dispatch

- **Parallel Read / Audit:** Dispatch multiple read-only sub-agents concurrently when inspecting disjoint modules (e.g., auditing `frontend/src/pages` while inspecting `backend/app/api/routes.py`).
- **Serialized Write Lock:** Never allow two sub-agents to edit overlapping files concurrently. Serialize write tasks or partition ownership strictly by directory/file path.
- **Sub-Agent Prompt Contract:** Every delegation prompt you issue must contain four explicit blocks:
  1. **Target Files:** Exact paths to read and modify.
  2. **Non-Negotiable Constraints:** Relevant rules from Sections 4, 5, and 6.
  3. **Definition of Done:** Exact behavior or copy changes required.
  4. **Verification Command:** The exact shell command the sub-agent must execute and paste output from.

### Diff & Git Hygiene

- **Minimal Blast Radius:** Touch only files directly required by the active Work Queue item. Never reformat unrelated files or reorder imports across untouched modules.
- **No Unsolicited Refactors:** If a sub-agent spots technical debt outside the current task scope, it must report it back to you rather than fixing it inline. Log valid improvements as new rows at the bottom of the Work Queue only after user approval.
- **Clean Working Tree Verification:** Before marking a task `Complete`, verify via `git status` and `git diff --stat` that no temporary scripts, stray logs, or unintended file mutations remain.

### Automated Grep Gates (Run Before Closing Frontend/Docs Tasks)

Sub-agents modifying UI copy, components, or markdown files must run these checks and confirm zero violations:

- **Em/En Dash Gate:** Search modified files for Unicode code points U+2014 and U+2013. Any match is an automatic rejection.
- **Architecture Leak Gate:** Search user-facing strings in `frontend/src/` for banned technical terms (`backend`, `frontend`, `API`, `endpoint`, `server`, `database`, `browser`, `client-side`, `sort index`, `payload`, `cache`, `query`) outside comments, types, and API client internals.
- **Type Escape Gate:** Search modified TypeScript files for `: any` or `as any`. Any match without an inline justification comment is rejected.

### Context & State Recovery

- **Handoff Summary on Long Queues:** If the conversation grows long or approaches context limits after completing a queue item, output a compact state snapshot (current Work Queue status, last verified commit/diff summary, and exact next queue ID) so work can resume seamlessly without re-reading the entire repository.
- **Deterministic Rollback:** If a multi-file edit introduces regressions that cannot be cleanly resolved within the 3-strike limit, instruct a sub-agent to revert the uncommitted working tree (`git checkout -- .`) before re-planning a smaller incremental step.

---

## 9. Work Queue

The queue is the source of truth for planned work. Append new requests to the end. A task is complete only when acceptance criteria and verification results are recorded. Do not mark the queue clear while any task is pending, in progress, or blocked.

| ID | Description | Priority | Status | Dependencies | Acceptance Criteria | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| F0-01 | Create root engineering instructions | High | Complete | None | `AGENTS.md` contains core instructions and engineering rules | Reviewed against mission |
| F0-02 | Document system and integration architecture | High | Complete | Backend inspection | `ARCHITECTURE.md` covers boundaries, flows, security, deployment, limitations, and Mermaid diagrams | Checked against `routes.py` and `schemas.py` |
| F1-01 | Scaffold React, TypeScript, Vite, Tailwind frontend | High | Complete | F0-02 | Strict TypeScript, Tailwind, React Router, TanStack Query, Vitest configured | `npm run typecheck`, `npm run build` pass |
| F1-02 | Implement centralized API client and verified types | High | Complete | F1-01 | Base URL config, bearer token, form login, timeout, cancellation, error normalization | 9 API client tests pass |
| F1-03 | Implement design tokens and design system document | High | Complete | F1-01 | Tokens implemented in CSS and documented in `frontend/DESIGN.md` | Build passes; tokens audited against `global.css` |
| F2-01 | Implement authentication and protected routes | High | Complete | F1-02 | Register, login, logout, `/auth/me`, expiry handling, redirects | Validation and login component tests pass |
| F2-02 | Implement catalogue, search, and title detail | High | Complete | F1-02, F1-03 | Keyset pagination, 409 recovery, filters, debounced search, fallbacks | API cancellation, 409, cursor, and media fallback tests pass |
| F2-03 | Implement personalized home and recommendation rows | High | Complete | F2-01 | `for_you`, `popular`, genre rows, load more, empty and 503 states | HomeHero test passes; contract audited against `routes.py` |
| F2-04 | Implement watchlist, ratings, history, profile, interactions | High | Complete | F2-01 | Real endpoints only, optimistic rollback where used, deduplicated impressions | Typecheck, lint, contract audit |
| F3-01 | Verify typecheck, lint, tests, production build | High | Complete | All above | All commands pass and results are recorded | `typecheck`, `lint`, production build pass; expanded suite passes |
| F3-02 | Critical review and cleanup | Medium | Complete | F3-01 | No dead code, fake features, unsupported assumptions, or documentation drift | Production build, lint, and documentation audit |
| F3-03 | Expand critical flow coverage | High | Complete | F3-01 | Auth, protected routes, session expiry, registration, catalogue pagination and 409 recovery, search, title details, home, ratings, watchlist, interactions, history, and fallback states | 47 mocked API, component, and page tests pass |
| F4-01 | Apply Netflix-inspired cinematic redesign | High | Complete | F3-01 | Black canvas, red primary, white editorial type, billboard hero, sharp media, gradient depth, 8px buttons | Typecheck, lint, tests, production build pass |
| F5-01 | Harden backend authentication and session security | High | Complete | F4-01 | Short-lived access JWT, rotating HttpOnly refresh sessions, reuse detection, logout and logout-all, session listing and revocation, ownership checks, CSRF, rate limiting, security logging, migration, tests, documentation | 26 auth tests and full backend suite pass; migration upgrade verified; documentation updated |
| F5-02 | Apply Plus Jakarta Sans and Inter typography | High | Complete | F4-01 | Google Fonts preconnect and stylesheet, display and sans tokens, weights, hero, rail, card, body, meta, and badge scale, tabular metadata numbers | Frontend typecheck, lint, tests, and production build pass |
| F5-03 | Rewrite UI copy for consumer clarity | High | Complete | F4-01 | No architecture terms, developer error instructions, redundant labels, or explanations of standard controls; headings, descriptions, errors, empty states, and buttons follow the supplied tone and length rules | Frontend typecheck, lint, 48 tests, and production build pass; visible copy audited |
| F5-04 | Create CineRank logo, favicon, and navbar | High | Complete | F5-02 | Reusable brand mark and wordmark, complete favicon metadata, responsive desktop and mobile navigation, signed-in state, accessible labels, and no regression in current routes | Frontend typecheck, lint, 48 tests, and production build pass; favicon sizes and rendered mark reviewed |
| F5-05 | Fix bundle import and activate recommendation artifacts | High | Complete | F5-01 | Imported bundle populates catalogue, users, and ratings on SQLite; active bundle is installed; API returns real recommendations | Checksums, 5,750 titles / 9,984 users / 980,778 ratings imported, active bundle installed, live registration and recommendation responses verified, 33 backend tests pass |
| F5-06 | Recover a missing ACTIVE_BUNDLE pointer at startup | High | Complete | F5-05 | If the pointer is absent and exactly one checksum-valid bundle directory exists, startup verifies it and writes the pointer; multiple candidates are left unset rather than guessed | Live startup recovery with six models loaded, frontend home and recommendation routes exercised from the Vite origin with CORS, 35 backend tests and 48 frontend tests pass, frontend production build passes |
| F6-01 | Add permanent public title serial numbers and canonical routes | High | Complete | F5-06 | Global immutable serial numbers, deterministic backfill, transactional allocation, serial in every title response, media-scoped lookup, `/movie/{serial}/` and `/tv/{serial}/` routes, legacy UUID redirects, serial in every title response and route navigation but not visible UI text, documentation | Migration applied to 5,750 titles with unique serials, live catalogue/search/recommendation/history/watchlist serials verified, cross-media lookup returns 404, direct Vite navigation to movie, TV, and legacy routes returns 200, 39 backend and 51 frontend tests pass, frontend typecheck, lint, and production build pass |
| F6-02 | Audit title integrity, remove internal IDs from visible UI, and separate metadata | High | Complete | F6-01 | Prove source-to-API title provenance, preserve provider punctuation, hide serial numbers and source names from UI, separate structural metadata from genre chips, remove middle-dot separators, make artwork fallback independent of titles, make crawler modules independently runnable, add regression tests and documentation | All 5,750 source rows match the database with 0 field mismatches and 0 orphans; all ten reported titles match detail, search, and catalogue responses; 42 backend tests and 61 frontend tests pass; typecheck, lint, and production build pass; both crawler CLIs launch from `backend/` and `backend/crawler/` and exit cleanly without credentials |
| F6-03 | Refactor catalogue presentation and recommendation entry points | High | Complete | F6-02 | Add computed display titles, catalogue media/genre facets, recommendation cache and unseen-hero rotation, unified 2:3 cards with typographic artwork fallback and watchlist hover action, dynamic Explore filters, Search and Watchlist discovery states, and compact Profile tabs | Source and API title provenance retained; 44 backend and 64 frontend tests pass; typecheck, lint, and production build pass |
| F6-04 | Secure persistent auth, header search sizing, custom error pages, and footer redesign | High | Complete | F6-03 | Memory-only access tokens with HttpOnly refresh bootstrap, silent 401 retry, synchronized logout, sliding refresh expiry, shorter single-clear header search, reusable 404 and runtime error pages, and three-column footer with permanent copyright | Backend auth tests pass; 71 frontend tests pass; typecheck, lint, and production build pass |
| F7-01 | Add dedicated personalized recommendations page and explicit feedback controls | High | Complete | F6-04 | Use canonical `/recommendations` response, visible-card impressions, `like`/`dislike` interaction events, route and navigation integration, and document the contract | Frontend dependency-backed checks pass: typecheck, lint, 87 tests, and production build |
| F8-01 | Implement shared Redis infrastructure, Argon2id password migration, weighted RRF, explicit user preferences, canonical recommendation route, and request security middleware | High | Complete | F7-01 | Redis-backed distributed limits/cache, legacy password hash upgrade, Alembic preferences migration, authenticated preference CRUD, recommendation filtering and versioned cache keys | 62 backend tests pass; fresh SQLite Alembic upgrade reaches `a8b9c0d1e2f3` |
| F8-02 | Integrate frontend preference settings and canonical recommendation identity | High | Complete | F8-01 | Preferences page, profile entry point, typed API calls, canonical recommendations endpoint, cache invalidation | Frontend typecheck, lint, 87 tests, and production build pass |
| F8-03 | Update deployment, CI, security headers, architecture and operational documentation | High | Partial | F8-01 | Redis service and secrets, pool configuration, CSP, CI workflow, synchronized endpoint/schema/deployment documentation | Python compile and Compose/CI/monitoring YAML parsing passed; Nginx static syntax passed with a test upstream. Docker runtime validation remains unavailable |
| F9-01 | Complete observability and account recovery | High | Complete | F8-03 | Recommendation/cache/inference/Redis/database metrics, Prometheus alert rules and dashboard panels, email verification, password reset, migration, tests, and synchronized documentation | Backend suite passes; fresh SQLite migration reaches `d0e1f2a3b4c5`; `alembic check` clean; frontend typecheck, lint, tests, and production build pass; Prometheus, Compose, and dashboard configuration parse. Real SMTP delivery remains blocked |
| F10-01 | Production-readiness completion pass | High | Partial | F8-03 | Dependency manifests, ownership regressions, real Redis/PostgreSQL CI, migration drift, audits, backups, dashboard provisioning, load harness, documentation and archive | 74 backend tests passed with 2 Redis tests skipped; fresh SQLite migration and `alembic check` passed; typecheck, lint, 87 tests and build passed; pip-audit and npm audit clean; local load smoke recorded; Docker/PostgreSQL/Redis/browser/restore checks blocked and documented in `PRODUCTION_READINESS.md` |
| F11-01 | Import real catalogue overviews, cast and director metadata from downloaded dumps | High | Complete | F6-02 | Download reproducible public dumps, match without duplicate titles, populate overview, director, cast, artwork and provider metadata, preserve existing identities, document provenance and display through the existing title page | 5,657 of 5,750 titles enriched from 434,803 dump rows; 5,343 exact TMDB-ID and 314 unique title/year matches; 0 duplicate TMDB owners; 93 unmatched left empty; API and frontend title metadata verified; importer regression tests pass |
| F9-01 | Replace uniform poster cards with title-derived cover shapes | Medium | Complete | F6-04 | Unique deterministic shape composition per title, distinct position and rotation, consistent 2:3 frames, fallback and artwork treatments, documentation | 3 poster shape tests pass; changed files pass ESLint; production bundle builds; 75 of 76 existing tests pass with one unrelated preferences failure |
| F9-02 | Add similar-title recommendations and interaction-informed picks on title pages | High | Complete | F9-01 | Title page shows 10 similar titles; card clicks and title views are recorded; recorded interactions influence future recommendations | Live similar route returned 10 unique titles for The Matrix and 404 for an unknown serial; title and click-signal tests pass; 62 backend tests pass with the 2 legacy torch-dependent modules excluded; frontend typecheck, lint and production build pass |
| F9-03 | Animate cover shapes with soft edges, glow and fluid drift | Medium | Complete | F9-01 | Shapes drift, breathe and glow, soften at the edges and visually merge with neighbours without a physics engine | 3 poster shape tests pass; title-derived drift, blur, glow and reduced-motion behavior implemented; frontend typecheck, lint and production build pass |
| F9-04 | Make title-page similar titles a scrollable rail and prefetch more recommendations on horizontal scroll | High | Complete | F9-02 | Similar titles scroll in a rail after the first cards; rails prefetch the next recommendation page before the user reaches the end | 2 rail prefetch tests pass; title rail expands from 10 toward 24; home For you appends six-item cursor pages; 80 of 81 frontend tests pass with one pre-existing preferences query ambiguity; frontend typecheck, lint and production build pass |


## Handoff verification note

The task-table verification entries above record the state claimed and checked during the original implementation phases. For this packaged handoff, use the dated/current verification record in `ARCHITECTURE.md` as the source of truth: backend tests and SQLite migration checks were rerun; full frontend dependency-backed checks, Docker image builds, ONNX runtime inference, PostgreSQL deployment tests and browser E2E were not run in the offline handoff environment. Do not promote those historical checklist entries into a claim that the current packaged tree passed those commands.
