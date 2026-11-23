import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { tokenStore } from "../src/api/token";
import HomePage from "../src/pages/HomePage";
import type { RecommendationItem } from "../src/types/api";
import {
  jsonResponse,
  makeMovie,
  renderWithProviders,
  testUser,
} from "./test-utils";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const heroItem: RecommendationItem = {
  ...makeMovie({
    title_id: "title_hero",
    serial_number: "000001",
    movielens_id: 123,
    title: "Hero Film",
    overview: "The synopsis comes from the hydrated recommendation response.",
    backdrop_path: "https://image.example/hero-backdrop.jpg",
    genres: "Drama",
    year: 2025,
  }),
  score: 0.83,
  reason: "rank-fusion; sources=popular+content",
};

const popularItem: RecommendationItem = {
  ...heroItem,
  title_id: "title_popular",
  title: "Popular Film",
  score: 0.61,
};

const genreItem: RecommendationItem = {
  ...heroItem,
  title_id: "title_genre",
  title: "Genre Film",
  score: 0.44,
};

describe("personalized home", () => {
  it("renders backend rows and continues to use real recommendation data", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url.includes("/home/1")) {
        return Promise.resolve(
          jsonResponse({
            user_id: 1,
            model: "hybrid",
            for_you: [heroItem],
            popular: [popularItem],
            genres: { genre_drama: [genreItem] },
            next_cursor: null,
            generated_at: "2026-01-01T00:00:00Z",
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<HomePage />);

    expect(await screen.findByText("Top pick for you")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Hero Film" })).toBeInTheDocument();
    expect(screen.getByText("The synopsis comes from the hydrated recommendation response.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/titles/movie/000001"))).toBe(false);
    expect(screen.getByText("For you")).toBeInTheDocument();
    expect(screen.getByText("Popular now")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More for you" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Drama").length).toBeGreaterThan(0);
    expect(screen.queryByText("0.83")).not.toBeInTheDocument();
  });

  it("explains an unavailable recommendation model without faking rows", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url.includes("/home/1")) {
        return Promise.resolve(
          jsonResponse({ detail: "No recommendation model is loaded" }, 503),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<HomePage />);

    expect(
      await screen.findByText("Your picks need a moment"),
    ).toBeInTheDocument();
    expect(screen.queryByText("For you")).not.toBeInTheDocument();
  });

  it("shows the empty recommendation state when every backend row is empty", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url.includes("/home/1")) {
        return Promise.resolve(
          jsonResponse({
            user_id: 1,
            model: "cold-start",
            for_you: [],
            popular: [],
            genres: {},
            next_cursor: null,
            generated_at: "2026-01-01T00:00:00Z",
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<HomePage />);

    expect(
      await screen.findByText("Your recommendations are still warming up"),
    ).toBeInTheDocument();
  });
});

describe("anonymous discovery home", () => {
  it("uses the public catalogue preview without inventing personalization", async () => {
    const preview = makeMovie({ title_id: "title_preview", title: "Preview Film" });
    fetchMock.mockImplementation((input) => {
      if (String(input).includes("/movies")) {
        return Promise.resolve(
          jsonResponse({
            items: [preview],
            next_cursor: null,
            catalogue_version: 1,
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<HomePage />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Find your next favorite.",
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Worth a look")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Preview Film" })).toBeInTheDocument();
    expect(screen.queryByText("Top pick for you")).not.toBeInTheDocument();
  });
});
