import type { TokenResponse } from "../types/api";
import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "./config";
import { ApiError, toApiError } from "./errors";
import { tokenStore } from "./token";

let refreshInFlight: Promise<string | null> | null = null;

export function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = requestRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function requestRefresh(): Promise<string | null> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const startingRevision = tokenStore.revision();

  try {
    const sendRefresh = () => fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });

    let response = await sendRefresh();
    // Refresh cookies are shared across tabs. When two tabs rotate the same
    // token concurrently, the backend returns 401 + Retry-After to the loser.
    // Retry once after the winning response has had time to update the cookie.
    const retryAfter = response.status === 401
      ? Number(response.headers.get("Retry-After") ?? 0)
      : 0;
    if (retryAfter > 0 && retryAfter <= 2) {
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, Math.ceil(retryAfter * 1000));
      });
      response = await sendRefresh();
    }

    if (response.status === 401) {
      if (tokenStore.revision() === startingRevision) {
        tokenStore.clear();
      }
      return null;
    }

    if (!response.ok) {
      throw toApiError(response.status, null, response.headers.get("Retry-After"));
    }

    let payload: TokenResponse;
    try {
      payload = (await response.json()) as TokenResponse;
    } catch {
      throw toApiError(response.status, null);
    }

    if (!payload.access_token) {
      if (tokenStore.revision() === startingRevision) {
        tokenStore.clear();
      }
      return null;
    }

    if (tokenStore.revision() !== startingRevision) {
      return null;
    }

    tokenStore.set(payload.access_token);
    return payload.access_token;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (controller.signal.aborted) {
      if (timedOut) {
        throw new ApiError("That took too long. Check your connection and try again.", {
          kind: "timeout",
        });
      }
      throw new ApiError("That was cancelled. Please try again.", { kind: "aborted" });
    }
    throw new ApiError("Couldn't connect. Check your connection and try again.", {
      kind: "network",
    });
  } finally {
    window.clearTimeout(timer);
  }
}
