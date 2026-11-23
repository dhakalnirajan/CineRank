export function genreRowLabel(key: string): string {
  const raw = key.replace(/^genre_/, "").replace(/_/g, " ").trim();
  if (!raw) {
    return "More recommendations";
  }
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}
