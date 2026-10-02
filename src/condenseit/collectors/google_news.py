"""Google News RSS search collector.

Fetches results from Google News's public RSS search endpoint, which supports
search operators such as ``site:``, ``when:``, ``intitle:``, and ``source:``.
No API key is needed.
"""

import logging
from datetime import UTC, datetime
from urllib.parse import quote_plus, urljoin, urlsplit

import feedparser
import httpx
import trafilatura
from googlenewsdecoder import gnewsdecoder

from condenseit.collectors.feed_dates import parse_feed_entry_date
from condenseit.collectors.health import collect_with_health
from condenseit.config import GoogleNewsSearchConfig
from condenseit.fetch_headers import digest_fetch_headers
from condenseit.store.database import ContentStore

logger = logging.getLogger(__name__)

_BASE_URL = "https://news.google.com/rss/search"
_MAX_ENTRIES = 8
_MAX_REDIRECTS = 6


def build_gnews_url(config: GoogleNewsSearchConfig) -> str:
    """Return the Google News RSS search URL for ``config``."""
    lang = config.language.lower()
    country = config.country.upper()
    return (
        f"{_BASE_URL}?q={quote_plus(config.query)}"
        f"&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"
    )


class GoogleNewsCollector:
    """Collect articles from Google News RSS search queries."""

    def __init__(self, sources: list[GoogleNewsSearchConfig]) -> None:
        self.sources = sources
        self._headers = digest_fetch_headers()
        self._client = httpx.Client(
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=True,
            headers=self._headers,
        )
        self._publisher_client = httpx.Client(
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=False,
        )

    def collect_all_with_health(
        self,
    ) -> tuple[list[dict[str, str]], list[tuple[str, str | None, int]]]:
        """Return ``(articles, [(rss_url, error_or_none, item_count), ...])``."""
        articles: list[dict[str, str]] = []
        health: list[tuple[str, str | None, int]] = []
        for cfg in self.sources:
            rss_url = build_gnews_url(cfg)
            items, entry = collect_with_health(
                rss_url,
                lambda cfg=cfg, rss_url=rss_url: self._collect_source(cfg, rss_url),
                log_label=f"Google News collect failed for query {cfg.query!r}",
            )
            articles.extend(items)
            health.append(entry)
        return articles, health

    def _collect_source(
        self,
        cfg: GoogleNewsSearchConfig,
        rss_url: str,
    ) -> list[dict[str, str]]:
        resp = self._client.get(rss_url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        items: list[dict[str, str]] = []

        for entry in feed.entries[:_MAX_ENTRIES]:
            link = entry.get("link", "")
            if not link:
                continue
            title = entry.get("title", "Untitled")
            entry_text = f"{title} {entry.get('summary', '')}".lower()
            if any(keyword.lower() in entry_text for keyword in cfg.hide_keywords):
                continue
            resolved = self._fetch_verified_article(link, cfg, entry)
            if resolved is None:
                continue
            publisher_url, content = resolved
            published = self._parse_published(entry)
            items.append(
                {
                    "url": publisher_url,
                    "title": title,
                    "content": content,
                    "source": cfg.publisher or urlsplit(publisher_url).hostname or "",
                    "category": cfg.category,
                    "content_hash": ContentStore.content_hash(content),
                    "published_at": published,
                    "collected_at": datetime.now(UTC).isoformat(),
                },
            )
        return items

    def _fetch_verified_article(
        self,
        url: str,
        cfg: GoogleNewsSearchConfig,
        entry: feedparser.FeedParserDict,
    ) -> tuple[str, str] | None:
        allowed = {domain.lower().lstrip(".") for domain in cfg.publisher_domains}
        if not allowed:
            return None

        try:
            decoded = gnewsdecoder(url, timeout=12)
        except Exception as exc:
            logger.debug("Google News URL decode failed for %s: %s", url, exc)
            return None
        current = decoded.get("decoded_url", "") if decoded.get("success") else ""
        if not current:
            return None
        publisher_client = getattr(self, "_publisher_client", self._client)

        for _ in range(_MAX_REDIRECTS + 1):
            parsed = urlsplit(current)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme != "https" or not host:
                return None
            is_publisher = any(
                host == domain or host.endswith(f".{domain}") for domain in allowed
            )
            if not is_publisher:
                return None

            try:
                response = publisher_client.get(current, follow_redirects=False)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.debug("Publisher fetch failed for %s: %s", current, exc)
                return None

            final_host = (
                (urlsplit(str(response.url)).hostname or "").lower().rstrip(".")
            )
            if not any(
                final_host == domain or final_host.endswith(f".{domain}")
                for domain in allowed
            ):
                return None
            content = trafilatura.extract(response.text, include_comments=False) or ""
            if not content.strip():
                summary = entry.get("summary", "")
                content = summary if isinstance(summary, str) else str(summary)
            if not content.strip():
                return None
            return str(response.url), content

        return None

    @staticmethod
    def _parse_published(entry: feedparser.FeedParserDict) -> str:
        return parse_feed_entry_date(entry)
