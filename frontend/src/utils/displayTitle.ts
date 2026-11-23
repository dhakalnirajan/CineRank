interface DisplayTitleSource {
  title: string;
  display_title?: string | null;
}

const RELEASE_YEAR = /\s*\(\d{4}\)\s*$/;
const TRAILING_ARTICLE = /^(.+),\s*(The|A|An)$/i;

export function displayTitle(item: DisplayTitleSource): string {
  const source = (item.display_title?.trim() || item.title || "").trim();
  const withoutYear = source.replace(RELEASE_YEAR, "").trim();
  const match = withoutYear.match(TRAILING_ARTICLE);
  if (!match) {
    return withoutYear;
  }
  const [, body, article] = match;
  if (!body || !article) {
    return withoutYear;
  }
  return `${article.charAt(0).toUpperCase()}${article.slice(1).toLowerCase()} ${body.trim()}`;
}
