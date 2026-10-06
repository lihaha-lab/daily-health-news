"""Conservative, inspectable gates for the mainland health edition.

These checks identify evidence gaps; they do not certify medical facts. A
person's reported death or collapse remains a review lead, not publishable
evidence, until a human checks the original source and diagnosis.
"""

import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from condenseit.config import (
    GoogleNewsSearchConfig,
    HealthReviewConfig,
    SearchMatrixConfig,
)

_EVENT_CLUES = (
    "突发疾病", "突然倒地", "突然晕倒", "抢救无效", "因病去世",
    "突然离世", "因公殉职", "不幸去世", "英年早逝",
)
_PERSON_EVENT_WORDS = (
    *_EVENT_CLUES, "猝死", "去世", "死亡", "殉职", "倒地", "抢救",
)
_PERSON_WORDS = (
    "岁", "男子", "女子", "居民", "民警", "辅警", "干部", "教师", "医生",
    "消防员", "公务员", "交警", "护士", "教授", "演员", "歌手", "企业家",
    "企业负责人", "工作人员",
)
_SENSITIVE_CLAIMS = (
    "心梗", "心肌梗死", "心脏骤停", "心源性猝死", "脑梗", "脑出血",
    "脑卒中", "卒中", "猝死", "死亡", "去世",
)


def matrix_queries(
    config: SearchMatrixConfig,
    *,
    on_date: date | None = None,
) -> list[GoogleNewsSearchConfig]:
    """Rotate bounded three-dimensional searches across configured media."""
    if not (
        config.enabled and config.identities and config.events and config.media
    ):
        return []
    day = (on_date or datetime.now(UTC).date()).toordinal()
    searches: list[GoogleNewsSearchConfig] = []
    for offset in range(min(config.max_queries_per_run, len(config.media))):
        medium = config.media[(day + offset) % len(config.media)]
        identity_start = (day * 3 + offset * 3) % len(config.identities)
        event_start = (day * 2 + offset * 2) % len(config.events)
        identities = [
            config.identities[(identity_start + index) % len(config.identities)]
            for index in range(min(3, len(config.identities)))
        ]
        events = [
            config.events[(event_start + index) % len(config.events)]
            for index in range(min(2, len(config.events)))
        ]
        if config.event_clues:
            events.append(config.event_clues[(day + offset) % len(config.event_clues)])
        identity_group = " OR ".join(f'"{word}"' for word in identities)
        event_group = " OR ".join(f'"{word}"' for word in events)
        # The publisher's allowlisted site is the third search dimension.
        domain = medium.domains[0].lower().lstrip(".")
        searches.append(
            GoogleNewsSearchConfig(
                query=(
                    f"site:{domain} ({identity_group}) ({event_group}) "
                    f"when:{config.lookback_days}d"
                ),
                language="zh",
                country="CN",
                category="地方人物健康事件",
                publisher=medium.name,
                publisher_domains=medium.domains,
                region=medium.region,
                trust_tier="reputable",
                publication_mode="direct",
            )
        )
    remaining = min(len(config.media), config.max_queries_per_run - len(searches))
    for offset in range(remaining):
        if not config.general_events:
            break
        medium = config.media[(day + offset) % len(config.media)]
        domain = medium.domains[0].lower().lstrip(".")
        general_group = " OR ".join(config.general_events)
        searches.append(
            GoogleNewsSearchConfig(
                query=(
                    f"site:{domain} ({general_group}) "
                    f"when:{config.lookback_days}d"
                ),
                language="zh",
                country="CN",
                category="地方心脑血管新闻",
                publisher=medium.name,
                publisher_domains=medium.domains,
                region=medium.region,
                trust_tier="reputable",
                publication_mode="direct",
            )
        )
    return searches


def _published_at(article: dict[str, Any]) -> datetime | None:
    raw = str(article.get("published_at") or "").strip()
    try:
        published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return published.replace(tzinfo=published.tzinfo or UTC).astimezone(UTC)


def prior_digest_urls(
    digests: list[dict[str, Any]],
    *,
    timezone: str,
    now: datetime | None = None,
) -> set[str]:
    """Find URLs used on earlier local days, ignoring preview-only runs."""
    today = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()
    used: set[str] = set()
    for digest in digests:
        try:
            created = datetime.fromisoformat(
                str(digest.get("created_at") or "").replace("Z", "+00:00")
            )
            if created.replace(tzinfo=created.tzinfo or UTC).astimezone(
                ZoneInfo(timezone)
            ).date() >= today:
                continue
            stats = json.loads(str(digest.get("stats_json") or "{}"))
        except (ValueError, TypeError):
            continue
        if not isinstance(stats, dict) or stats.get("dry_run"):
            continue
        items = stats.get("digest_items")
        if isinstance(items, list):
            used.update(
                str(item.get("url") or "")
                for item in items
                if isinstance(item, dict) and item.get("url")
            )
    return used


