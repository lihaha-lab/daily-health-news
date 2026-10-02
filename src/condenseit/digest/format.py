"""Compact reader-facing digest markdown; source links stay in the archive table."""

from datetime import UTC, datetime
from typing import Any


def build_digest_markdown(
    categorized: dict[str, list[dict[str, Any]]],
    changes: list[dict[str, str]] | None = None,
    videos: list[dict[str, Any]] | None = None,
    *,
    title: str = "CondenseIt Digest",
    disclaimer: str = "",
) -> str:
    """Build a concise digest without embedding source URLs."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# {title}",
        "",
        stamp,
        "",
    ]

    for category in sorted(categorized.keys()):
        items = categorized[category]
        if not items:
            continue
        for item in items:
            lines.extend(_format_item(item))

    if videos:
        for item in videos:
            lines.extend(_format_item(item))

    if len(lines) == 4:
        lines.append("今日暂无符合主题的新闻。")

    return "\n".join(lines).strip() + "\n"


def _format_item(item: dict[str, Any]) -> list[str]:
    title = (item.get("title") or "Untitled").strip()
    summary = (item.get("summary") or "").strip()
    source = (item.get("source") or "").strip()
    published_at = (item.get("published_at") or "").strip()
    date = published_at[:10] if len(published_at) >= 10 else "日期未标注"

    return [
        f"### {date}｜{title}",
        f"**来源：** {source or '未标注'}",
        f"**摘要：** {summary or '暂无摘要'}",
        "",
    ]
