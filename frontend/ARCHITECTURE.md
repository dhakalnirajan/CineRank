# CineRank Frontend Architecture

Current as of the Netflix-inspired cinematic redesign.

## 1. Purpose and boundaries

CineRank is a movie and television discovery product. A FastAPI backend owns the catalogue, identity, ratings, watchlists, interactions, and recommendation models. The React frontend owns presentation, routing, search UX, and interaction collection.

Frontend responsibilities:

- Display catalogue, recommendations, search results, title detail, watchlist, ratings, history, profile, and active-session data.
- Own navbar search UX, user identity presentation, and page chrome.
- Collect meaningful, deduplicated interaction events.
- Never rank, filter, or invent catalogue records.
- Never play media. Interaction endpoints are logged only.

The frontend is a static single-page app served from a CDN or static host. It calls `VITE_API_BASE_URL` directly over HTTPS. There is no proxy layer inside the frontend build.

## 2. Entry points and routing

- `frontend/src/app/App.tsx` is the root. It declares the router, top-level route guards, and the app shell.
- `frontend/src/app/App.tsx` defines the route map: Home, Explore, Search, Recommendations, Watchlist, History, Profile, title detail routes, account routes, and catch-all 404.
- Public title routes use the permanent serial number pattern `/movie/{serial}/` and `/tv/{serial}/`. Those routes resolve the serial to `title_id` through the backend before any protected work.
- Protected routes use route guards that check authentication state and redirect to login with a return path on failure.

## 3. State architecture

- TanStack Query owns all server state: account, catalogue pages, search, title details, recommendations, watchlist, history, and model info.
- Query keys are centralized and include filters, cursors, and user identity where relevant.
- Authentication-dependent queries stay disabled until `/auth/me` resolves.
- Local state lives in components only: search query text, scroll state, popover open state, active keyboard row, form fields, and load-more accumulation.
- There is no Zustand, Redux, or context-based client state store beyond auth and theme.

## 4. Auth architecture

- `frontend/src/features/auth/AuthProvider.tsx` provides `useAuth()` returning `status` and `user`.
- Status values: `loading`, `authenticated`, `anonymous`, `error`.
- The header renders one structure for every status. Search stays visible for all statuses; the right-hand auth zone shows the compact account avatar when authenticated, the sign-in controls when anonymous, and a fixed-size placeholder while the session is loading or unresolved.
- Login uses `POST /auth/token` form-encoded `username` and `password`.
- Access tokens are kept in memory only. A non-sensitive `cinerank.has_session` hint in local storage decides whether to attempt a refresh on startup; the refresh token itself is never readable by JavaScript.
- The client calls `POST /auth/refresh` with the HttpOnly cookie when a session hint exists, keeps one in-flight refresh promise, and retries an authenticated request once after a 401 before clearing the session.
- Logout posts to `POST /auth/logout` with the cookie, then clears the memory token, query cache, session hint, and server session state.
- The token is attached as a bearer token to protected calls and cleared on 401.

## 5. API architecture

- One client module owns base URL, headers, serialization, timeouts, cancellation, and error normalization.
- Feature modules expose typed functions for verified endpoints only.
- `frontend/src/api/endpoints.ts` exports `api.search(query, limit, signal)` and related helpers.
- Search contract: `GET /api/v1/search?q=...&limit=...` returns `SearchResponse { query, count, results: Movie[] }`.
- `Movie` fields used in the UI include `display_title`, `poster_path`, `vote_average`, `year`, `media_type`, `genres`, and `title`.
- The frontend never renders `title_id`, `serial_number`, or provider IDs.

## 6. Navbar architecture

File: `frontend/src/components/navigation/Header.tsx`. Exported component: `Header`.

Responsibilities:

- Own navbar presentation and the three-zone layout.
- Own navbar search query state and the live search TanStack Query call.
- Own auth presentation for signed-in and signed-out states.
- Drive the compact search field and the floating results popover through `SearchInput`.

### 6.1 Layout

The navbar is a fixed bar with height `var(--header-height)` (72px) and a translucent dark surface. It is rendered once by `AppShell` and reused by `AuthLayout`, so app routes and auth routes share the same structure.

Three horizontal zones inside the `.page-shell` container:

1. Brand + primary nav on the left, `shrink-0`.
2. Compact search in the middle, flex-1 with a capped width, always rendered.
3. Auth controls on the right, `shrink-0`, with a reserved minimum width on desktop so the search zone does not move between auth states.

Non-home pages offset their content by `var(--header-height)`. The home page keeps its hero underneath the transparent bar.

Primary nav items come from `frontend/src/components/navigation/navItems.ts`:

- Home (`/`)
- Explore (`/explore`)
- Search (`/search`)
- Watchlist (`/watchlist`, auth-gated)

`MobileNav` maps the same list and keeps one slot per entry. When no session is present, the auth-gated slot becomes a `Sign in` link to `/login`. The bottom bar therefore keeps four equal columns before and after the session resolves instead of reflowing.

