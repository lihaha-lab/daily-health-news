from condenseit.digest.format import build_digest_markdown


def test_digest_is_compact_and_keeps_links_out() -> None:
    md = build_digest_markdown(
        {
            "心脑血管健康": [
                {
                    "title": "心脏健康新闻",
                    "url": "https://example.com/article",
                    "published_at": "2026-09-24T01:00:00Z",
                    "summary": "面向普通读者的简短摘要。",
                    "source": "地方媒体",
                    "tldr": "不应出现在简报中",
                    "relevance_to_you": "也不应出现",
                },
            ],
        },
        title="每日大众健康简报",
    )

    assert md.startswith("# 每日大众健康简报\n\n")
    assert "### 2026-09-24｜心脏健康新闻" in md
    assert "**来源：** 地方媒体" in md
    assert "**摘要：** 面向普通读者的简短摘要。" in md
    assert "https://example.com/article" not in md
    assert "不应出现在简报中" not in md
    assert "也不应出现" not in md


def test_digest_shows_empty_state() -> None:
    md = build_digest_markdown({}, title="每日简报")

    assert "今日暂无符合主题的新闻。" in md
