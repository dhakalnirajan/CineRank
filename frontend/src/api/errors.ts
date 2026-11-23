export type ApiErrorKind = "api" | "network" | "timeout" | "aborted";

export interface ApiErrorInit {
  status?: number;
  kind?: ApiErrorKind;
  fieldErrors?: Record<string, string>;
  detail?: string;
  retryAfterSeconds?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  readonly fieldErrors: Record<string, string>;
  readonly retryAfterSeconds: number | null;

  constructor(message: string, init: ApiErrorInit = {}) {
    super(message);
    this.name = "ApiError";
    this.status = init.status ?? 0;
    this.kind = init.kind ?? "api";
    this.fieldErrors = init.fieldErrors ?? {};
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }
}

interface ValidationDetail {
  loc?: unknown;
  msg?: unknown;
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isAbortError(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.kind === "aborted";
  }
  return error instanceof DOMException && error.name === "AbortError";
}

function readValidationErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) {
    return {};
  }
  const fields: Record<string, string> = {};
  for (const entry of detail) {
    const item = entry as ValidationDetail;
    if (typeof item.msg !== "string" || !Array.isArray(item.loc)) {
      continue;
    }
    const key = item.loc
      .filter((part): part is string | number => typeof part === "string" || typeof part === "number")
      .filter((part) => part !== "body" && part !== "query" && part !== "path")
      .join(".");
    if (key) {
      const field = key.split(".")[0] ?? "";
      const fieldMessages: Record<string, string> = {
        username: "Choose a valid username.",
        email: "Enter a valid email address.",
        password: "Choose a valid password.",
        confirmPassword: "Passwords do not match.",
      };
      fields[key] = fieldMessages[field] ?? "Check this field.";
    }
  }
  return fields;
}

export function readErrorMessage(detail: unknown, status: number, retryAfterSeconds?: number): string {
  const detailText = typeof detail === "string" ? detail.toLowerCase() : "";
  if (status === 400 || status === 422) {
    return "Please check your details and try again.";
  }
  if (status === 401) {
    return "Your session ended. Sign in again.";
  }
  if (status === 403) {
    return "You don't have access to this page.";
  }
  if (status === 404) {
    return "We couldn't find that title.";
  }
  if (status === 409) {
    return detailText.includes("catalogue") || detailText.includes("pagination")
      ? "This list changed. Refresh to see the latest titles."
      : "That name or email is already in use.";
  }
  if (status === 429) {
    return retryAfterSeconds && retryAfterSeconds > 0
      ? `Too many attempts. Try again in ${retryAfterSeconds} seconds.`
      : "Too many attempts. Please wait a moment.";
  }
  if (status === 503) {
    return "This isn't available right now. Please try again soon.";
  }
  return "Something went wrong. Please try again.";
}

export function toApiError(status: number, detail: unknown, retryAfterHeader?: string | null): ApiError {
  let retryAfterSeconds: number | undefined;
  if (retryAfterHeader) {
    const numeric = Number(retryAfterHeader);
    if (Number.isFinite(numeric)) {
      retryAfterSeconds = Math.max(0, Math.ceil(numeric));
    } else {
      const timestamp = Date.parse(retryAfterHeader);
      if (Number.isFinite(timestamp)) retryAfterSeconds = Math.max(0, Math.ceil((timestamp - Date.now()) / 1000));
    }
  }
  return new ApiError(readErrorMessage(detail, status, retryAfterSeconds), {
    status,
    kind: "api",
    fieldErrors: readValidationErrors(detail),
    retryAfterSeconds,
  });
}