### 6.2 Surface states

- On the home page above the fold, the bar is transparent with a gradient-from-black surface so the hero shows through.
- Once scrolled or on every other route, including login and register, the bar becomes solid dark with a subtle border and backdrop blur.
- The bar stays fixed on every route, so navigation never changes its position or height.

### 6.3 Search architecture

Navbar search is a scaled-down `SearchInput` rendered inside the header.

`Header` owns:

- `query` text state.
- The TanStack Query search call to `api.search(...)`.
- `hits`, `moreAvailable`, `loading`, and `open` state.
- Keyboard and clear handling for the input.

`SearchInput` receives:

- `value`, `onChange`, `onClear`, `onKeyDown`
- `loading`, `hits`, `moreAvailable`
- `open`, `onClose`

It does not own search or refetch logic. That keeps a single source of truth for navbar search and avoids double-fetching. Result rows and the full-results action navigate to `/{media_type}/{serial_number}` and `/search?q=...` through the router, and the component never gates its own render on auth or a mount ref.

Auth does not control whether the search field exists. Only the popover contents depend on the current query.

## 7. Navbar search UX

### 7.1 Input presentation

- Single leading magnifying-glass icon.
- Single internal clear button that appears only when text is present; the native search cancel control is suppressed by using a text input with search input mode.
- No stray icons outside the input.
- Compact height with increased padding, capped width, and rounded corners.

### 7.2 Popover behavior

- Typing opens a floating popover anchored directly beneath the input.
- The navbar does not blur or hide when the popover opens.
- The screen does not become modal; the popover is a listbox-style overlay.

### 7.3 Popover content

Each result row shows:

- Poster thumbnail.
- Normalized title using `display_title`, not raw database title order.
- Genre/type.
- Rating.
- Year.
- A bottom action row that links to the full search results.

The popover never exposes raw database IDs in visible text.

### 7.4 Keyboard interaction

- Up/Down arrow keys move through results.
- Enter selects the active row.
- Escape closes the popover.
- Outside click dismisses the popover.

### 7.5 Empty and loading states

- While loading, the popover shows skeleton rows.
- When there are no results, the popover shows an empty state.
- The full-results action is shown when more results are available.

### 7.6 Poster fallback

Poster thumbnails use a deterministic typographic fallback when artwork is missing. The fallback is a dark red-to-amber gradient with initials, independent of title text content, and never derived from ID data.

## 8. User identity and avatar

Files: `frontend/src/components/navigation/Header.tsx` and `frontend/src/components/navigation/AccountMenu.tsx`.

Signed-in presentation:

- A fixed `36px` circular avatar button with `border-radius: 50%`.
- A generic person icon, not username initials. No visible username in the navbar.
- Warm red gradient surface with a subtle ring.
- The button sits in normal flow inside a `relative` container. It does not change the header's height or width.
- Click, Enter, or Space toggles the account menu. Hover does not open or close it, so the panel persists while the pointer moves away.
- The panel is absolutely positioned below the avatar, so the header footprint stays fixed.
- The panel shows the username and email once, then Profile, Watchlist, Rating history, and Sign out.
- Escape closes the panel and returns focus to the avatar. An outside pointer press closes it. Route changes close it.

The panel starts directly below the avatar with internal top padding, keeping a clean visual gap without changing the header's physical footprint.

Signed-out presentation:

- “Sign in” ghost button.
- “Join CineRank” primary button.

While auth is loading or unresolved, the right-hand zone keeps its width with a small pulsing placeholder so the search field and nav links do not shift.

### 8.1 Profile page composition

File: `frontend/src/pages/ProfilePage.tsx`.

- A contained identity card with a short cinematic banner, overlapping avatar, username, email, and Sign out action.
- Statistics render as three equal cards: Titles rated, Watchlist, and Member since. Values use tabular numerals and a loading dash while data resolves.
- Rating history and watchlist share one poster-based card grid. Cards keep a 2:3 media frame, title-first hierarchy, subdued date metadata, a genre chip, and a rating badge where applicable.
- The grid uses two columns on small screens, then three, four, and five columns as width permits.
- History cards use the existing typographic artwork fallback because the history response does not carry poster paths.

There is no settings route in the product, so the account menu does not link to a placeholder settings screen.

## 8. Error pages

- `frontend/src/components/feedback/ErrorPage.tsx` is the shared cinematic layout for 404 and runtime errors.
- `NotFoundPage` uses it for missing routes.
- `ErrorBoundary` uses it for unhandled render errors, with reload and home actions.
- Error copy is consumer-facing and avoids internal identifiers or implementation details.

## 9. Footer architecture

File: `frontend/src/components/layout/Footer.tsx`. Exported component: `Footer`.

Responsibilities:

- Provide the page-chrome footer aligned with `.page-shell`.
- Two-zone grid layout.
- Brand and attribution zone on the left.
- Navigation columns on the right.

### 9.1 Layout

