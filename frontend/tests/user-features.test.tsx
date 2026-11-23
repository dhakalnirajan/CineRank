import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../src/api/config";
import { tokenStore } from "../src/api/token";
import { useTitleClick } from "../src/features/interactions/useInteraction";
import { RatingForm } from "../src/features/ratings/RatingForm";
import { WatchlistButton } from "../src/features/watchlist/WatchlistButton";
import HistoryPage from "../src/pages/HistoryPage";
import {
  jsonResponse,
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

describe("rating submission", () => {
  it("posts the personal rating with backend relevance and shows saved state", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url.endsWith("/ratings")) {
        return Promise.resolve(
          jsonResponse({
            id: 1,
            user_id: testUser.id,
            title_id: "title_rating",
            rating: 4.5,
            relevance: 1,
            timestamp: "2026-01-01T00:00:00Z",
            is_implicit: false,
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<RatingForm titleId="title_rating" initialRating={null} />);

    fireEvent.change(screen.getByLabelText("Your rating from 0.5 to 5 stars"), {
      target: { value: "4.5" },
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Save rating" }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    const ratingCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).endsWith("/ratings"),
    );
    expect(JSON.parse(String(ratingCall?.[1]?.body))).toEqual({
      title_id: "title_rating",
      rating: 4.5,
      relevance: 1,
    });
  });
});

describe("watchlist", () => {
  it("adds and removes a title through the real endpoints", async () => {
    const user = userEvent.setup();
    tokenStore.set("valid-token");
    let saved = false;

    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url === `${API_BASE_URL}/watchlist` && method === "GET") {
        return Promise.resolve(
          jsonResponse(
            saved
              ? [
                  {
                    created_at: "2026-01-01T00:00:00Z",
                    title: {
                      title_id: "title_watchlist",
                      media_type: "movie",
                      movielens_id: null,
                      tmdb_id: null,
                      imdb_id: null,
                      title: "Saved Film",
                      genres: "Drama",
                      year: 2025,
                      overview: null,
                      poster_path: null,
                      backdrop_path: null,
                      popularity: 1,
                      vote_average: null,
                      vote_count: null,
                      runtime: null,
                      directors_json: null,
                      cast_json: null,
                      source: "catalogue",
                    },
                  },
                ]
              : [],
          ),
        );
      }
      if (url.endsWith("/watchlist/title_watchlist") && method === "POST") {
        saved = true;
        return Promise.resolve(
          jsonResponse({ status: "saved", title_id: "title_watchlist" }, 201),
        );
      }
      if (url.endsWith("/watchlist/title_watchlist") && method === "DELETE") {
        saved = false;
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<WatchlistButton titleId="title_watchlist" />);

    await user.click(await screen.findByRole("button", { name: "Add to watchlist" }));
    expect(await screen.findByRole("button", { name: "In watchlist" })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        (call) => call[1]?.method === "POST" && String(call[0]).endsWith("/title_watchlist"),
      ),
    ).toBe(true);

    await user.click(screen.getByRole("button", { name: "In watchlist" }));
    expect(await screen.findByRole("button", { name: "Add to watchlist" })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        (call) => call[1]?.method === "DELETE" && String(call[0]).endsWith("/title_watchlist"),
      ),
    ).toBe(true);
  });
});

describe("interaction recording", () => {
  it("records one click event even when two subscribers render the same title", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url.endsWith("/interactions")) {
        return Promise.resolve(
          jsonResponse({
            status: "recorded",
            title_id: "title_interaction_unique",
            event_type: "click",
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    function ClickProbe() {
      useTitleClick("title_interaction_unique");
      return null;
    }

    renderWithProviders(
      <>
        <ClickProbe />
        <ClickProbe />
      </>,
    );

    await waitFor(() => {
      const interactions = fetchMock.mock.calls.filter((call) =>
        String(call[0]).endsWith("/interactions"),
      );
      expect(interactions).toHaveLength(1);
    });

    const call = fetchMock.mock.calls.find((entry) =>
      String(entry[0]).endsWith("/interactions"),
    );
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      title_id: "title_interaction_unique",
      event_type: "click",
      value: 1,
    });
  });
});

describe("rating history", () => {
  it("renders the actual ratings returned for the signed-in owner", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url.includes("/users/1/history")) {
        return Promise.resolve(
          jsonResponse({
            user_id: 1,
            count: 1,
            items: [
              {
                title_id: "title_history",
                serial_number: "000222",
                media_type: "movie",
                title: "History Film",
                rating: 4.5,
                timestamp: "2026-01-02T00:00:00Z",
              },
            ],
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<HistoryPage />, { route: "/history" });

    expect(await screen.findByText("History Film")).toBeInTheDocument();
    expect(screen.getByText("4.5")).toBeInTheDocument();
    expect(screen.getByText("History Film").closest("a")).toHaveAttribute(
      "href",
      "/movie/000222/",
    );
  });
});
