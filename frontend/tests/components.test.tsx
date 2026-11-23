import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { HomeHero } from "../src/features/home/HomeHero";
import { SearchInput } from "../src/components/navigation/SearchInput";
import { RatingStars } from "../src/features/ratings/RatingStars";
import { PosterCard } from "../src/components/media/PosterCard";
import LoginPage from "../src/pages/LoginPage";
import { tokenStore } from "../src/api/token";
import { jsonResponse, renderWithProviders } from "./test-utils";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const punctuationTitles = [
  "'burbs, The (1989)",
  "(500) Days of Summer (2009)",
  "*batteries not included (1987)",
  "...And Justice for All (1979)",
  "10 (1979)",
  "10 Cloverfield Lane (2016)",
  "10 Things I Hate About You (1999)",
  "10,000 BC (2008)",
  "101 Dalmatians (1996)",
  "101 Dalmatians (One Hundred and One Dalmatians) (1961)",
] as const;

describe("PosterCard", () => {
  it("renders a deliberate fallback when artwork is missing", () => {
    renderWithProviders(
      <PosterCard
        item={{
          title_id: "title_test",
          serial_number: "000123",
          title: "Test Title",
          media_type: "movie",
          genres: "Drama|Comedy",
          year: 2024,
          poster_path: null,
        }}
      />,
    );

    expect(
      screen.getByRole("img", { name: "Artwork unavailable" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Test Title")).toHaveLength(2);
    expect(screen.getAllByText("Drama")).toHaveLength(2);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/movie/000123/");
    expect(screen.getByRole("link")).toHaveAttribute(
      "aria-label",
      "Test Title, 2024",
    );
    expect(screen.queryByText("000123")).not.toBeInTheDocument();
    expect(screen.getAllByText("2024")).toHaveLength(2);
  });

  it("uses the normalized display title without rewriting the provider title", () => {
    renderWithProviders(
      <PosterCard
        item={{
          title_id: "title_matrix",
          serial_number: "000456",
          title: "Matrix, The (1999)",
          display_title: "The Matrix",
          media_type: "movie",
          genres: "Action|Science Fiction",
          year: 1999,
          poster_path: null,
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "The Matrix" })).toBeInTheDocument();
    expect(screen.queryByText("Matrix, The (1999)")).not.toBeInTheDocument();
    expect(screen.getAllByText("Action").length).toBeGreaterThan(0);
  });

  it.each(punctuationTitles)(
    "keeps the exact title %s separate from the artwork fallback",
    (title) => {
      const { container } = renderWithProviders(
        <PosterCard
          item={{
            title_id: "title_test",
            serial_number: "000123",
            title,
            media_type: "movie",
            year: 2024,
            poster_path: null,
          }}
        />,
      );

      const expected = title
        .replace(/\s*\(\d{4}\)$/, "")
        .replace(/^(.+),\s*(The|A|An)$/i, (_match, body: string, article: string) => `${article} ${body}`);
      expect(screen.getByRole("heading", { name: expected }).textContent).toBe(
        expected,
      );
      expect(
        screen.getByRole("img", { name: "Artwork unavailable" }),
      ).toBeInTheDocument();
      expect(container.textContent).not.toContain("Artwork unavailable");
      expect(container.textContent).not.toContain("000123");
    },
  );
});

describe("RatingStars", () => {
  it("supports half-step selection and announces the value", () => {
    const onChange = vi.fn();
    renderWithProviders(<RatingStars value={3.5} onChange={onChange} />);

    const slider = screen.getByLabelText("Your rating from 0.5 to 5 stars");
    expect(slider).toHaveAttribute("aria-valuetext", "3.5 out of 5");

    fireEvent.change(slider, { target: { value: "4.5" } });
    expect(onChange).toHaveBeenCalledWith(4.5);
  });
});

describe("HomeHero", () => {
  it("renders a recommendation with a plain-language reason and no fake score", () => {
    const { container } = renderWithProviders(
      <HomeHero
        item={{
          title_id: "title_hero",
          serial_number: "000025",
          movielens_id: null,
          tmdb_id: null,
          imdb_id: null,
          media_type: "tv",
          title: "Cold Start Show",
          genres: "Drama|Mystery",
          year: 2025,
          overview: null,
          poster_path: null,
          backdrop_path: null,
          popularity: 0,
          vote_average: null,
          vote_count: null,
          runtime: null,
          directors_json: null,
          cast_json: null,
          is_adult: false,
          source: "movielens",
          score: 0.42,
          reason: "rank-fusion; sources=popular+content",
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Cold Start Show" })).toBeInTheDocument();
    expect(screen.getByText("2025")).toBeInTheDocument();
    expect(container.textContent).not.toContain("\u00B7");
    expect(screen.getByRole("link", { name: "Drama" })).toHaveAttribute(
      "href",
      "/explore?genre=Drama",
    );
    expect(screen.getByRole("link", { name: "Mystery" })).toHaveAttribute(
      "href",
      "/explore?genre=Mystery",
    );
    expect(screen.queryByText("000025")).not.toBeInTheDocument();
    expect(screen.getByText("Picked from popular titles and your taste.")).toBeInTheDocument();
    expect(screen.queryByText(/0.42/)).not.toBeInTheDocument();
  });
});

describe("LoginPage", () => {
  it("shows field errors before contacting the API", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, { route: "/login" });

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter your username.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits form-encoded credentials and stores the token", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/token")) {
        return Promise.resolve(
          jsonResponse({
            access_token: "token-123",
            token_type: "bearer",
            expires_in: 3600,
          }),
        );
      }
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(
          jsonResponse({
            id: 1,
            username: "ada",
            email: null,
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<LoginPage />, { route: "/login" });

    await user.type(screen.getByLabelText("Username"), "ada");
    await user.type(screen.getByLabelText("Password"), "longpassword123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(tokenStore.get()).toBe("token-123"));

    const loginCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).endsWith("/auth/token"),
    );
    expect(loginCall?.[1]?.body).toBe("username=ada&password=longpassword123");
  });
});

describe("SearchInput", () => {
  function Harness() {
    const [value, setValue] = useState("");
    return (
      <SearchInput
        value={value}
        onChange={setValue}
        onClear={() => setValue("")}
        onKeyDown={() => undefined}
        loading={false}
        hits={[]}
        moreAvailable={false}
        open={false}
        onClose={() => undefined}
      />
    );
  }

  it("types and clears with one clear control", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />, { route: "/" });

    const input = screen.getByLabelText("Search titles");
    await user.type(input, "Alien");
    expect(input).toHaveValue("Alien");
    const clearButton = screen.getByRole("button", { name: "Clear search" });
    expect(screen.getAllByRole("button", { name: "Clear search" })).toHaveLength(1);

    await user.click(clearButton);
    expect(input).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
  });
});
