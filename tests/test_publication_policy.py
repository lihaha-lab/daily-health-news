from condenseit.pipeline.orchestrator import _apply_publication_mode


def test_discovery_only_items_do_not_enter_digest() -> None:
    articles = [{"title": "Unverified public-figure report"}]

    assert _apply_publication_mode(articles, "discovery_only", "WeChat") == []


def test_direct_items_remain_eligible_for_digest() -> None:
    articles = [{"title": "Official health notice"}]

    assert _apply_publication_mode(articles, "direct", "Health agency") == articles
