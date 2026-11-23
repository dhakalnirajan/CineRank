# CineRank Frontend API Integration

This document records the frontend's verified integration with the current FastAPI application. The backend OpenAPI document and route/schema implementation remain authoritative. All paths below are relative to the configured `VITE_API_BASE_URL`, normally `/api/v1` in the Docker deployment.

## Authentication and account

| Frontend operation | HTTP method | Path | Request behavior |
|---|---|---|---|
| Register | POST | `/auth/register` | JSON registration payload |
| Sign in | POST | `/auth/token` | Form-encoded `username` and `password`; receives access token and refresh cookie |
| Restore/rotate session | POST | `/auth/refresh` | Sends HttpOnly refresh cookie with credentials |
| Sign out | POST | `/auth/logout` | Sends refresh cookie; backend revokes current session |
| Sign out all sessions | POST | `/auth/logout-all` | Bearer-authenticated |
| Sign out other sessions | POST | `/auth/logout-others` | Bearer-authenticated |
| Current account | GET | `/auth/me` | Bearer-authenticated |
| Update profile | PATCH | `/users/{user_id}` | Bearer-authenticated; backend enforces ownership |
| Upload avatar | POST | `/users/me/avatar` | Multipart form data |
| List sessions | GET | `/auth/sessions` | Bearer-authenticated |
| Revoke session | DELETE | `/auth/sessions/{session_id}` | Bearer-authenticated; owner-scoped |

Access tokens are held in memory. The refresh token is HttpOnly and never read by JavaScript. A non-sensitive local session hint only determines whether startup should attempt refresh. Concurrent refresh calls are coalesced, and authenticated requests are retried at most once after a successful refresh.

## Catalogue and discovery

| Frontend operation | HTTP method | Path | Request behavior |
|---|---|---|---|
| List catalogue | GET | `/movies` | Keyset pagination; supports `limit`, `cursor`, `genre`, and `media_type` |
| Catalogue facets | GET | `/catalogue/facets` | Returns only media types and genres present in the catalogue |
| Movie/series detail | GET | `/titles/{media_type}/{serial_number}` | Public canonical route lookup |
| Legacy title lookup | GET | `/movies/{title_id}` | Used only for legacy route resolution |
| Search | GET | `/search` | Query parameters `q` and `limit` |

Public routes use the media-scoped permanent serial number. `title_id` is the immutable internal identity used for ratings, watchlists, interactions, cache keys, and React keys. Neither identifier nor provider identifiers should be rendered as visible UI copy. Render `display_title` for user-facing title text.

Catalogue cursors are opaque and must be passed back unchanged. A `409` during continuation means the catalogue order/version changed; discard the stale cursor and restart from the first page. Do not substitute offset pagination.

## Personalization and activity

| Frontend operation | HTTP method | Path | Request behavior |
|---|---|---|---|
| Grouped personalized home | GET | `/home/{user_id}` | Bearer-authenticated owner request; supports `k` and optional `genres` |
| Continue home rows | GET | `/home/{user_id}/more` | Bearer-authenticated; requires the opaque `cursor` from the previous response |
| Ranked recommendations | GET | `/recommendations` | Bearer-authenticated; user identity derived from token; supports `k` |
| User preferences | GET | `/users/me/preferences` | Bearer-authenticated; returns defaults when no row exists |
| Update preferences | PUT | `/users/me/preferences` | Bearer-authenticated; genre, adult, year and runtime controls |
| Record interaction | POST | `/interactions` | JSON with `title_id`, `event_type`, `value`, and optional metadata |
| Submit/update rating | POST | `/ratings` | JSON with `title_id`, `rating`, and `relevance` |
| Read rating history | GET | `/users/{user_id}/history` | Bearer-authenticated owner request; bounded `limit` |
| Read watchlist | GET | `/watchlist` | Bearer-authenticated |
| Add watchlist item | POST | `/watchlist/{title_id}` | Bearer-authenticated |
| Remove watchlist item | DELETE | `/watchlist/{title_id}` | Bearer-authenticated |

The dedicated `/recommendations` page uses `/recommendations`, which derives identity from the access token. The home page uses `/home/{user_id}` for its grouped rows; the backend enforces ownership for this compatibility route. Recommendation items are already hydrated with canonical movie metadata by the backend. The frontend must not re-rank them or interpret `score` as a calibrated probability.

Visible recommendation cards record deduplicated `impression` events. Explicit feedback records `like` or `dislike` using `/interactions`. These event types are accepted by the backend's interaction schema and influence the backend's interaction-aware recommendation history. Ratings and watchlist changes invalidate both the grouped home and dedicated recommendation query caches.

## Error and retry behavior

| Status | Frontend handling |
|---|---|
| 401 | Attempt one refresh for eligible authenticated requests; clear the local session if refresh fails |
| 403 | Display an access-denied state; do not retry |
| 404 | Display title/resource not found |
| 409 | Restart catalogue pagination when the cursor/order version is stale; show conflict feedback for other conflicts |
| 422 | Display field validation errors where available |
| 429 | Respect `Retry-After`; avoid immediate repeat submissions |
| 503 | Explain temporary model/service unavailability and provide catalogue fallback |

Writes are not blindly retried. The frontend must not assume a failed network response means the server did not commit a write.

## Account recovery and email delivery

The backend exposes `POST /auth/password/forgot`, `POST /auth/password/reset`, `POST /auth/email/verification/request` and `POST /auth/email/verify`. Public frontend pages consume them at `/forgot-password`, `/reset-password` and `/verify-email`, and the profile page can request a new confirmation link. Forgot-password responses stay generic so account existence is not disclosed. These endpoints return `503` until SMTP is configured, and the UI reports temporary unavailability without exposing delivery details. The profile page also supports profile editing, preferences and active-session management through existing endpoints.
