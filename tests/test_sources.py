import json
from pathlib import Path

from condenseit.collectors.google_news import build_gnews_url
from condenseit.config import AppConfig, FeedConfig, GoogleNewsSearchConfig
from condenseit.store.database import ContentStore
from condenseit.store.sources import SourceRegistry


def test_seed_google_news_source_from_topic_pack(tmp_path: Path) -> None:
    search = GoogleNewsSearchConfig(
        query="site:who.int/news when:7d",
        language="en",
        country="US",
        category="Public Health",
        priority=1,
        publisher="World Health Organization",
        publisher_domains=["who.int"],
        highlight_keywords=["guideline"],
    )
    store = ContentStore(tmp_path / "sources.db")
    try:
        registry = SourceRegistry(store)
        registry.seed_from_config(AppConfig(google_news=[search]))

        rows = registry.list_all()
        assert len(rows) == 1
        assert rows[0]["type"] == "google_news"
        assert rows[0]["name"] == search.query
        assert rows[0]["url"] == build_gnews_url(search)
        assert rows[0]["category"] == "Public Health"
        assert rows[0]["priority"] == 1
        assert '"highlight_keywords": ["guideline"]' in rows[0]["extra_json"]
        assert '"publisher_domains": ["who.int"]' in rows[0]["extra_json"]

        registry.seed_from_config(AppConfig(google_news=[search]))
        assert len(registry.list_all()) == 1
        loaded = registry.google_news_for_config()[0]
        assert loaded.publisher_domains == ["who.int"]
        assert loaded.publisher == "World Health Organization"
    finally:
        store.close()


def test_seed_rss_source_preserves_quality_metadata(tmp_path: Path) -> None:
    feed = FeedConfig(
        url="https://example.gov/news.xml",
        category="Policy",
        priority=1,
        publisher="Example Health Agency",
        region="global",
        trust_tier="primary",
        publication_mode="direct",
    )
    store = ContentStore(tmp_path / "sources.db")
    try:
        registry = SourceRegistry(store)
        registry.seed_from_config(AppConfig(feeds=[feed]))

        row = registry.list_all()[0]
        metadata = json.loads(row["extra_json"])
        assert row["name"] == "Example Health Agency"
        assert metadata["trust_tier"] == "primary"
        assert metadata["publication_mode"] == "direct"
        assert registry.feeds_for_config()[0].publisher == "Example Health Agency"
    finally:
        store.close()


def test_seed_enriches_legacy_source_without_overwriting_user_values(
    tmp_path: Path,
) -> None:
    store = ContentStore(tmp_path / "sources.db")
    try:
        registry = SourceRegistry(store)
        source_id = registry.add(
            "rss",
            "https://example.gov/news.xml",
            "Custom category",
            3,
            "https://example.gov/news.xml",
            extra={"region": "custom"},
        )
        feed = FeedConfig(
            url="https://example.gov/news.xml",
            publisher="Example Health Agency",
            region="global",
            trust_tier="primary",
            publication_mode="direct",
        )

        registry.seed_from_config(AppConfig(feeds=[feed]))

        row = registry.list_all()[0]
        metadata = json.loads(row["extra_json"])
        assert row["id"] == source_id
        assert row["name"] == "Example Health Agency"
        assert row["category"] == "Custom category"
        assert metadata["region"] == "custom"
        assert metadata["trust_tier"] == "primary"
    finally:
        store.close()


def test_disabled_source_type_does_not_fall_back_to_topic_pack(
    tmp_path: Path,
) -> None:
    store = ContentStore(tmp_path / "sources.db")
    try:
        registry = SourceRegistry(store)
        feed = FeedConfig(url="https://example.gov/news.xml")
        registry.seed_from_config(AppConfig(feeds=[feed]))
        source_id = registry.list_all()[0]["id"]

        registry.toggle(source_id, False)

        assert registry.has_type("rss") is True
        assert registry.feeds_for_config() == []
    finally:
        store.close()


def test_deleted_topic_pack_source_stays_deleted_until_readded(tmp_path: Path) -> None:
    feed = FeedConfig(url="https://example.gov/news.xml")
    store = ContentStore(tmp_path / "sources.db")
    try:
        registry = SourceRegistry(store)
        registry.seed_from_config(AppConfig(feeds=[feed]))
        source_id = registry.list_all()[0]["id"]

        registry.delete(source_id)
        registry.seed_from_config(AppConfig(feeds=[feed]))
        assert registry.list_all() == []

        registry.add("rss", "Restored", "General", 2, feed.url)
        registry.seed_from_config(AppConfig(feeds=[feed]))
        assert len(registry.list_all()) == 1
    finally:
        store.close()