def review_health_candidates(
    articles: list[dict[str, Any]],
    *,
    required_keywords: list[str],
    title_keywords: list[str],
    config: HealthReviewConfig,
    previously_used_urls: set[str] | None = None,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Return publishable candidates and an audit row for every input item."""
    now = now or datetime.now(UTC)
    ready: list[dict[str, Any]] = []
    audit: list[dict[str, str]] = []
    for article in articles:
        title = str(article.get("title") or "")
        content = str(article.get("content") or article.get("description") or "")
        original = (title + " " + content[:500]).casefold()
        title_lower = title.casefold()
        host = urlsplit(str(article.get("url") or "")).hostname
        published = _published_at(article)
        body_lower = content[:500].casefold()
        title_signals = {
            word for word in required_keywords if word.casefold() in title_lower
        }
        body_signals = {
            word for word in required_keywords if word.casefold() in body_lower
        }
        title_topic = bool(title_signals) or any(
            word.casefold() in title_lower for word in title_keywords
        )
        body_topic = len(body_signals) >= 2
        person = any(word in title for word in _PERSON_WORDS)
        event = any(word in original for word in _PERSON_EVENT_WORDS)

        if not title or not host or urlsplit(str(article.get("url"))).scheme != "https":
            status, reason = "rejected", "missing_title_or_original_https_url"
        elif str(article.get("url")) in (previously_used_urls or set()):
            status, reason = "rejected", "used_in_previous_digest"
        elif config.require_publication_date and published is None:
            status, reason = "review", "publication_date_unconfirmed"
        elif published is not None and published > now + timedelta(hours=1):
            status, reason = "review", "publication_date_in_future"
        elif any(marker in content for marker in config.contributor_markers):
            status, reason = "review", "contributor_content_requires_attribution_review"
        elif not title_topic and person and event:
            status, reason = "review", "event_lead_without_confirmed_diagnosis"
        elif not title_topic and body_topic:
            status, reason = "review", "cardiovascular_terms_only_in_body"
        elif not title_topic:
            status, reason = "rejected", "not_cardiovascular"
        elif any(phrase in title for phrase in config.caution_title_phrases):
            status, reason = "review", "sensational_headline_requires_review"
        elif config.hold_person_events and person and event:
            status, reason = "review", "person_event_requires_source_and_cause_review"
        elif len(content.strip()) < config.minimum_source_text_chars:
            status, reason = "review", "insufficient_original_article_text"
        else:
            status, reason = "ready", "topic_and_source_metadata_present"
            ready.append(article)

        audit.append(
            {
                "url": str(article.get("url") or ""),
                "title": title,
                "published_at": str(article.get("published_at") or ""),
                "status": status,
                "reason": reason,
            }
        )
    return ready, audit


def select_recent_articles(
    ranked: list[dict[str, Any]],
    config: HealthReviewConfig,
    *,
    max_articles: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Use 24h news first, then 48h and 72h only if needed."""
    now = now or datetime.now(UTC)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hours in config.selection_windows_hours:
        cutoff = now - timedelta(hours=hours)
        for article in ranked:
            url = str(article.get("url") or "")
            published = _published_at(article)
            if url in seen or published is None or published < cutoff:
                continue
            selected.append(article)
            seen.add(url)
            if len(selected) >= max_articles:
                return selected
        if len(selected) >= config.target_articles:
            break
    return selected


def generated_claim_issues(
    article: dict[str, Any], result: dict[str, Any]
) -> list[str]:
    """Flag conspicuous claims introduced by the model, not certify the rest."""
    original = (
        str(article.get("title") or "")
        + " "
        + str(article.get("content") or article.get("description") or "")
    )
    generated = " ".join(
        str(result.get(field) or "")
        for field in ("hook_title", "translated_title", "summary", "tldr")
    )
    issues = [
        f"unsupported_claim:{claim}"
        for claim in _SENSITIVE_CLAIMS
        if claim in generated and claim not in original
    ]
    for age in set(re.findall(r"\d{1,3}岁", generated)):
        if age not in original:
            issues.append(f"unsupported_age:{age}")
    if "导致" in generated and not any(
        word in original for word in ("导致", "引起", "造成")
    ):
        issues.append("unsupported_causation")
    return issues
