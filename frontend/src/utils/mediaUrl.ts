import { API_BASE_URL } from "../api/config";

const API_ORIGIN = new URL(API_BASE_URL, typeof window === "undefined" ? "http://localhost" : window.location.origin).origin;

export function mediaUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  if (/^https:\/\//i.test(value) || value.startsWith("data:image/")) return value;
  if (value.startsWith("/")) return `${API_ORIGIN}${value}`;
  return value;
}
