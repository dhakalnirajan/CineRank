# CineRank - High Level System Documentation

## Overview

CineRank is a movie and television recommendation product that provides personalized content recommendations to users. The system consists of a backend authority for catalogue data, identity, authentication, recommendations, and persistence, and a frontend authority for presentation, navigation, interaction, and client-side UX.

## Architecture

### System Boundaries

- **Backend** (`backend/`): Authority for catalogue data, identity, authentication, recommendations, and persistence.
- **Frontend** (`frontend/`): Authority for presentation, navigation, interaction, and client-side UX.
- **Database**: SQLite (development) / PostgreSQL (production) for persistence.
- **External Data**: CSV, parquet, and JSON datasets imported into the database.

### Core Data Flow

1. **User Authentication**: Form-encoded `POST /auth/token` login with bearer token authentication
2. **Catalogue Access**: Keyset-paginated `GET /home/{user_id}` and `GET /watchlist` endpoints
3. **Recommendations**: `GET /recommendations` using bearer token identity
4. **User Interactions**: Rating, watchlist, and watch history via mutation endpoints

### Key APIs

| Endpoint | Description |
|----------|-------------|
| `POST /auth/token` | Login with form-encoded credentials |
| `GET /auth/me` | Get current user information |
| `GET /home/{user_id}` | Personalized home page with recommendations |
| `GET /watchlist` | User's watchlist |
| `GET /users/{user_id}/history` | User's rating history |
| `GET /recommendations` | Personalized recommendations |
| `POST /watchlist` | Add/remove from watchlist |
| `PUT /users/me/preferences` | Update user preferences |

### Data Sources

- **Seed Data**: 5,750 MovieLens titles from `backend/data/seeds/catalogue_movielens.jsonl`
- **External Datasets**: Imported from `backend/data/external/`:
  - `9000plus.csv` - Additional movie metadata (4.2MB)
  - `IMDB Dataset.csv` - IMDB movie data (66MB)
  - `TMDB-IMDB-Movies-Dataset.csv` - Merged TMDB/IMDB data (278MB)
  - `imdb-60k-dataset.csv` - 60K movie dataset (45MB)
  - `imdb-media.csv` - Detailed IMDB metadata (973MB)
  - `tv-details.parquet` - TV show data (214K shows)
  - `tvmaze/` - TVMaze show data (200 JSON files)
- **Database Migration**: Alembic-managed schema evolution

### Recommendation System

1. **Engine**: Weighted Reciprocal Rank Fusion (RRF) combining multiple ranking signals
2. **Inputs**: User preferences (genres, adult content, minimum year, maximum runtime)
3. **Output**: Ranked list of titles with display titles and reasons
4. **Cache**: Redis-backed distributed cache for recommendation results
5. **Versioning**: Sort versioning for cache invalidation on `409` response

### State Management

- **Watchlist Tab**: `useState<WatchlistTab>("watchlist")` controls filtering between "Watchlist" and "Watched" collections
- **Profile Tab**: `useState<ProfileTab>("history")` controls which panel renders ("history" or "watchlist")
- **Button Variants**: "default" for active tab, "ghost" for inactive

## Component Structure

### Frontend Pages

- **WatchlistPage**: Tab system filtering between "Watchlist" and "Watched"; conditional action buttons
- **ProfilePage**: Tab system at top controls Rating History and Saved Watchlist panels; CSS Grid layout
- **TitlePage**: Detail view for individual titles with watchlist/watch buttons
- **HomePage**: Personalized hero carousel and recommendation rows

### Key UI Patterns

- **CSS Grid Layout**: Profile page uses CSS Grid for card layout with standardized margins
- **Styled Cards**: Distinct typography with clear font weights; metadata separated from genre chips
- **Artwork Fallback**: Black canvas with red primary, white editorial type, gradient depth
- **Button System**: Primary/secondary variants with consistent sizing

### Backend Services

- **API Routes**: `/api/v1` base path configured via `VITE_API_BASE_URL`
- **Authentication**: Short-lived access JWT + rotating HttpOnly refresh sessions
- **Session Security**: Reuse detection, logout-all, CSRF protection, rate limiting
- **Data Import**: Alembic migrations, idempotent import scripts for external datasets
- **Preferences**: `GET/PUT /users/me/preferences` for explicit recommendation preferences

## Deployment

- **Development**: `npm run dev` (frontend) + `python run.sh` (backend)
- **Production Build**: `npm run build` (frontend) + `pytest` (backend tests)
- **Database Migrations**: `alembic upgrade head`
- **CORS**: Configured for Vite development origin

## Security

- **Authentication**: JWT access tokens + HttpOnly refresh session cookies
- **Session Management**: Short-lived access tokens, rotating refresh sessions, reuse detection
- **Ownership Checks**: Backend enforces ownership; frontend is never an auth boundary
- **Input Validation**: Defensive parsing of genres, directors_json, cast_json
- **Error Handling**: Calm error states; no architecture leaks in user-facing text
