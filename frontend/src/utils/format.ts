export function formatYear(year: number | null | undefined): string | null {
  return typeof year === "number" && Number.isFinite(year) ? String(year) : null;
}

export function formatRuntime(minutes: number | null | undefined): string | null {
  if (typeof minutes !== "number" || !Number.isFinite(minutes) || minutes <= 0) {
    return null;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) {
    return `${rest} min`;
  }
  return rest === 0 ? `${hours} hr` : `${hours} hr ${rest} min`;
}

export function formatRating(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value.toFixed(1);
}

export function formatDate(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

export function mediaLabel(mediaType: string | null | undefined): string {
  if (!mediaType) {
    return "Title";
  }
  return mediaType === "tv" ? "Series" : "Film";
}

export function parseGenres(genres: string | null | undefined): string[] {
  if (!genres) {
    return [];
  }
  const seen = new Set<string>();
  return genres
    .split(/[|,]/)
    .map((genre) => genre.trim())
    .filter((genre) => {
      if (!genre || seen.has(genre.toLowerCase())) {
        return false;
      }
      seen.add(genre.toLowerCase());
      return true;
    });
}

export interface Person {
  name: string;
  role: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parsePeople(raw: string | null | undefined): Person[] {
  if (!raw) {
    return [];
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) {
    return [];
  }
  const people: Person[] = [];
  for (const entry of parsed) {
    if (typeof entry === "string") {
      const name = entry.trim();
      if (name) {
        people.push({ name, role: null });
      }
      continue;
    }
    if (!isRecord(entry)) {
      continue;
    }
    const name = typeof entry.name === "string" ? entry.name.trim() : "";
    if (!name) {
      continue;
    }
    const roleSource = entry.character ?? entry.role ?? entry.job;
    people.push({ name, role: typeof roleSource === "string" ? roleSource : null });
  }
  return people;
}

export function isRenderableImageUrl(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function ratingLabel(rating: number): string {
  return `${rating.toFixed(1)} out of 5`;
}

const FRIENDLY_REASON_SOURCES: Record<string, string> = {
  popular: "popular titles",
  content: "your taste",
  itemknn: "similar viewers",
  als: "viewers like you",
  bpr: "viewers like you",
  attn: "your recent ratings",
  hybrid: "your taste",
};

export function recommendationReason(reason: string | null | undefined): string | null {
  if (!reason) {
    return null;
  }
  const sources = reason
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("sources="));
  if (!sources) {
    return "Picked for you.";
  }
  const labels = [
    ...new Set(
      sources
        .replace("sources=", "")
        .split("+")
        .map((value) => value.trim().toLowerCase())
        .map((value) => FRIENDLY_REASON_SOURCES[value])
        .filter((value): value is string => Boolean(value)),
    ),
  ];
  return labels.length > 0 ? `Picked from ${labels.join(" and ")}.` : "Picked for you.";
}
