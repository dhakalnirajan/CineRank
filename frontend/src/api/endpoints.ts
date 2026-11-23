import type {
  CatalogueFacets,
  HomeResponse,
  InteractionEventType,
  Movie,
  MoviePage,
  RatingResponse,
  RecommendationPage,
  RecommendationResponse,
  RegisterPayload,
  SearchResponse,
  SimilarTitlesResponse,
  UpdateProfilePayload,
  TokenResponse,
  User,
  UserHistory,
  UserSession,
  UserPreferences,
  WatchlistEntry,
  WatchedEntry,
} from "../types/api";
import { apiRequest } from "./client";

type QueryValue = string | number | undefined | null;

function toQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export interface CatalogueParams {
  limit?: number;
  cursor?: string | null;
  genre?: string | null;
  mediaType?: "movie" | "tv" | null;
}

export const api = {
  register(payload: RegisterPayload): Promise<User> {
    return apiRequest<User>("/auth/register", {
      method: "POST",
      auth: false,
      body: payload,
    });
  },

  login(username: string, password: string): Promise<TokenResponse> {
    const form = new URLSearchParams({ username, password });
    return apiRequest<TokenResponse>("/auth/token", {
      method: "POST",
      auth: false,
      form,
    });
  },

  me(signal?: AbortSignal): Promise<User> {
    return apiRequest<User>("/auth/me", { signal });
  },

  updateProfile(userId: number, payload: UpdateProfilePayload): Promise<User> {
    return apiRequest<User>(`/users/${userId}`, {
      method: "PATCH",
      body: payload,
    });
  },

  requestEmailVerification(): Promise<{ status: string }> {
    return apiRequest<{ status: string }>("/auth/email/verification/request", {
      method: "POST",
    });
  },

  verifyEmail(token: string): Promise<User> {
    return apiRequest<User>("/auth/email/verify", {
      method: "POST",
      auth: false,
      body: { token },
    });
  },

  forgotPassword(email: string): Promise<{ status: string }> {
    return apiRequest<{ status: string }>("/auth/password/forgot", {
      method: "POST",
      auth: false,
      body: { email },
    });
  },

  resetPassword(token: string, newPassword: string): Promise<{ status: string }> {
    return apiRequest<{ status: string }>("/auth/password/reset", {
      method: "POST",
      auth: false,
      body: { token, new_password: newPassword },
    });
  },

  uploadAvatar(file: File): Promise<User> {
    const formData = new FormData();
    formData.append("image", file);
    return apiRequest<User>("/users/me/avatar", { method: "POST", formData });
  },

  getPreferences(signal?: AbortSignal): Promise<UserPreferences> {
    return apiRequest<UserPreferences>("/users/me/preferences", { signal });
  },

  updatePreferences(payload: Omit<UserPreferences, "updated_at">): Promise<UserPreferences> {
    return apiRequest<UserPreferences>("/users/me/preferences", { method: "PUT", body: payload });
  },

  sessions(signal?: AbortSignal): Promise<UserSession[]> {
    return apiRequest<UserSession[]>("/auth/sessions", { signal });
  },

  revokeSession(sessionId: string): Promise<void> {
    return apiRequest<void>(`/auth/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  },

  logoutAll(): Promise<{ status: string; revoked: number }> {
    return apiRequest("/auth/logout-all", { method: "POST" });
  },

  addToWatched(titleId: string): Promise<{ status: string; title_id: string }> {
    return apiRequest(`/watched/${encodeURIComponent(titleId)}`, { method: "POST" });
  },

  watchedEntry(titleId: string): Promise<WatchedEntry> {
    return apiRequest<WatchedEntry>(`/watched/${encodeURIComponent(titleId)}`, { method: "GET" });
  },

  removeFromWatched(titleId: string): Promise<void> {
    return apiRequest<void>(`/watched/${encodeURIComponent(titleId)}`, { method: "DELETE" });
  },

  logoutOtherSessions(): Promise<{ status: string; revoked: number }> {
    return apiRequest("/auth/logout-others", { method: "POST" });
  },

  logout(): Promise<{ status: string }> {
    return apiRequest<{ status: string }>("/auth/logout", {
      method: "POST",
      auth: false,
    });
  },

  listMovies(params: CatalogueParams, signal?: AbortSignal): Promise<MoviePage> {
    const query = toQuery({
      limit: params.limit,
      cursor: params.cursor,
      genre: params.genre,
      media_type: params.mediaType,
    });
    return apiRequest<MoviePage>(`/movies${query}`, { signal });
  },

  getTitle(mediaType: "movie" | "tv", serialNumber: string, signal?: AbortSignal): Promise<Movie> {
    return apiRequest<Movie>(
      `/titles/${mediaType}/${encodeURIComponent(serialNumber)}`,
      { signal },
    );
  },

  getMovie(titleId: string, signal?: AbortSignal): Promise<Movie> {
    return apiRequest<Movie>(`/movies/${encodeURIComponent(titleId)}`, { signal });
  },

  similarTitles(
    mediaType: "movie" | "tv",
    serialNumber: string,
    limit = 10,
    signal?: AbortSignal,
  ): Promise<SimilarTitlesResponse> {
    return apiRequest<SimilarTitlesResponse>(
      `/titles/${mediaType}/${encodeURIComponent(serialNumber)}/similar${toQuery({ limit })}`,
      { signal },
    );
  },

  catalogueFacets(signal?: AbortSignal): Promise<CatalogueFacets> {
    return apiRequest<CatalogueFacets>("/catalogue/facets", { signal });
  },

  search(query: string, limit = 24, signal?: AbortSignal): Promise<SearchResponse> {
    return apiRequest<SearchResponse>(`/search${toQuery({ q: query, limit })}`, { signal });
  },

  rate(titleId: string, rating: number): Promise<RatingResponse> {
    return apiRequest<RatingResponse>("/ratings", {
      method: "POST",
      body: { title_id: titleId, rating, relevance: 1.0 },
    });
  },

  recordInteraction(
    titleId: string,
    eventType: InteractionEventType,
    value = 1,
  ): Promise<{ status: string; title_id: string; event_type: string }> {
    return apiRequest("/interactions", {
      method: "POST",
      body: { title_id: titleId, event_type: eventType, value, metadata: null },
    });
  },

  history(userId: number, limit = 100, signal?: AbortSignal): Promise<UserHistory> {
    return apiRequest<UserHistory>(
      `/users/${userId}/history${toQuery({ limit })}`,
      { signal },
    );
  },

  watchlist(signal?: AbortSignal): Promise<WatchlistEntry[]> {
    return apiRequest<WatchlistEntry[]>("/watchlist", { signal });
  },

  addToWatchlist(titleId: string): Promise<{ status: string; title_id: string }> {
    return apiRequest(`/watchlist/${encodeURIComponent(titleId)}`, { method: "POST" });
  },

  removeFromWatchlist(titleId: string): Promise<void> {
    return apiRequest<void>(`/watchlist/${encodeURIComponent(titleId)}`, { method: "DELETE" });
  },

  home(userId: number, k = 12, signal?: AbortSignal): Promise<HomeResponse> {
    return apiRequest<HomeResponse>(`/home/${userId}${toQuery({ k })}`, { signal });
  },

  homeMore(
    userId: number,
    k: number,
    cursor: string,
    signal?: AbortSignal,
  ): Promise<RecommendationPage> {
    return apiRequest<RecommendationPage>(
      `/home/${userId}/more${toQuery({ k, cursor })}`,
      { signal },
    );
  },

  recommendations(k = 24, signal?: AbortSignal): Promise<RecommendationResponse> {
    // Canonical route derives user identity from the validated access token.
    return apiRequest<RecommendationResponse>(`/recommendations${toQuery({ k })}`, { signal });
  },

};
