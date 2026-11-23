"""Display-only title normalisation. Stored provider titles are never rewritten."""
from __future__ import annotations

import re

_ARTICLES = {"the", "a", "an"}
_TRAILING_ARTICLE = re.compile(r"^(?P<body>.+),\s*(?P<article>The|A|An)$", re.IGNORECASE)
_RELEASE_YEAR = re.compile(r"\s*\(\d{4}\)\s*$")


def normalize_display_title(title: str) -> str:
    """Return a clean title without a duplicate year suffix.

    The release year is a separate API field and should be rendered in metadata,
    not repeated inside the title label. Library-style trailing articles are moved
    to the front after removing the provider's optional ``(YYYY)`` suffix.
    """
    value = _RELEASE_YEAR.sub("", (title or "").strip()).strip()
    match = _TRAILING_ARTICLE.match(value)
    if not match:
        return value
    article = match.group("article")
    if article.casefold() not in _ARTICLES:
        return value
    return f"{article.title()} {match.group('body').strip()}"
