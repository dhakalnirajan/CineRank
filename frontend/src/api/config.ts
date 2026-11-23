const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();

function defaultApiBase(): string {
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
  }
  return "http://localhost:8000/api/v1";
}

export const API_BASE_URL = (configuredBase || defaultApiBase()).replace(
  /\/+$/,
  "",
);

export const REQUEST_TIMEOUT_MS = 20_000;
