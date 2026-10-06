import json
from pathlib import Path

from click.testing import CliRunner

from condenseit.cli import cli
from condenseit.store.database import ContentStore


def test_migrate_applies_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    path = ContentStore.migrate(db_path=db_path)
    assert path == db_path
    assert db_path.is_file()
    store = ContentStore(db_path=db_path)
    assert "articles" in store.db.table_names()
    store.close()


def test_candidate_audit_is_independent_of_digest_history(tmp_path: Path) -> None:
    store = ContentStore(db_path=tmp_path / "test.db")
    audit_id = store.save_candidate_audit(
        {"counts": {"review": 1}, "items": [{"reason": "not_cardiovascular"}]}
    )

    row = store.latest_candidate_audit()

    assert row is not None and row["id"] == audit_id
    assert json.loads(row["audit_json"])["counts"]["review"] == 1
    assert store.latest_digest() is None
    store.close()


def test_migrate_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["migrate"])
    assert result.exit_code == 0, result.output
    assert "Migrations applied" in result.output
    assert (tmp_path / "condenseit.db").is_file()


def test_deduplicate_new_article(tmp_path: Path) -> None:
    store = ContentStore(db_path=tmp_path / "test.db")
    article = {
        "url": "https://example.com/a",
        "title": "Test",
        "content": "Hello world",
        "source": "Example",
        "category": "General",
        "content_hash": ContentStore.content_hash("Hello world"),
        "published_at": "2026-01-01T00:00:00+00:00",
        "collected_at": "2026-01-01T00:00:00+00:00",
    }
    fresh = store.deduplicate([article])
    assert len(fresh) == 1
    expected_hash = article["content_hash"]

    same_hash_again = {
        **article,
        "collected_at": "2026-06-01T12:00:00+00:00",
        "title": "Test renamed",
    }
    fresh_again = store.deduplicate([same_hash_again])
    assert len(fresh_again) == 0
    row = store.db["articles"].get(article["url"])
    # Keep the first-seen time so old feed items eventually leave the pool.
    assert row["collected_at"] == "2026-01-01T00:00:00+00:00"
    assert row["title"] == "Test renamed"
    assert row["content_hash"] == expected_hash


def test_articles_collected_since_supports_a_rolling_window(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    store = ContentStore(db_path=tmp_path / "rolling-window.db")
    now = datetime(2026, 9, 23, 12, tzinfo=UTC)
    rows = [
        {
            "url": f"https://example.com/{hours}",
            "title": f"Article {hours}",
            "content": "Health news",
            "source": "Example",
            "category": "Health",
            "content_hash": ContentStore.content_hash(str(hours)),
            "published_at": (now - timedelta(hours=hours)).isoformat(),
            "collected_at": (now - timedelta(hours=hours)).isoformat(),
        }
        for hours in (12, 48, 80)
    ]
    for row in rows:
        store.save_article(row)

    recent = store.articles_collected_since(now - timedelta(hours=72))

    assert {row["url"] for row in recent} == {
        "https://example.com/12",
        "https://example.com/48",
    }
    store.close()


def test_disabled_rss_domain_is_removed_from_cached_articles() -> None:
    from condenseit.pipeline.orchestrator import DigestPipeline

    class FakeSources:
        @staticmethod
        def list_all() -> list[dict[str, object]]:
            return [
                {
                    "type": "rss",
                    "url": "https://fda.gov/feed.xml",
                    "enabled": 0,
                },
                {
                    "type": "rss",
                    "url": "https://who.int/feed.xml",
                    "enabled": 1,
                },
            ]

        @staticmethod
        def google_news_for_config() -> list[object]:
            from condenseit.config import GoogleNewsSearchConfig

            return [
                GoogleNewsSearchConfig(
                    query="site:example.gov",
                    publisher="Official Health",
                    publisher_domains=["www.example.gov"],
                    publication_mode="direct",
                ),
            ]

    pipeline = object.__new__(DigestPipeline)
    pipeline.sources = FakeSources()
    articles = [
        {"url": "https://www.fda.gov/recall", "title": "FDA"},
        {"url": "https://www.who.int/news", "title": "WHO"},
        {
            "url": "https://news.example.gov/item",
            "source": "Official Health",
            "title": "Unapproved subdomain",
        },
        {
            "url": "https://www.example.gov/item",
            "source": "Official Health",
            "title": "Allowed publisher",
        },
    ]

    filtered = pipeline._filter_cached_articles_to_active_sources(articles)

    assert [article["title"] for article in filtered] == [
        "WHO",
        "Allowed publisher",
    ]


def test_cached_search_results_respect_current_source_rules() -> None:
    import json

    from condenseit.config import GoogleNewsSearchConfig
    from condenseit.pipeline.orchestrator import DigestPipeline

    class FakeSources:
        @staticmethod
        def list_all() -> list[dict[str, object]]:
            return [
                {
                    "type": "google_news",
                    "url": "https://news.google.com/rss/search?q=wechat",
                    "enabled": 1,
                    "extra_json": json.dumps(
                        {
                            "publisher_domains": ["mp.weixin.qq.com"],
                        }
                    ),
                },
                {
                    "type": "google_news",
                    "url": "https://news.google.com/rss/search?q=health",
                    "enabled": 1,
                    "extra_json": json.dumps({"publisher": "Health Agency"}),
                },
            ]

        @staticmethod
        def google_news_for_config() -> list[GoogleNewsSearchConfig]:
            return [
                GoogleNewsSearchConfig(
                    query="wechat",
                    category="WeChat leads",
                    publisher_domains=["mp.weixin.qq.com"],
                    publication_mode="discovery_only",
                ),
                GoogleNewsSearchConfig(
                    query="health",
                    category="Heart health",
                    publisher="Health Agency",
                    publisher_domains=["health.gov.cn"],
                    publication_mode="direct",
                    require_keywords=["心脏"],
                ),
            ]

    pipeline = object.__new__(DigestPipeline)
    pipeline.sources = FakeSources()
    articles = [
        {
            "url": "https://mp.weixin.qq.com/story",
            "source": "mp.weixin.qq.com",
            "category": "WeChat leads",
            "title": "心脏新闻",
        },
        {
            "url": "https://health.gov.cn/a",
            "source": "Health Agency",
            "category": "Heart health",
            "title": "Unrelated announcement",
        },
        {
            "url": "https://health.gov.cn/b",
            "source": "Health Agency",
            "category": "Heart health",
            "title": "心脏健康提醒",
        },
    ]

    assert [article["title"] for article in
            pipeline._filter_cached_articles_to_active_sources(articles)] == [
        "心脏健康提醒"
    ]
