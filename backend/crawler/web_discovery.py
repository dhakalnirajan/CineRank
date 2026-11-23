"""Polite, allow-listed web discovery for structured movie/TV metadata.

This is not a general-purpose unrestricted web scraper. It crawls only configured
seed hosts, follows robots.txt, bounds page/depth/body limits, and accepts a title
only when JSON-LD identifies a Movie/TVSeries/TVSeason/TVEpisode-like entity.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import logging
import socket
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, urlunparse
from urllib.robotparser import RobotFileParser

if __package__ in (None, ""):
    # Allow `python crawler/web_discovery.py` and running from inside crawler/.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ids import generate_title_id
from app.db.session import SessionLocal
from app.models.entities import CrawlFrontier, CrawledPage, Movie
from app.services.catalogue_service import make_sort_key, append_to_active_sort_index

logger = logging.getLogger("cinerank.web_crawler")

MOVIE_TYPES = {"movie", "tvmovie"}
TV_TYPES = {"tvseries", "tvseason", "tvminiseries", "creativeworkseries"}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _normalise_url(url: str) -> str | None:
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parsed.port
        netloc = host if port in (None, 80 if parsed.scheme == "http" else 443) else f"{host}:{port}"
        # Fragments and common tracking keys do not identify a distinct document.
        query_parts = []
        for pair in parsed.query.split("&") if parsed.query else []:
            key = pair.split("=", 1)[0].lower()
            if key.startswith("utm_") or key in {"fbclid", "gclid", "ref", "source"}:
                continue
            query_parts.append(pair)
        normalized = parsed._replace(scheme=parsed.scheme.lower(), netloc=netloc,
                                     fragment="", query="&".join(query_parts))
        result = urldefrag(urlunparse(normalized))[0]
        return result if len(result) <= 2048 else None
    except (TypeError, ValueError, UnicodeError):
        return None


def _public_host(host: str) -> bool:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except OSError:
        return False
    if not addresses:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def _same_allowed_domain(host: str, allowed: set[str]) -> bool:
    if host in allowed:
        return True
    return settings.CRAWLER_ALLOW_SUBDOMAINS and any(host.endswith("." + domain) for domain in allowed)


def _jsonld_objects(value):
    if isinstance(value, list):
        for item in value:
            yield from _jsonld_objects(item)
    elif isinstance(value, dict):
        if "@graph" in value:
            yield from _jsonld_objects(value["@graph"])
        else:
            yield value


class WebDiscoveryCrawler:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.1",
        })
        self.allowed_domains = {_host(url) for url in settings.crawler_seed_urls if _host(url)}
        self.allowed_domains.discard("")
        self.robots_cache: dict[str, tuple[float, RobotFileParser]] = {}
        self.last_request_by_host: dict[str, float] = {}
        self.host_delay_seconds: dict[str, float] = {}
        self.public_host_cache: dict[str, bool] = {}
        self.robots_sitemaps: dict[str, list[str]] = {}
        self.request_headers = {"Accept-Encoding": "gzip, deflate"}

    @property
    def enabled(self) -> bool:
        return bool(settings.WEB_CRAWLER_ENABLED and settings.crawler_seed_urls and self.allowed_domains)

    def _robots(self, base_url: str) -> RobotFileParser:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self.robots_cache.get(origin)
        now = time.monotonic()
        if cached and now - cached[0] < settings.CRAWLER_ROBOTS_TTL_SECONDS:
            return cached[1]
        parser = RobotFileParser()
        robots_url = origin + "/robots.txt"
        self._throttle(_host(base_url))
        try:
            response = self.session.get(
                robots_url,
                timeout=(settings.CRAWLER_CONNECT_TIMEOUT, settings.CRAWLER_READ_TIMEOUT),
                allow_redirects=False,
            )
            if response.status_code == 200:
                lines = response.text.splitlines()
                parser.parse(lines)
                self.robots_sitemaps[origin] = [
                    _normalise_url(line.split(":", 1)[1].strip())
                    for line in lines if line.casefold().startswith("sitemap:")
                    and _normalise_url(line.split(":", 1)[1].strip())
                ]
            elif response.status_code in (401, 403):
                parser.parse(["User-agent: *", "Disallow: /"])
                self.robots_sitemaps[origin] = []
            else:
                # A missing robots file is equivalent to no explicit disallow rule.
                parser.parse(["User-agent: *", "Allow: /"])
                self.robots_sitemaps[origin] = []
        except requests.RequestException:
            # Fail closed: a temporary robots retrieval failure means defer this host.
            parser.parse(["User-agent: *", "Disallow: /"])
            self.robots_sitemaps[origin] = []
        declared_delay = parser.crawl_delay(settings.CRAWLER_USER_AGENT) or parser.crawl_delay("*") or 0
        configured_delay = max(float(settings.CRAWLER_MIN_HOST_DELAY_SECONDS),
                               float(settings.CRAWLER_DEFAULT_DELAY_SECONDS),
                               1.0 / max(0.1, settings.CRAWLER_REQUESTS_PER_SECOND))
        self.host_delay_seconds[_host(base_url)] = max(configured_delay, float(declared_delay))
        self.robots_cache[origin] = (now, parser)
        return parser

    def _allowed(self, url: str) -> bool:
        normal = _normalise_url(url)
        if not normal:
            return False
        parsed = urlparse(normal)
        host = (parsed.hostname or "").lower()
        if not _same_allowed_domain(host, self.allowed_domains):
            return False
        if host not in self.public_host_cache:
            self.public_host_cache[host] = _public_host(host)
        if not self.public_host_cache[host]:
            logger.warning("Blocked non-public or unresolvable crawler host: %s", host)
            return False
        return self._robots(normal).can_fetch(settings.CRAWLER_USER_AGENT, normal)

    def _throttle(self, host: str) -> None:
        interval = max(
            settings.CRAWLER_MIN_HOST_DELAY_SECONDS,
            settings.CRAWLER_DEFAULT_DELAY_SECONDS,
            1.0 / max(0.1, settings.CRAWLER_REQUESTS_PER_SECOND),
            self.host_delay_seconds.get(host, 0.0),
        )
        previous = self.last_request_by_host.get(host, 0.0)
        delay = interval - (time.monotonic() - previous)
        if delay > 0:
            time.sleep(delay)
        self.last_request_by_host[host] = time.monotonic()

    def _fetch(self, url: str, previous: CrawledPage | None = None) -> tuple[requests.Response | None, str | None]:
        current = url
        redirects = 0
        attempts = 0
        while redirects <= settings.CRAWLER_MAX_REDIRECTS:
            if not self._allowed(current):
                return None, "blocked_by_domain_or_robots"
            host = _host(current)
            headers = dict(self.request_headers)
            if previous and previous.etag:
                headers["If-None-Match"] = previous.etag
            if previous and previous.last_modified:
                headers["If-Modified-Since"] = previous.last_modified
            while attempts < max(1, settings.CRAWLER_MAX_RETRIES):
                self._throttle(host)
                try:
                    response = self.session.get(
                        current, headers=headers,
                        timeout=(settings.CRAWLER_CONNECT_TIMEOUT, settings.CRAWLER_READ_TIMEOUT),
                        allow_redirects=False, stream=True,
                    )
                except requests.RequestException as exc:
                    attempts += 1
                    if attempts >= max(1, settings.CRAWLER_MAX_RETRIES):
                        return None, str(exc)[:1000]
                    time.sleep(min(30.0, 2.0 ** (attempts - 1)))
                    continue
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    response.close()
                    if not location:
                        return None, "redirect_without_location"
                    current = urljoin(current, location)
                    redirects += 1
                    attempts = 0
                    break
                if response.status_code in (429, 500, 502, 503, 504):
                    retry_after = response.headers.get("Retry-After", "")
                    response.close()
                    attempts += 1
                    if attempts >= max(1, settings.CRAWLER_MAX_RETRIES):
                        return None, f"http_{response.status_code}"
                    try:
                        delay = max(1.0, min(60.0, float(retry_after)))
                    except ValueError:
                        delay = min(30.0, 2.0 ** (attempts - 1))
                    time.sleep(delay)
                    continue
                if response.status_code == 304:
                    response.close()
                    return response, None
                if response.status_code != 200:
                    status_code = response.status_code
                    response.close()
                    return None, f"http_{status_code}"
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type and "xml" not in content_type:
                    response.close()
                    return None, "unsupported_content_type"
                content_length = response.headers.get("Content-Length")
                try:
                    if content_length and int(content_length) > settings.CRAWLER_MAX_BODY_BYTES:
                        response.close()
                        return None, "response_too_large"
                except ValueError:
                    response.close()
                    return None, "invalid_content_length"
                chunks = []
                size = 0
                try:
                    for chunk in response.iter_content(64 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > settings.CRAWLER_MAX_BODY_BYTES:
                            response.close()
                            return None, "response_too_large"
                        chunks.append(chunk)
                    response._content = b"".join(chunks)
                    response._content_consumed = True
                except requests.RequestException as exc:
                    response.close()
                    attempts += 1
                    if attempts >= max(1, settings.CRAWLER_MAX_RETRIES):
                        return None, str(exc)[:1000]
                    time.sleep(min(30.0, 2.0 ** (attempts - 1)))
                    continue
                return response, None
            else:
                return None, "retry_limit_exceeded"
        return None, "redirect_limit_exceeded"

    @staticmethod
    def _date_year(value) -> int | None:
        if not value:
            return None
        if isinstance(value, list):
            value = value[0] if value else None
        text = str(value)
        try:
            return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None
        except (TypeError, ValueError):
            return None

    def _extract_entity(self, html: bytes, url: str) -> tuple[dict | None, list[str]]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        source_host = _host(url)
        for anchor in soup.find_all("a", href=True)[:settings.CRAWLER_MAX_LINKS_PER_PAGE]:
            candidate = _normalise_url(urljoin(url, anchor.get("href", "")))
            candidate_host = _host(candidate) if candidate else ""
            # Extraction returns same-site links even in isolated parser tests or
            # when no crawl policy is configured. The queue still applies the
            # configured allow-list, robots rules, and public-address checks.
            same_site = (candidate_host == source_host or
                         _same_allowed_domain(candidate_host, self.allowed_domains))
            if candidate and same_site:
                links.append(candidate)
        entities = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text()
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue
            entities.extend(_jsonld_objects(data))
        title_record = None
        for entity in entities:
            types = entity.get("@type", [])
            if isinstance(types, str):
                types = [types]
            types = {str(value).split("/")[-1].casefold() for value in types}
            if types & MOVIE_TYPES:
                media_type = "movie"
            elif types & TV_TYPES:
                media_type = "tv"
            else:
                continue
            title = entity.get("name")
            if not title or not str(title).strip():
                continue
            genre_value = entity.get("genre", [])
            if isinstance(genre_value, str):
                genre_value = [genre_value]
            genre_value = [str(value).strip() for value in genre_value if value]
            image = entity.get("image")
            if isinstance(image, dict):
                image = image.get("url")
            if isinstance(image, list):
                image = image[0] if image else None
            same_as = entity.get("sameAs")
            if isinstance(same_as, str):
                same_as = [same_as]
            same_as = same_as or []
            imdb_id = None
            for identity in same_as:
                text = str(identity)
                match = __import__("re").search(r"imdb\.com/title/(tt\d+)", text, __import__("re").I)
                if match:
                    imdb_id = match.group(1)
                    break
            directors = entity.get("director", [])
            actors = entity.get("actor", [])
            def names(value):
                if not isinstance(value, list):
                    value = [value] if value else []
                return [str(item.get("name") if isinstance(item, dict) else item) for item in value if item]
            title_record = {
                "media_type": media_type,
                "title": str(title).strip()[:512],
                "original_title": None,
                "year": self._date_year(entity.get("datePublished") or entity.get("dateCreated")),
                "overview": str(entity.get("description") or "")[:12000],
                "genres": "|".join(genre_value)[:1024],
                "poster_path": str(image)[:1024] if image else None,
                "backdrop_path": None,
                "popularity": 0.0,
                "vote_average": None,
                "vote_count": None,
                "runtime": None,
                "directors_json": json.dumps(names(directors), ensure_ascii=False),
                "cast_json": json.dumps(names(actors)[:20], ensure_ascii=False),
                "imdb_id": imdb_id,
                "source": "web_jsonld",
                "source_url": url,
                "source_domain": _host(url),
                "source_metadata_json": json.dumps({"schema_types": sorted(types), "same_as": same_as[:20]}, ensure_ascii=False),
            }
            break
        return title_record, list(dict.fromkeys(links))

    def _enqueue(self, db: Session, url: str, depth: int, priority: int = 100) -> None:
        if not self._allowed(url):
            return
        normal = _normalise_url(url)
        if not normal:
            return
        url_hash = hashlib.sha256(normal.encode("utf-8")).hexdigest()
        existing = db.query(CrawlFrontier).filter_by(url_hash=url_hash).first()
        now = datetime.now(timezone.utc)
        if existing:
            due_at = existing.next_crawl_at
            if due_at is not None and due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
            due = due_at is not None and due_at <= now
            if existing.state in {"done", "failed", "skipped"} and due:
                existing.state = "queued"
                existing.depth = min(existing.depth, depth)
                existing.priority = min(existing.priority, priority)
                existing.last_error = None
            return
        db.add(CrawlFrontier(url_hash=url_hash, url=normal, domain=_host(normal), depth=depth,
                             priority=priority, state="queued", next_crawl_at=None))
        try:
            db.flush()
        except Exception:
            db.rollback()

    def _parse_sitemap(self, content: bytes, source_url: str) -> list[str]:
        urls = []
        try:
            root = ET.fromstring(content)
            for child in root.iter():
                if child.tag.rsplit("}", 1)[-1] == "loc" and child.text:
                    url = _normalise_url(child.text.strip())
                    if url and _same_allowed_domain(_host(url), self.allowed_domains):
                        urls.append(url)
        except ET.ParseError:
            logger.warning("Invalid sitemap XML: %s", source_url)
        return urls

    def crawl(self, db: Session, max_pages: int | None = None) -> dict:
        if not self.enabled:
            return {"enabled": False, "pages_fetched": 0, "titles_inserted": 0, "titles_updated": 0}
        max_pages = max_pages or settings.CRAWLER_MAX_PAGES_PER_RUN
        for seed in settings.crawler_seed_urls:
            self._enqueue(db, seed, 0, priority=0)
            parsed = urlparse(seed)
            self._robots(seed)
            # Sitemap declarations are reused from the single robots.txt fetch.
            origin = f"{parsed.scheme}://{parsed.netloc}"
            for sitemap_url in self.robots_sitemaps.get(origin, []):
                if sitemap_url and _host(sitemap_url) in self.allowed_domains:
                    self._enqueue(db, sitemap_url, 0, priority=5)
        db.commit()

        # Recover interrupted fetches and schedule due revisits/retries.
        now_utc = datetime.now(timezone.utc)
        db.query(CrawlFrontier).filter(CrawlFrontier.state == "processing").update(
            {"state": "queued"}, synchronize_session=False
        )
        db.query(CrawlFrontier).filter(
            CrawlFrontier.state.in_(["done", "failed", "skipped"]),
            CrawlFrontier.next_crawl_at.is_not(None),
            CrawlFrontier.next_crawl_at <= now_utc,
        ).update({"state": "queued", "last_error": None}, synchronize_session=False)
        db.commit()
        stats = {"enabled": True, "pages_fetched": 0, "not_modified": 0,
                 "titles_inserted": 0, "titles_updated": 0, "links_discovered": 0,
                 "errors": 0, "robots_or_scope_skips": 0}
        for _ in range(max_pages):
            entry = db.query(CrawlFrontier).filter(
                CrawlFrontier.state == "queued"
            ).order_by(CrawlFrontier.priority.asc(), CrawlFrontier.discovered_at.asc()).first()
            if not entry:
                break
            url, depth = entry.url, int(entry.depth)
            entry.state = "processing"
            db.commit()
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            previous = db.query(CrawledPage).filter_by(url_hash=url_hash).first()
            response, error = self._fetch(url, previous)
            now = datetime.now(timezone.utc)
            if response is None:
                entry.state = "failed" if error != "blocked_by_domain_or_robots" else "skipped"
                entry.last_error = error
                retry_hours = settings.CRAWLER_RETRY_HOURS if entry.state == "failed" else settings.CRAWLER_REVISIT_HOURS
                entry.next_crawl_at = now + timedelta(hours=max(1, retry_hours))
                stats["errors" if entry.state == "failed" else "robots_or_scope_skips"] += 1
                page = previous or CrawledPage(url_hash=url_hash, url=url)
                page.last_error = error
                db.merge(page)
                db.commit()
                continue
            if response.status_code == 304:
                stats["not_modified"] += 1
                entry.state = "done"
                if previous:
                    previous.last_crawled_at = now
                    previous.last_error = None
                entry.next_crawl_at = now + timedelta(hours=max(1, settings.CRAWLER_REVISIT_HOURS))
                db.commit()
                continue
            content = response.content
            digest = hashlib.sha256(content).hexdigest()
            page = previous or CrawledPage(url_hash=url_hash, url=url)
            changed = page.content_sha256 != digest
            page.etag = response.headers.get("ETag")
            page.last_modified = response.headers.get("Last-Modified")
            page.status_code = response.status_code
            page.last_crawled_at = now
            page.last_changed_at = now if changed else page.last_changed_at
            page.content_sha256 = digest
            page.last_error = None
            db.merge(page)

            content_type = response.headers.get("Content-Type", "").lower()
            if "xml" in content_type or content.lstrip().startswith(b"<?xml"):
                entity, links = None, self._parse_sitemap(content, response.url or url)
            else:
                entity, links = self._extract_entity(content, response.url or url)
            if entity:
                existing = None
                if entity.get("imdb_id"):
                    existing = db.query(Movie).filter_by(imdb_id=entity["imdb_id"], media_type=entity["media_type"]).first()
                if existing is None:
                    source_hash = hashlib.sha256(entity["source_url"].encode("utf-8")).hexdigest()
                    existing = db.query(Movie).filter_by(source_url_hash=source_hash).first()
                if existing is None and entity.get("year"):
                    existing = db.query(Movie).filter(
                        Movie.media_type == entity["media_type"],
                        Movie.year == entity["year"],
                        Movie.title == entity["title"],
                    ).first()
                is_new = existing is None
                if existing is None:
                    existing = Movie(title_id=generate_title_id(), title=entity["title"],
                                      media_type=entity["media_type"], sort_key=make_sort_key(entity["title"]))
                    db.add(existing)
                for key, value in entity.items():
                    if key not in {"title_id", "sort_key"}:
                        setattr(existing, key, value)
                existing.source_url_hash = hashlib.sha256(entity["source_url"].encode("utf-8")).hexdigest()
                existing.title = entity["title"]
                existing.sort_key = make_sort_key(existing.title)
                db.flush()
                if is_new:
                    append_to_active_sort_index(db, existing.title_id)
                    stats["titles_inserted"] += 1
                else:
                    stats["titles_updated"] += 1
            if depth < settings.CRAWLER_MAX_DEPTH:
                for link in links:
                    self._enqueue(db, link, depth + 1, priority=50 + depth)
                    stats["links_discovered"] += 1
            entry.state = "done"
            entry.last_error = None
            entry.next_crawl_at = now + timedelta(hours=max(1, settings.CRAWLER_REVISIT_HOURS))
            stats["pages_fetched"] += 1
            db.commit()
        logger.info("Web discovery crawl stats: %s", stats)
        return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CineRank allow-listed web discovery crawler.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum pages to fetch (defaults to CRAWLER_MAX_PAGES_PER_RUN).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit only the crawl result as JSON.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db = SessionLocal()
    try:
        result = WebDiscoveryCrawler().crawl(db, max_pages=args.max_pages)
    finally:
        db.close()

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("CineRank web discovery finished:")
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
