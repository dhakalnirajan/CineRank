import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL, apiRequest } from "../src/api/client";
import { api } from "../src/api/endpoints";
import { ApiError } from "../src/api/errors";
import { tokenStore } from "../src/api/token";
import { refreshAccessToken } from "../src/api/session";
import { jsonResponse } from "./test-utils";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  tokenStore.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  tokenStore.clear();
});

describe("api client", () => {
  it("builds requests from the configured base URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await apiRequest("/movies");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`${API_BASE_URL}/movies`);
    expect(API_BASE_URL.endsWith("/api/v1")).toBe(true);
  });

  it("attaches the bearer token to authenticated requests", async () => {
    tokenStore.set("signed-token");
    fetchMock.mockResolvedValue(jsonResponse({ id: 1 }));

    await apiRequest("/auth/me");

    const init = fetchMock.mock.calls[0]?.[1];
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer signed-token",
    );
  });

  it("sends login credentials as form data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ access_token: "token", token_type: "bearer", expires_in: 3600 }),
    );

    await api.login("ada", "longpassword123");

    const init = fetchMock.mock.calls[0]?.[1];
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/auth/token");
    expect(init?.body).toBe("username=ada&password=longpassword123");
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/x-www-form-urlencoded",
    );
  });

  it("normalizes validation errors and field messages", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: [
            {
              loc: ["body", "username"],
              msg: "String should match pattern",
              type: "string_pattern_mismatch",
            },
          ],
        },
        422,
      ),
    );

    let caught: unknown;
    try {
      await api.register({ username: "x", password: "longpassword123" });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(ApiError);
    const apiError = caught as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.fieldErrors.username).toBe("Choose a valid username.");
  });

  it("surfaces Retry-After guidance for rate-limited requests", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Too many requests" }), {
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "17" },
    }));

    await expect(apiRequest("/search?q=film", { auth: false })).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: 17,
      message: "Too many attempts. Try again in 17 seconds.",
    });
  });

  it("clears authentication state when an authenticated request returns 401", async () => {
    tokenStore.set("expired-token");
    const listener = vi.fn();
    window.addEventListener("cinerank:unauthorized", listener);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Invalid or expired access token" }, 401));

    await expect(api.me()).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(tokenStore.get()).toBeNull();

    window.removeEventListener("cinerank:unauthorized", listener);
  });

  it("refreshes once and retries an authenticated request after a 401", async () => {
    tokenStore.set("expired-token");
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "Invalid or expired access token" }, 401))
      .mockResolvedValueOnce(
        jsonResponse({ access_token: "fresh-token", token_type: "bearer", expires_in: 900 }),
      )
      .mockResolvedValueOnce(jsonResponse({ id: 1 }));

    await expect(api.me()).resolves.toMatchObject({ id: 1 });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/auth/refresh");
    expect(fetchMock.mock.calls[1]?.[1]?.credentials).toBe("include");
    expect((fetchMock.mock.calls[2]?.[1]?.headers as Record<string, string>).Authorization).toBe(
      "Bearer fresh-token",
    );
    expect(tokenStore.get()).toBe("fresh-token");
  });

  it("retries a cross-tab refresh conflict before clearing the session", async () => {
    vi.useFakeTimers();
    tokenStore.set("expired-token");
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Refresh already completed" }), {
        status: 401,
        headers: { "Content-Type": "application/json", "Retry-After": "1" },
      }))
      .mockResolvedValueOnce(jsonResponse({
        access_token: "rotated-token",
        token_type: "bearer",
        expires_in: 900,
      }));

    const refreshPromise = refreshAccessToken();
    await vi.advanceTimersByTimeAsync(1000);
    await expect(refreshPromise).resolves.toBe("rotated-token");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(tokenStore.get()).toBe("rotated-token");
    vi.useRealTimers();
  });

  it("logs out with the refresh cookie", async () => {
    tokenStore.set("signed-token");
    fetchMock.mockResolvedValue(jsonResponse({ status: "logged out" }));

    await api.logout();

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/auth/logout");
    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("include");
  });

  it("surfaces catalogue version conflicts", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Catalogue order changed; restart pagination" }, 409),
    );

    await expect(api.listMovies({ cursor: "opaque" })).rejects.toMatchObject({
      status: 409,
      message: "This list changed. Refresh to see the latest titles.",
    });
  });

  it("passes catalogue cursors through unchanged", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [], next_cursor: null, catalogue_version: 3 }),
    );

    await api.listMovies({ cursor: "abc.def", genre: "Drama", mediaType: "movie" });

    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("cursor=abc.def");
    expect(url).toContain("genre=Drama");
    expect(url).toContain("media_type=movie");
  });

  it("reports cancellation as an aborted request", async () => {
    const controller = new AbortController();
    controller.abort();
    fetchMock.mockRejectedValue(new DOMException("Aborted", "AbortError"));

    let caught: unknown;
    try {
      await apiRequest("/movies", { signal: controller.signal });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).kind).toBe("aborted");
  });

  it("stores access tokens in memory only", () => {
    tokenStore.set("memory-token");
    expect(tokenStore.get()).toBe("memory-token");
    expect(window.localStorage.getItem("cinerank.access_token")).toBeNull();
    tokenStore.clear();
  });

  it("reports a timeout when the request exceeds the limit", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );

    const expectation = expect(apiRequest("/slow")).rejects.toMatchObject({
      kind: "timeout",
    });
    await vi.advanceTimersByTimeAsync(20_001);
    await expectation;
    vi.useRealTimers();
  });
});
