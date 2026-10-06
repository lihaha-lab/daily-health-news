import json
from datetime import UTC, date, datetime, timedelta

from condenseit.config import HealthReviewConfig, MatrixMediaConfig, SearchMatrixConfig
from condenseit.pipeline.health_review import (
    generated_claim_issues,
    matrix_queries,
    prior_digest_urls,
    review_health_candidates,
    select_recent_articles,
)


def _article(title: str, content: str, *, hours_ago: int = 2) -> dict[str, str]:
    return {
        "title": title,
        "content": content,
        "url": "https://news.example.cn/story",
        "published_at": (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
    }


def test_matrix_queries_are_bounded_and_use_verified_publisher_domains() -> None:
    cfg = SearchMatrixConfig(
        enabled=True,
        identities=["民警", "教师"],
        events=["心梗", "因公殉职"],
        event_clues=["突发疾病"],
        media=[
            MatrixMediaConfig(name="甲报", domains=["a.example.cn"]),
            MatrixMediaConfig(name="乙报", domains=["b.example.cn"]),
        ],
        max_queries_per_run=2,
    )

    searches = matrix_queries(cfg, on_date=date(2026, 10, 6))

    assert len(searches) == 2
    assert all("site:" in item.query and "when:3d" in item.query for item in searches)
    assert all(" OR " in item.query and "突发疾病" in item.query for item in searches)
    assert all(
        item.publisher_domains and item.publication_mode == "direct"
        for item in searches
    )
    assert {item.publisher_domains[0] for item in searches} == {
        "a.example.cn", "b.example.cn"
    }


def test_matrix_adds_broad_regional_cardio_searches_within_budget() -> None:
    cfg = SearchMatrixConfig(
        enabled=True,
        identities=["民警"],
        events=["心梗"],
        general_events=["心梗", "高血压"],
        media=[MatrixMediaConfig(name="地方报", domains=["local.example.cn"])],
        max_queries_per_run=2,
    )

    searches = matrix_queries(cfg, on_date=date(2026, 10, 6))

    assert len(searches) == 2
    assert "民警" in searches[0].query
    assert "民警" not in searches[1].query
    assert "高血压" in searches[1].query


def test_unconfirmed_cause_of_death_is_held_as_a_lead() -> None:
    articles = [
        _article("44岁辅警因公殉职", "当地公安部门发布讣告。"),
        _article("49岁民警心梗去世", "媒体称其因急性心肌梗死离世。"),
        _article("康桥运动健康季", "免费普拉提课程。"),
        _article("社区健身活动", "活动介绍顺带提到心脏健康。"),
        _article("普通长寿习惯", "文章谈到心脏健康与心血管风险。"),
        _article("年度心血管死亡率报告", "报告发布了心血管死亡率数据。"),
    ]

    ready, audit = review_health_candidates(
        articles,
        required_keywords=["心血管", "心梗", "心脏"],
        title_keywords=["高血压"],
        config=HealthReviewConfig(enabled=True),
    )

    assert [item["title"] for item in ready] == ["年度心血管死亡率报告"]
    assert [row["status"] for row in audit] == [
        "review", "review", "rejected", "rejected", "review", "ready"
    ]
    assert audit[0]["reason"] == "event_lead_without_confirmed_diagnosis"
    assert audit[1]["reason"] == "person_event_requires_source_and_cause_review"
    assert audit[4]["reason"] == "cardiovascular_terms_only_in_body"


def test_missing_date_does_not_auto_publish() -> None:
    article = _article("心血管疾病新报告", "报告内容")
    article["published_at"] = ""

    ready, audit = review_health_candidates(
        [article],
        required_keywords=["心血管"],
        title_keywords=[],
        config=HealthReviewConfig(enabled=True),
    )

    assert ready == []
    assert audit[0]["reason"] == "publication_date_unconfirmed"


def test_future_publication_date_is_held() -> None:
    article = _article("心血管健康报道", "相关内容")
    article["published_at"] = (
        datetime.now(UTC) + timedelta(hours=3)
    ).isoformat()

    ready, audit = review_health_candidates(
        [article],
        required_keywords=["心血管"],
        title_keywords=[],
        config=HealthReviewConfig(enabled=True),
    )

    assert ready == []
    assert audit[0]["reason"] == "publication_date_in_future"


def test_previous_day_article_is_not_repackaged_as_today() -> None:
    now = datetime(2026, 10, 6, 0, tzinfo=UTC)
    url = "https://news.example.cn/story"
    digests = [
        {
            "created_at": "2026-10-04T00:00:00+00:00",
            "stats_json": json.dumps({"digest_items": [{"url": url}]}),
        },
        {
            "created_at": "2026-10-04T00:00:00+00:00",
            "stats_json": json.dumps(
                {"dry_run": True, "digest_items": [{"url": "https://preview.cn"}]}
            ),
        },
    ]
    used = prior_digest_urls(digests, timezone="Asia/Shanghai", now=now)
    article = _article("心血管健康报道", "心血管健康内容")

    ready, audit = review_health_candidates(
        [article],
        required_keywords=["心血管"],
        title_keywords=[],
        config=HealthReviewConfig(enabled=True),
        previously_used_urls=used,
    )

    assert used == {url}
    assert ready == []
    assert audit[0]["reason"] == "used_in_previous_digest"


def test_recent_selection_expands_from_24_to_48_hours() -> None:
    now = datetime(2026, 10, 6, 0, tzinfo=UTC)
    articles = [
        {
            "url": f"https://example.cn/{hours}",
            "published_at": (now - timedelta(hours=hours)).isoformat(),
        }
        for hours in (3, 30, 40, 65)
    ]

    selected = select_recent_articles(
        articles,
        HealthReviewConfig(enabled=True, target_articles=3),
        max_articles=5,
        now=now,
    )

    assert [item["url"] for item in selected] == [
        "https://example.cn/3",
        "https://example.cn/30",
        "https://example.cn/40",
    ]


def test_generated_claim_audit_flags_invented_diagnosis_age_and_cause() -> None:
    article = _article("社区健康讲座", "文章讨论血压和血脂管理。")
    issues = generated_claim_issues(
        article,
        {
            "hook_title": "42岁男子心梗去世",
            "summary": "熬夜导致心梗。",
        },
    )

    assert "unsupported_claim:心梗" in issues
    assert "unsupported_claim:去世" in issues
    assert "unsupported_age:42岁" in issues
    assert "unsupported_causation" in issues


def test_contributor_short_text_and_alarmist_title_are_held() -> None:
    config = HealthReviewConfig(
        enabled=True,
        contributor_markers=["本文为澎湃号作者或机构"],
        caution_title_phrases=["当心"],
        minimum_source_text_chars=30,
    )
    articles = [
        _article("心梗住院治疗要带什么", "本文为澎湃号作者或机构在平台发布。"),
        _article("不注意这些事，当心心梗找上门", "文章正文详细讨论心梗。" * 4),
        _article("心梗预防新提醒", "很短"),
    ]

    ready, audit = review_health_candidates(
        articles,
        required_keywords=["心梗"],
        title_keywords=[],
        config=config,
    )

    assert ready == []
    assert [row["reason"] for row in audit] == [
        "contributor_content_requires_attribution_review",
        "sensational_headline_requires_review",
        "insufficient_original_article_text",
    ]
