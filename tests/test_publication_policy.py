from condenseit.pipeline.orchestrator import _apply_publication_mode, _apply_topic_gate


def test_discovery_only_items_do_not_enter_digest() -> None:
    articles = [{"title": "Unverified public-figure report"}]

    assert _apply_publication_mode(articles, "discovery_only", "WeChat") == []


def test_direct_items_remain_eligible_for_digest() -> None:
    articles = [{"title": "Official health notice"}]

    assert _apply_publication_mode(articles, "direct", "Health agency") == articles


def test_topic_gate_rejects_generic_wellness_and_generated_health_angle() -> None:
    articles = [
        {
            "title": "康桥运动健康季让健身服务触手可及",
            "content": "免费普拉提课程帮助学员放松身体、缓解负面情绪。",
            "category": "心脑血管健康与民生新闻",
            "summary": "提醒大家关注心脑血管健康。",
        },
        {"title": "高血压防治新指南", "content": "关注血压管理。"},
        {"title": "社区急救培训", "description": "演练心肺复苏和AED使用。"},
        {"title": "月饼怎么吃更健康", "content": "高血压人群也应注意饮食。"},
    ]

    accepted = _apply_topic_gate(
        articles,
        ["心脏", "心血管", "心肺复苏"],
        ["高血压"],
    )

    assert [item["title"] for item in accepted] == [
        "高血压防治新指南",
        "社区急救培训",
    ]


def test_topic_gate_is_optional_for_other_topic_packs() -> None:
    articles = [{"title": "体育新闻", "content": "比赛结果"}]

    assert _apply_topic_gate(articles, [], []) == articles
