import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "./config";
import { ApiError, toApiError } from "./errors";
import { refreshAccessToken } from "./session";
import { tokenStore } from "./token";

export { API_BASE_URL, REQUEST_TIMEOUT_MS } from "./config";

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  form?: URLSearchParams;
  formData?: FormData;
  auth?: boolean;
  signal?: AbortSignal;
}

async function readDetail(response: Response): Promise<unknown> {
  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object" && "detail" in payload) {
      return (payload as { detail: unknown }).detail;
    }
    return payload;
  } catch {
    return null;
  }
}

async function sendRequest(
  path: string,
  options: RequestOptions,
  token: string | null,
): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  const externalSignal = options.signal;
  const forwardAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener("abort", forwardAbort);
    }
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.auth !== false && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (options.form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = options.form.toString();
  } else if (options.formData !== undefined) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body,
      credentials: "include",
      signal: controller.signal,
    });
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
    externalSignal?.removeEventListener("abort", forwardAbort);
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let token = tokenStore.get();
  let response = await sendRequest(path, options, token);

  if (
    response.status === 401 &&
    options.auth !== false &&
    token &&
    path !== "/auth/refresh"
  ) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      token = refreshedToken;
      response = await sendRequest(path, options, token);
    } else if (!tokenStore.get()) {
      window.dispatchEvent(new Event("cinerank:unauthorized"));
    }
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    if (response.status === 401 && options.auth !== false && tokenStore.get()) {
      window.dispatchEvent(new Event("cinerank:unauthorized"));
    }
    throw toApiError(response.status, detail, response.headers.get("Retry-After"));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  return (text ? (JSON.parse(text) as T) : (undefined as T));
}
