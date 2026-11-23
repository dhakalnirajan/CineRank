import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../src/features/auth/AuthProvider";
import type { Movie, User } from "../src/types/api";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui: ReactElement,
  { route = "/" }: { route?: string } = {},
) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function renderRoutes(
  routes: ReactElement,
  initialEntries: string[] = ["/"],
) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>{routes}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const testUser: User = {
  id: 1,
  username: "ada",
  email: "ada@example.com",
  email_verified: true,
  avatar_url: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

export function makeMovie(overrides: Partial<Movie> = {}): Movie {
  return {
    title_id: "title_fixture_000000000000000000000000000",
    serial_number: "000001",
    media_type: "movie",
    movielens_id: null,
    tmdb_id: null,
    imdb_id: null,
    title: "Fixture Film",
    genres: "Drama|Mystery",
    year: 2025,
    overview: "A fixture overview supplied by the backend.",
    poster_path: null,
    backdrop_path: null,
    popularity: 12.5,
    vote_average: 8.4,
    vote_count: 1200,
    runtime: 112,
    directors_json: '["Ada Director"]',
    cast_json: '[{"name":"Grace Hopper","character":"Self"}]',
    source: "catalogue",
    ...overrides,
  };
}
