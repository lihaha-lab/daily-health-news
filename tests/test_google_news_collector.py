from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from condenseit.collectors.google_news import GoogleNewsCollector
from condenseit.config import GoogleNewsSearchConfig


def _response(
    url: str, status: int, *, headers: dict[str, str] | None = None
) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(
        status,
        headers=headers,
        text="<html><body>source article body</body></html>",
        request=request,
    )


def test_google_news_item_uses_allowlisted_publisher_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = GoogleNewsCollector.__new__(GoogleNewsCollector)
    collector._client = SimpleNamespace(get=lambda url, **_kwargs: _response(url, 200))
    monkeypatch.setattr(
        "condenseit.collectors.google_news.gnewsdecoder",
        lambda *_args, **_kwargs: {
            "success": True,
            "decoded_url": "https://www.cdc.gov/healthy-living/story.html",
        },
    )
    monkeypatch.setattr(
        "condenseit.collectors.google_news.trafilatura.extract",
        lambda *_args, **_kwargs: "Publisher article text",
    )
    cfg = GoogleNewsSearchConfig(
        query="site:cdc.gov healthy living",
        publisher="CDC",
        publisher_domains=["cdc.gov"],
        publication_mode="direct",
    )
    entry = {"summary": "RSS summary", "published": datetime.now(UTC).isoformat()}

    result = collector._fetch_verified_article(
        "https://news.google.com/rss/articles/item",
        cfg,
        entry,
    )

    assert result == (
        "https://www.cdc.gov/healthy-living/story.html",
        "Publisher article text",
    )


def test_google_news_item_rejects_unapproved_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = GoogleNewsCollector.__new__(GoogleNewsCollector)
    calls: list[str] = []

    def get(url: str, **_kwargs: object) -> httpx.Response:
        calls.append(url)
        return _response(url, 302, headers={"location": "https://example.com/story"})

    collector._client = SimpleNamespace(get=get)
    monkeypatch.setattr(
        "condenseit.collectors.google_news.gnewsdecoder",
        lambda *_args, **_kwargs: {
            "success": True,
            "decoded_url": "https://example.com/story",
        },
    )
    cfg = GoogleNewsSearchConfig(
        query="health",
        publisher_domains=["cdc.gov"],
        publication_mode="direct",
    )

    result = collector._fetch_verified_article(
        "https://news.google.com/rss/articles/item",
        cfg,
        {"summary": "Unverified summary"},
    )

    assert result is None
    assert calls == []
