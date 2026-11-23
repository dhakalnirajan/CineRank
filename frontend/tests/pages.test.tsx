import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { tokenStore } from "../src/api/token";
import { MobileNav } from "../src/components/navigation/MobileNav";
import ExplorePage from "../src/pages/ExplorePage";
import LegacyTitlePage from "../src/pages/LegacyTitlePage";
import SearchPage from "../src/pages/SearchPage";
import TitlePage from "../src/pages/TitlePage";
import {
  jsonResponse,
  makeMovie,
  renderRoutes,
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

describe("catalogue browsing", () => {
  it("appends keyset pages and deduplicates repeated titles", async () => {
    const shared = makeMovie({ title_id: "title_shared", title: "Shared Film" });
    const first = makeMovie({ title_id: "title_first", title: "First Film" });
    const second = makeMovie({ title_id: "title_second", title: "Second Film" });

    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/movies")) {
        if (url.includes("cursor=cursor-page-2")) {
          return Promise.resolve(
            jsonResponse({
              items: [shared, second],
              next_cursor: null,
              catalogue_version: 1,
            }),
          );
        }
        return Promise.resolve(
          jsonResponse({
            items: [first, shared],
            next_cursor: "cursor-page-2",
            catalogue_version: 1,
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<ExplorePage />, { route: "/explore" });

    expect(await screen.findByRole("heading", { name: "First Film" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("heading", { name: "Second Film" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Shared Film" })).toHaveLength(1);
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes("cursor=cursor-page-2")),
    ).toBe(true);
  });

  it("restarts from the first page after a catalogue version conflict", async () => {
    const first = makeMovie({ title_id: "title_conflict", title: "Conflict Film" });
    let catalogueCalls = 0;

    fetchMock.mockImplementation((input) => {
      if (!String(input).includes("/movies")) {
        return Promise.resolve(jsonResponse({}));
      }
      catalogueCalls += 1;
      if (catalogueCalls === 2) {
        return Promise.resolve(
          jsonResponse({ detail: "Catalogue order changed; restart pagination" }, 409),
        );
      }
      return Promise.resolve(
        jsonResponse({
          items: [first],
          next_cursor: catalogueCalls === 1 ? "cursor-stale" : null,
          catalogue_version: catalogueCalls === 1 ? 1 : 2,
        }),
      );
    });

    renderWithProviders(<ExplorePage />, { route: "/explore" });

    expect(await screen.findByRole("heading", { name: "Conflict Film" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Load more" }));    expect(await screen.findByText(/this list changed/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(catalogueCalls).toBe(3));
    expect(screen.queryByText(/this list changed/i)).not.toBeInTheDocument();
  });

  it("hides unavailable media tabs and uses genre pills", async () => {
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/catalogue/facets")) {
        return Promise.resolve(
          jsonResponse({
            media_types: [{ value: "movie", count: 2 }],
            genres: [{ value: "Drama", count: 2 }],
          }),
        );
      }
      if (url.includes("/movies")) {
        return Promise.resolve(
          jsonResponse({ items: [], next_cursor: null, catalogue_version: 1 }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<ExplorePage />, { route: "/explore" });

    expect(await screen.findByRole("button", { name: "Drama" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Films" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "TV" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Search by title" })).not.toBeInTheDocument();
  });

  it("shows a loading skeleton before the catalogue resolves", () => {
    fetchMock.mockImplementation(() => new Promise<Response>(() => {}));
    renderWithProviders(<ExplorePage />, { route: "/explore" });

    expect(screen.getByLabelText("Loading titles")).toBeInTheDocument();
  });

  it("shows a retryable error state when the catalogue fails", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Upstream failure" }, 500));
    renderWithProviders(<ExplorePage />, { route: "/explore" });

    expect(await screen.findByText("We couldn't load these titles")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("search", () => {
  it("debounces input and renders backend results", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((input) => {
      if (String(input).includes("/search")) {
        return Promise.resolve(
          jsonResponse({ query: "Dune", count: 1, results: [makeMovie({ title: "Dune" })] }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<SearchPage />, { route: "/search" });

    expect(screen.getByText("Start with a genre")).toBeInTheDocument();
    expect(screen.getByText("Worth a look")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search films and series by title"), "Dune");

    expect(
      await screen.findByRole("heading", { name: "Dune" }, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes("q=Dune")),
    ).toBe(true);
  });

  it("shows a no-results state for an empty catalogue search", async () => {
    fetchMock.mockImplementation((input) => {
      if (String(input).includes("/search")) {
        return Promise.resolve(jsonResponse({ query: "zzz", count: 0, results: [] }));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<SearchPage />, { route: "/search?q=zzz" });

    expect(await screen.findByText('No results for "zzz"')).toBeInTheDocument();
  });
});

describe("title details", () => {
  it("renders verified metadata and handles optional artwork", async () => {
    const movie = makeMovie({
      title: "Backend Film",
      serial_number: "000321",
      poster_path: null,
      backdrop_path: null,
    });
    fetchMock.mockImplementation((input) => {
      if (String(input).includes("/titles/movie/000321")) {
        return Promise.resolve(jsonResponse(movie));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderRoutes(
      <Routes>
        <Route path="/movie/:serialNumber" element={<TitlePage mediaType="movie" />} />
      </Routes>,
      ["/movie/000321/"],
    );

    expect(await screen.findByRole("heading", { name: "Backend Film" })).toBeInTheDocument();
    expect(screen.getByText("A fixture overview supplied by the backend.")).toBeInTheDocument();
    expect(screen.getByText("Ada Director")).toBeInTheDocument();
    expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("8.4")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Artwork unavailable" })).toBeInTheDocument();
    expect(screen.queryByText("Serial number")).not.toBeInTheDocument();
    expect(screen.queryByText("000321")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Drama" })).toHaveAttribute(
      "href",
      "/explore?genre=Drama",
    );
    expect(screen.getByRole("link", { name: "Sign in to save" })).toBeInTheDocument();
  });

  it("shows the not-found state for a missing serial number", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Not found" }, 404));
    renderRoutes(
      <Routes>
        <Route path="/movie/:serialNumber" element={<TitlePage mediaType="movie" />} />
      </Routes>,
      ["/movie/999999/"],
    );

    expect(await screen.findByText("Title not found")).toBeInTheDocument();
  });

  it("redirects a legacy UUID URL to the canonical serial URL", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(makeMovie({ serial_number: "000654", title: "Legacy Film" })),
    );
    renderRoutes(
      <Routes>
        <Route path="/title/:titleId" element={<LegacyTitlePage />} />
        <Route path="/movie/:serialNumber" element={<h1>Canonical title route</h1>} />
      </Routes>,
      ["/title/title_fixture"],
    );

    expect(
      await screen.findByRole("heading", { name: "Canonical title route" }),
    ).toBeInTheDocument();
  });
});

describe("responsive navigation", () => {
  it("keeps anonymous navigation minimal on mobile", () => {
    tokenStore.clear();
    renderWithProviders(<MobileNav />);

    const navigation = screen.getByRole("navigation", { name: "Primary mobile" });
    expect(navigation).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Explore" })).toHaveAttribute("href", "/explore");
    expect(screen.getByRole("link", { name: "Search" })).toHaveAttribute("href", "/search");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: "For you" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Watchlist" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Profile" })).not.toBeInTheDocument();
  });

  it("shows saved destinations after sign in", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      if (String(input).endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      return Promise.resolve(jsonResponse({}));
    });

    const { unmount } = renderWithProviders(<MobileNav />);

    expect(await screen.findByRole("link", { name: "Watchlist" })).toHaveAttribute(
      "href",
      "/watchlist",
    );
    expect(await screen.findByRole("link", { name: "For you" })).toHaveAttribute(
      "href",
      "/recommendations",
    );
    expect(screen.queryByRole("link", { name: "Profile" })).not.toBeInTheDocument();
    unmount();
    tokenStore.clear();
  });
});
