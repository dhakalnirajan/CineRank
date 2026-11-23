export type MediaType = "movie" | "tv";

export type InteractionEventType =
  | "impression"
  | "click"
  | "play"
  | "complete"
  | "like"
  | "dislike"
  | "skip"
  | "rating"
  | "watched";

export interface User {
  id: number;
  username: string;
  email: string | null;
  email_verified: boolean;
  avatar_url: string | null;
  is_active: boolean;
  created_at: string;
}

export interface UpdateProfilePayload {
  username?: string;
  email?: string | null;
  current_password?: string;
  password?: string;
  avatar_url?: string | null;
}

export interface UserSession {
  id: string;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  user_agent: string | null;
  current: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Movie {
  title_id: string;
  serial_number: string;
  media_type: MediaType;
  movielens_id: number | null;
  tmdb_id: number | null;
  imdb_id: string | null;
  title: string;
  original_title?: string | null;
  display_title?: string;
  genres: string;
  year: number | null;
  overview: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  popularity: number;
  vote_average: number | null;
  vote_count: number | null;
  runtime: number | null;
  directors_json: string | null;
  cast_json: string | null;
  is_adult?: boolean;
  source: string;
}

export interface MoviePage {
  items: Movie[];
  next_cursor: string | null;
  catalogue_version: number;
}

export interface SearchResponse {
  query: string;
  count: number;
  results: Movie[];
}

export interface SimilarTitlesResponse {
  title_id: string;
  model: string;
  items: Movie[];
}

export interface RecommendationItem extends Movie {
  score: number;
  reason: string | null;
}

export interface HomeResponse {
  user_id: number;
  model: string;
  for_you: RecommendationItem[];
  popular: RecommendationItem[];
  recently_added: RecommendationItem[];
  genres: Record<string, RecommendationItem[]>;
  next_cursor: string | null;
  generated_at: string;
}

export interface RecommendationResponse {
  user_id: number;
  model: string;
  k: number;
  items: RecommendationItem[];
  generated_at: string;
}

export interface RecommendationPage {
  items: RecommendationItem[];
  next_cursor: string | null;
}

export interface RatingResponse {
  id: number;
  user_id: number;
  title_id: string;
  rating: number;
  relevance: number;
  timestamp: string;
  is_implicit: boolean;
}

export interface HistoryItem {
  title_id: string;
  serial_number: string;
  media_type: MediaType;
  title: string;
  display_title?: string;
  genres: string;
  rating: number;
  timestamp: string;
}

export interface UserHistory {
  user_id: number;
  count: number;
  items: HistoryItem[];
}

export interface WatchlistEntry {
  created_at: string;
  title: Movie;
}

export interface WatchedEntry {
  title_id: string;
  serial_number: string;
  media_type: MediaType;
  title: string;
  display_title?: string;
  genres: string;
  year: number | null;
  poster_path: string | null;
  backdrop_path: string | null;
  popularity: number;
  vote_average: number | null;
  vote_count: number | null;
  runtime: number | null;
  is_adult?: boolean;
}

export interface CatalogueFacet {
  value: string;
  count: number;
}

export interface CatalogueFacets {
  media_types: CatalogueFacet[];
  genres: CatalogueFacet[];
}

export interface RegisterPayload {
  username: string;
  email?: string;
  password: string;
}

export interface UserPreferences {
  preferred_genres: string[];
  excluded_genres: string[];
  include_adult: boolean;
  min_year: number | null;
  max_runtime: number | null;
  updated_at?: string | null;
}