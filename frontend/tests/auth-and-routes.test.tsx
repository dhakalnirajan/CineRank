import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { sessionHint, tokenStore } from "../src/api/token";
import { useAuth } from "../src/features/auth/AuthProvider";
import { ProtectedRoute } from "../src/features/auth/ProtectedRoute";
import LoginPage from "../src/pages/LoginPage";
import ProfilePage from "../src/pages/ProfilePage";
import RegisterPage from "../src/pages/RegisterPage";
import { jsonResponse, makeMovie, renderRoutes, renderWithProviders, testUser } from "./test-utils";

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

function SessionProbe() {
  const { status, user, signOut } = useAuth();
  return (
    <div>
      <span>{status}</span>
      <span>{user?.username ?? "no user"}</span>
      <button type="button" onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}

function protectedRoutes() {
  return (
    <Routes>
      <Route
        path="/watchlist"
        element={
          <ProtectedRoute>
            <div>Private watchlist</div>
          </ProtectedRoute>
        }
      />
      <Route path="/login" element={<div>Login screen</div>} />
    </Routes>
  );
}

describe("authentication and route protection", () => {
  it("redirects an anonymous visitor away from a protected route", async () => {
    renderRoutes(protectedRoutes(), ["/watchlist"]);

    expect(await screen.findByText("Login screen")).toBeInTheDocument();
    expect(screen.queryByText("Private watchlist")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows profile editing, activity and account security controls", async () => {
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
                title_id: "title_profile_history",
                serial_number: "000333",
                media_type: "movie",
                title: "Profile Film",
                genres: "Drama|Mystery",
                rating: 4.5,
                timestamp: "2026-01-02T00:00:00Z",
              },
            ],
          }),
        );
      }
      if (url.endsWith("/auth/sessions")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/watchlist")) {
        return Promise.resolve(
          jsonResponse([
            {
              created_at: "2026-01-02T00:00:00Z",
              title: makeMovie({ title_id: "title_profile_saved", title: "Saved Profile Film" }),
            },
          ]),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<ProfilePage />, { route: "/profile" });

    expect(await screen.findByRole("heading", { name: "ada" })).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Titles rated")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rating history/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /saved watchlist/i })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Sign out" })).toHaveLength(1);
    await userEvent.setup().click(screen.getByRole("button", { name: /edit profile/i }));
    expect(await screen.findByRole("heading", { name: "Make it yours" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("ada");
    expect(screen.getByLabelText("Email")).toHaveValue("ada@example.com");
  });

  it("loads the current account and clears the session on logout", async () => {
    tokenStore.set("valid-token");
    fetchMock.mockImplementation((input) => {
      if (String(input).endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderRoutes(<SessionProbe />);

    expect(await screen.findByText("ada")).toBeInTheDocument();
    expect(screen.getByText("authenticated")).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));

    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).endsWith("/auth/logout")),
    ).toBe(true);
    expect(tokenStore.get()).toBeNull();
    expect(screen.getByText("anonymous")).toBeInTheDocument();
  });

  it("clears expired authentication after a 401 response", async () => {
    tokenStore.set("expired-token");
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Invalid or expired access token" }, 401),
    );

    renderRoutes(<SessionProbe />);

    await waitFor(() => expect(tokenStore.get()).toBeNull());
    expect(await screen.findByText("anonymous")).toBeInTheDocument();
  });

  it("restores a session from the refresh cookie on load", async () => {
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        return Promise.resolve(
          jsonResponse({ access_token: "restored-token", token_type: "bearer", expires_in: 900 }),
        );
      }
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      return Promise.resolve(jsonResponse({}));
    });

    sessionHint.set();
    renderRoutes(<SessionProbe />);

    expect(await screen.findByText("ada")).toBeInTheDocument();
    expect(screen.getByText("authenticated")).toBeInTheDocument();
    const refreshCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).endsWith("/auth/refresh"),
    );
    expect(refreshCall?.[1]?.credentials).toBe("include");
  });

  it("shows a specific error when sign in is rejected", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Incorrect credentials" }, 401));
    renderWithProviders(<LoginPage />, { route: "/login" });

    await user.type(screen.getByLabelText("Username"), "ada");
    await user.type(screen.getByLabelText("Password"), "longpassword123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Incorrect username or password.")).toBeInTheDocument();
    expect(tokenStore.get()).toBeNull();
  });

  it("registers with JSON and signs in with the returned credentials", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/auth/register")) {
        return Promise.resolve(jsonResponse(testUser, 201));
      }
      if (url.endsWith("/auth/token")) {
        return Promise.resolve(
          jsonResponse({ access_token: "new-token", token_type: "bearer", expires_in: 3600 }),
        );
      }
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      return Promise.resolve(jsonResponse({}));
    });

    renderWithProviders(<RegisterPage />, { route: "/register" });

    await user.type(screen.getByLabelText("Username"), "ada");
    await user.type(screen.getByLabelText("Password"), "longpassword123");
    await user.type(screen.getByLabelText("Confirm password"), "longpassword123");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(tokenStore.get()).toBe("new-token"));
    const registerCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).endsWith("/auth/register"),
    );
    expect(JSON.parse(String(registerCall?.[1]?.body))).toEqual({
      username: "ada",
      password: "longpassword123",
    });
  });

  it("shows a clear duplicate account error", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Username or email is already registered" }, 409),
    );

    renderWithProviders(<RegisterPage />, { route: "/register" });

    await user.type(screen.getByLabelText("Username"), "ada");
    await user.type(screen.getByLabelText("Password"), "longpassword123");
    await user.type(screen.getByLabelText("Confirm password"), "longpassword123");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText("That name or email is already in use."),
    ).toBeInTheDocument();
  });
});
