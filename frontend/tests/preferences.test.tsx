import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { tokenStore } from "../src/api/token";
import PreferencesPage from "../src/pages/PreferencesPage";
import { jsonResponse, renderWithProviders, testUser } from "./test-utils";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  tokenStore.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  tokenStore.clear();
  vi.unstubAllGlobals();
});

describe("recommendation preferences", () => {
  it("loads persisted controls and saves explicit preferences", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return Promise.resolve(jsonResponse(testUser));
      if (url.endsWith("/users/me/preferences") && init?.method !== "PUT") {
        return Promise.resolve(jsonResponse({
          preferred_genres: ["Drama"], excluded_genres: [], include_adult: false,
          min_year: null, max_runtime: null, updated_at: null,
        }));
      }
      if (url.endsWith("/catalogue/facets")) {
        return Promise.resolve(jsonResponse({
          media_types: [{ value: "movie", count: 20 }],
          genres: [{ value: "Drama", count: 10 }, { value: "Comedy", count: 8 }],
        }));
      }
      if (url.endsWith("/users/me/preferences") && init?.method === "PUT") {
        return Promise.resolve(jsonResponse(JSON.parse(String(init.body))));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<PreferencesPage />, { route: "/preferences" });
    await screen.findByRole("button", { name: "Prefer Drama" }, { timeout: 4000 });
    await waitFor(
      () =>
        expect(screen.getByRole("button", { name: "Prefer Drama" })).toHaveAttribute(
          "aria-pressed",
          "true",
        ),
      { timeout: 4000 },
    );
    expect(screen.getByRole("button", { name: "Exclude Drama" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "Prefer Comedy" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /include adult titles/i }));
    fireEvent.click(screen.getByRole("button", { name: /save preferences/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([input, init]) =>
        String(input).endsWith("/users/me/preferences") && init?.method === "PUT");
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        preferred_genres: ["Drama", "Comedy"],
        include_adult: true,
      });
    });
    expect(await screen.findByText(/preferences saved/i)).toBeInTheDocument();
  });
});
