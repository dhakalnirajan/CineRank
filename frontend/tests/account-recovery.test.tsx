import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { tokenStore } from "../src/api/token";
import ForgotPasswordPage from "../src/pages/ForgotPasswordPage";
import ResetPasswordPage from "../src/pages/ResetPasswordPage";
import VerifyEmailPage from "../src/pages/VerifyEmailPage";
import { jsonResponse, renderWithProviders, testUser } from "./test-utils";

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

describe("account recovery", () => {
  it("requests a reset link without confirming whether an account exists", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "reset_link_sent" }, 202));
    renderWithProviders(<ForgotPasswordPage />, { route: "/forgot-password" });

    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(
      await screen.findByText("If that email is on an account, a reset link is on its way."),
    ).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toContain("/auth/password/forgot");
    expect(init?.body).toBe(JSON.stringify({ email: "ada@example.com" }));
  });

  it("saves a new password from a valid reset link", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "password_reset" }));
    renderWithProviders(<ResetPasswordPage />, {
      route: "/reset-password?token=reset-token-value-that-is-long-enough",
    });

    await userEvent.type(screen.getByLabelText("New password"), "a-new-password-123");
    await userEvent.type(screen.getByLabelText("Confirm password"), "a-new-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));

    expect(await screen.findByText("Your password has been updated.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toContain("/auth/password/reset");
    expect(init?.body).toBe(
      JSON.stringify({
        token: "reset-token-value-that-is-long-enough",
        new_password: "a-new-password-123",
      }),
    );
  });

  it("explains when a reset link is missing", () => {
    renderWithProviders(<ResetPasswordPage />, { route: "/reset-password" });

    expect(screen.getByText("Link not valid")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("confirms an email from a valid link", async () => {
    fetchMock.mockResolvedValue(jsonResponse(testUser));
    renderWithProviders(<VerifyEmailPage />, {
      route: "/verify-email?token=verification-token-value-long-enough",
    });

    expect(await screen.findByText("Email confirmed")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toContain("/auth/email/verify");
    expect(init?.body).toBe(
      JSON.stringify({ token: "verification-token-value-long-enough" }),
    );
  });

  it("shows an error when a confirmation link cannot be used", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "This verification link is invalid or has expired" }, 400),
    );
    renderWithProviders(<VerifyEmailPage />, {
      route: "/verify-email?token=expired-token-value-long-enough",
    });

    const alert = await screen.findByRole("alert", {}, { timeout: 3000 });
    expect(alert).toHaveTextContent("This confirmation link is invalid or has expired.");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });
});