- Background is the site's near-black footer tone.
- Top section uses a responsive grid with brand, Explore, Community, and Legal and Attribution columns.
- Explore links to the catalogue and genre guide. Community shows account links when signed in and sign-in links when signed out.
- Legal and Attribution carries the artwork and metadata credit instead of the brand tagline.
- The footer bottom strip contains the copyright line and is separated by a divider from the upper footer.
- The copyright strip is left-aligned and not gated behind authentication.

### 9.2 Content rules

- No cliché filler copy.
- No auth-gated copyright text.
- Navigation links are purposeful, not decorative.

## 10. Startup intro and loading

File: `frontend/src/features/intro/IntroScreen.tsx`.

- The intro renders once per browser session. `sessionStorage` key `cinerank:intro-seen` suppresses repeat plays until a new session starts.
- A fixed black stage runs a red ribbon sweep, then the CineRank mark resolves, then the wordmark fades in. The full sequence is 2.8 seconds.
- With `prefers-reduced-motion: reduce`, the ribbon and flare are removed, the lockup is static, and the stage clears after 1.1 seconds.
- The audio cue is synthesized with the Web Audio API: a filtered noise sweep and a low-to-high two-tone sting. Sound is enabled by default with a visible mute control. Browser autoplay policy can hold playback until a user gesture, and unmuting retries it.
- There is no skip control, by product decision.
- `App` renders the intro above the router, so session checks, lazy route loading, and catalogue requests continue underneath it. Once it clears, any still-pending route or session work shows the branded `PageLoader`.

## 11. Shared primitives

- `frontend/src/utils/cn.ts` merges Tailwind classes safely.
- `frontend/src/components/ui/Button.tsx` exposes `buttonClasses(...)` for button variants.
- `frontend/src/components/navigation/Logo.tsx` renders the compact and full brand mark.
- `frontend/src/components/navigation/navItems.ts` defines the primary nav list.
- Design tokens live in `frontend/src/styles/global.css`, including the accent color, type scale, and `.page-shell` layout.

## 12. Dedicated recommendations experience

- `/recommendations` is protected and calls the canonical `GET /api/v1/recommendations?k=24` endpoint. The backend derives identity from the access token.
- The response is typed as `RecommendationResponse`; each item is already hydrated from the canonical catalogue row by the backend.
- The page renders the backend's ranked items and friendly reason text. It does not reinterpret model scores as probabilities or calculate a second ranking in the browser.
- Recommendation impressions are recorded only when a card becomes visible, using the existing deduplicated interaction observer.
- Positive and negative feedback use the supported `POST /api/v1/interactions` contract with `event_type` equal to `like` or `dislike`. Successful feedback invalidates recommendation and home queries so the next feed reflects the backend's interaction-aware history.
- Ratings, watchlist changes, title clicks, and recommendation feedback invalidate the relevant personalized query caches.
- The home page links its `For you` row to the dedicated recommendations page.

## 13. Backend capabilities intentionally not fabricated

- Explicit recommendation preferences are supported by `GET/PUT /users/me/preferences` and the `/preferences` page.
- `/forgot-password`, `/reset-password` and `/verify-email` call the backend account-recovery endpoints. The profile page shows unverified email state and can resend a confirmation link. Delivery requires SMTP configuration; the UI reports a temporary error when delivery is unavailable.
- Account editing and active-session review/revocation are available through the existing profile page and verified endpoints.
- The backend's `GET /recommendations` response is a separate ranked list from the grouped `/home/{user_id}` response. The frontend uses each for its intended purpose. The legacy `/recommend/{user_id}` endpoint remains for compatibility only.

## 14. Verification commands

From the repo root:

- Typecheck: `cd frontend && npm run typecheck`
- Lint: `cd frontend && npm run lint`
- Tests: `cd frontend && npm test`
- Production build: `cd frontend && npm run build`

All four must pass before frontend changes are considered complete.

## 15. Current verification status

- Clean lockfile install passed after clearing generated `node_modules`.
- `npm run typecheck`, `npm run lint`, all 82 Vitest tests and `npm run build` passed.
- `npm audit` and `npm audit --omit=dev --audit-level=high` both reported 0 vulnerabilities after upgrading Vitest to 5.1.1.
- Backend regression suite: 67 tests passed with 2 live-Redis tests skipped.
- Docker image builds, browser E2E, accessibility auditing and live PostgreSQL deployment were not run.
- The full executed matrix and blockers are recorded in the root `PRODUCTION_READINESS.md`.

## Recommendation preferences

The protected `/preferences` route manages explicit user controls through `GET/PUT /users/me/preferences`. It reads genre choices from `/catalogue/facets`, stores preferred and excluded genres, adult-content inclusion, minimum year and maximum runtime, and invalidates personalized home/recommendation queries after save. The backend applies these constraints during candidate selection; the frontend does not re-rank recommendations.

## Canonical recommendation identity

The dedicated recommendations page calls `GET /recommendations?k=...`. The backend derives the user ID from the validated access token. The legacy `/recommend/{user_id}` route remains for backward compatibility but should not be used by new frontend features.
