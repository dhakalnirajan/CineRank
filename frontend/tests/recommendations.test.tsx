import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { tokenStore } from "../src/api/token";
import RecommendationsPage from "../src/pages/RecommendationsPage";
import type { RecommendationItem } from "../src/types/api";
import { jsonResponse, makeMovie, renderWithProviders, testUser } from "./test-utils";

const fetchMock = vi.fn<typeof fetch>();

const item: RecommendationItem = {
  ...makeMovie({
    title_id: "title_recommendation_test",
    serial_number: "000314",
    title: "Feedback Film",
    display_title: "Feedback Film",
    genres: "Drama|Mystery",
    year: 2024,
  }),
  score: 0.91,
  reason: "rank-fusion; sources=content+als",
};

beforeEach(() => {
  tokenStore.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  tokenStore.clear();
  vi.unstubAllGlobals();
});

describe("personalized recommendations", () => {
  it("loads the verified recommendation endpoint and renders hydrated titles", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return Promise.resolve(jsonResponse(testUser));
      if (url.includes("/recommendations")) {
        return Promise.resolve(jsonResponse({
          user_id: 1,
          model: "hybrid",
          k: 24,
          items: [item],
          generated_at: "2026-01-01T12:00:00Z",
        }));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<RecommendationsPage />, { route: "/recommendations" });

    expect(await screen.findByRole("link", { name: "Feedback Film" })).toBeInTheDocument();
    expect(screen.getByText("A ranked selection shaped by your ratings and activity. Your feedback helps refine future picks.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/recommendations?k=24"))).toBe(true);
  });

  it("sends explicit like feedback through the supported interaction contract", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return Promise.resolve(jsonResponse(testUser));
      if (url.includes("/recommendations")) {
        return Promise.resolve(jsonResponse({
          user_id: 1,
          model: "hybrid",
          k: 24,
          items: [item],
          generated_at: "2026-01-01T12:00:00Z",
        }));
      }
      if (url.endsWith("/interactions")) {
        return Promise.resolve(jsonResponse({
          status: "accepted",
          title_id: item.title_id,
          event_type: "like",
        }, 202));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<RecommendationsPage />, { route: "/recommendations" });
    fireEvent.click(await screen.findByRole("button", { name: "Recommend more like Feedback Film" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/interactions"));
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        title_id: item.title_id,
        event_type: "like",
        value: 1,
      });
    });
    expect(await screen.findByText("Thanks, that helps.")).toBeInTheDocument();
  });
});
