"""Publish a generated digest to Feishu Docs and WeCom destinations."""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _request_with_retry(
    client: httpx.Client, method: str, url: str, **kwargs: object
) -> httpx.Response:
    for attempt in range(3):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < 2:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            return response
        except httpx.TransportError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Request retries exhausted")


def publish_digest(
    markdown_text: str,
    *,
    articles: list[dict[str, object]] | None = None,
    published_at: str | None = None,
) -> dict[str, object]:
    """Publish configured destinations independently and report each result."""
    report: dict[str, object] = {}
    document_url = ""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if app_id and app_secret:
        try:
            document_url = _publish_feishu(
                markdown_text, app_id, app_secret, published_at=published_at
            )
            report["feishu"] = {"status": "sent", "url": document_url}
        except Exception as exc:
            logger.exception("Feishu digest publishing failed")
            report["feishu"] = {"status": "failed", "reason": str(exc)}
    else:
        report["feishu"] = {"status": "not_configured"}

    bitable_app = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    bitable_table = os.environ.get("FEISHU_BITABLE_TABLE_ID", "").strip()
    if app_id and app_secret and bitable_app and bitable_table:
        try:
            created_records = _publish_bitable(
                articles or [],
                published_at,
                app_id,
                app_secret,
                bitable_app,
                bitable_table,
            )
            report["feishu_bitable"] = {
                "status": "sent",
                "records": created_records,
            }
        except Exception as exc:
            logger.exception("Feishu Bitable publishing failed")
            report["feishu_bitable"] = {"status": "failed", "reason": str(exc)}
    else:
        report["feishu_bitable"] = {"status": "not_configured"}

    webhook = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
    if webhook:
        try:
            _publish_wecom(markdown_text, webhook, document_url)
            report["wecom"] = {"status": "sent"}
        except Exception as exc:
            logger.exception("WeCom digest publishing failed")
            report["wecom"] = {"status": "failed", "reason": str(exc)}
    else:
        report["wecom"] = {"status": "not_configured"}

    corp_id = os.environ.get("WECOM_CORP_ID", "").strip()
    agent_id = os.environ.get("WECOM_AGENT_ID", "").strip()
    app_secret = os.environ.get("WECOM_APP_SECRET", "").strip()
    user_id = os.environ.get("WECOM_TO_USER", "").strip()
    if corp_id and agent_id and app_secret and user_id:
        try:
            _publish_wecom_user(
                markdown_text, corp_id, agent_id, app_secret, user_id, document_url
            )
            report["wecom_user"] = {"status": "sent", "to": user_id}
        except Exception as exc:
            logger.exception("WeCom personal digest publishing failed")
            report["wecom_user"] = {"status": "failed", "reason": str(exc)}
    else:
        report["wecom_user"] = {"status": "not_configured"}
    return report


def _publish_feishu(
    markdown_text: str,
    app_id: str,
    app_secret: str,
    *,
    published_at: str | None = None,
) -> str:
    base_url = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/")
    published = _published_datetime(published_at)
    month = published.strftime("%Y-%m")
    day = published.strftime("%Y-%m-%d")
    folder_token = os.environ.get("FEISHU_FOLDER_TOKEN", "").strip()
    fixed_document_id = os.environ.get("FEISHU_DIGEST_DOCUMENT_ID", "").strip()
    fixed_document_url = os.environ.get("FEISHU_DIGEST_DOCUMENT_URL", "").strip()
    with httpx.Client(timeout=30) as client:
        token_response = _request_with_retry(
            client,
            "POST",
            f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        token_data = token_response.json()
        if token_data.get("code") != 0 or not token_data.get("tenant_access_token"):
            raise RuntimeError(
                f"Feishu token error: {token_data.get('msg', 'unknown')}"
            )
        headers = {"Authorization": f"Bearer {token_data['tenant_access_token']}"}
        registry_path = _feishu_month_registry_path()
        registry = _load_month_registry(registry_path)
        registry_key = "daily" if fixed_document_id else month
        month_entry = registry.get(registry_key, {})
        if fixed_document_id and month_entry.get("document_id") != fixed_document_id:
            month_entry = {"document_id": fixed_document_id, "published_days": []}
        document_id = fixed_document_id or str(month_entry.get("document_id") or "")
        document_url = (
            fixed_document_url if fixed_document_id else ""
        ) or f"https://www.feishu.cn/docx/{document_id}"
        if day in month_entry.get("published_days", []):
            return document_url

        if not document_id:
            payload: dict[str, object] = {"title": f"每日健康简报 | {month}"}
            if folder_token:
                payload["folder_token"] = folder_token
            create_response = _request_with_retry(
                client,
                "POST",
                f"{base_url}/open-apis/docx/v1/documents",
                headers=headers,
                json=payload,
            )
            create_data = create_response.json()
            if create_data.get("code") != 0:
                raise RuntimeError(
                    f"Feishu document error: {create_data.get('msg', 'unknown')}"
                )
            document = create_data.get("data", {}).get("document", {})
            document_id = str(document.get("document_id") or "")
            if not document_id:
                raise RuntimeError("Feishu did not return a document_id")
            month_entry = {"document_id": document_id, "published_days": []}
            registry[registry_key] = month_entry
            _save_month_registry(registry_path, registry)

        document_url = (
            fixed_document_url if fixed_document_id else ""
        ) or f"https://www.feishu.cn/docx/{document_id}"

        blocks = _feishu_digest_blocks(markdown_text, day)
        for start in range(0, len(blocks), 50):
            append_response = _request_with_retry(
                client,
                "POST",
                f"{base_url}/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                headers=headers,
                params={"document_revision_id": -1},
                json={"children": blocks[start : start + 50], "index": start},
            )
            append_data = append_response.json()
            if append_data.get("code") != 0:
                raise RuntimeError(
                    f"Feishu content error: {append_data.get('msg', 'unknown')}"
                )
        if fixed_document_id:
            month_entry.setdefault("published_days", []).append(day)
            registry[registry_key] = month_entry
            _save_month_registry(registry_path, registry)
            return document_url

        permission_url = (
            f"{base_url}/open-apis/drive/v1/permissions/{document_id}/public"
        )
        permission_payload = {"link_share_entity": "anyone_readable"}
        permission_response = _request_with_retry(
            client,
            "PATCH",
            permission_url,
            headers=headers,
            params={"type": "docx"},
            json=permission_payload,
        )
        permission_data = permission_response.json()
        if permission_data.get("code") != 0:
            raise RuntimeError(
                "Feishu share permission error: "
                f"{permission_data.get('msg', 'unknown')}"
            )
        verify_response = _request_with_retry(
            client,
            "GET",
            permission_url,
            headers=headers,
            params={"type": "docx"},
        )
        verify_data = verify_response.json()
        if verify_data.get("code") != 0:
            raise RuntimeError(
                f"Feishu share verification error: {verify_data.get('msg', 'unknown')}"
            )
        actual = verify_data.get("data", {}).get("permission_public", {})
        if actual.get("link_share_entity") != "anyone_readable":
            raise RuntimeError("Feishu did not enable anyone-with-link read access")
        month_entry.setdefault("published_days", []).append(day)
        _save_month_registry(registry_path, registry)
        return document_url


def _published_datetime(value: str | None) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
            return parsed.astimezone(ZoneInfo("Asia/Shanghai"))
        except ValueError:
            logger.warning("Invalid digest timestamp %r; using current date", value)
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _feishu_month_registry_path() -> Path:
    data_dir = Path(os.environ.get("CONDENSEIT_DATA_DIR", "data"))
    return data_dir / "feishu_monthly_docs.json"


def _load_month_registry(path: Path) -> dict[str, dict[str, object]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read Feishu monthly document registry")
        return {}


def _save_month_registry(path: Path, registry: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)


def _publish_bitable(
    articles: list[dict[str, object]],
    published_at: str | None,
    app_id: str,
    app_secret: str,
    app_token: str,
    table_id: str,
) -> int:
    """Write article rows into a configured Feishu Bitable table."""
    if not articles:
        return 0
    base_url = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/")
    briefing_day = _published_datetime(published_at).strftime("%Y-%m-%d")
    registry_path = (
        Path(os.environ.get("CONDENSEIT_DATA_DIR", "data")) / "feishu_bitable_seen.json"
    )
    seen = _load_seen_urls(registry_path)

    with httpx.Client(timeout=30) as client:
        token_response = _request_with_retry(
            client,
            "POST",
            f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        token_data = token_response.json()
        if token_data.get("code") != 0 or not token_data.get("tenant_access_token"):
            raise RuntimeError(
                f"Feishu token error: {token_data.get('msg', 'unknown')}"
            )
        headers = {"Authorization": f"Bearer {token_data['tenant_access_token']}"}
        created = 0
        for article in articles:
            url = str(article.get("url") or "").strip()
            if not url or url in seen:
                continue
            title = str(article.get("hook_title") or article.get("title") or "健康新闻")
            title = " ".join(title.split())[:80]
            fields: dict[str, object] = {
                "日期": briefing_day,
                "吸睛标题": title,
                "来源链接": url,
                "信息来源": str(article.get("source") or "")[:200],
                "简短看点": str(article.get("tldr") or article.get("summary") or "")[
                    :500
                ],
            }
            response = _request_with_retry(
                client,
                "POST",
                f"{base_url}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                headers=headers,
                json={"fields": fields},
            )
            data = response.json()
            if data.get("code") != 0:
                raise RuntimeError(
                    f"Feishu Bitable error: {data.get('msg', 'unknown')}"
                )
            seen.add(url)
            created += 1
            _save_seen_urls(registry_path, seen)
    return created


def _load_seen_urls(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except FileNotFoundError:
        return set()
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read Feishu Bitable duplicate registry")
        return set()


def _save_seen_urls(path: Path, urls: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(sorted(urls), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)


def _feishu_digest_blocks(markdown_text: str, day: str) -> list[dict[str, object]]:
    """Turn the compact digest into native Feishu blocks without Markdown marks."""
    published = datetime.fromisoformat(day)
    date_label = f"{published.month}月{published.day}日"
    blocks: list[dict[str, object]] = [
        {
            "block_type": 4,
            "heading2": {
                "elements": [{"text_run": {"content": date_label}}],
            },
        }
    ]
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith("# ")
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", line)
        ):
            continue
        bold = line.startswith("### ")
        if bold:
            line = line[4:]
            line = re.sub(r"^\d{4}-\d{2}-\d{2}｜", "", line)
        line = line.replace("**来源：**", "来源：", 1)
        line = line.replace("**摘要：**", "摘要：", 1)
        line = re.sub(r"^(来源：|摘要：)\s+", r"\1", line)
        for start in range(0, len(line), 800):
            run: dict[str, object] = {"content": line[start : start + 800]}
            if bold:
                run["text_element_style"] = {"bold": True}
            blocks.append(
                {
                    "block_type": 5 if bold else 2,
                    "heading3" if bold else "text": {"elements": [{"text_run": run}]},
                }
            )
    return blocks


def _publish_wecom(markdown_text: str, webhook: str, document_url: str) -> None:
    lines = [line.strip() for line in markdown_text.splitlines() if line.strip()]
    excerpt = "\n".join(lines[:12])
    content = "每日健康简报\n" + excerpt
    if document_url:
        content += f"\n\n[查看飞书完整简报]({document_url})"
    if len(content) > 4000:
        content = content[:3950] + "\n\n内容较长，请查看完整简报。"
    with httpx.Client(timeout=30) as client:
        response = _request_with_retry(
            client,
            "POST",
            webhook,
            json={"msgtype": "markdown", "markdown": {"content": content}},
        )
    result = response.json()
    if result.get("errcode", 0) != 0:
        raise RuntimeError(f"WeCom webhook error: {result.get('errmsg', 'unknown')}")


def _publish_wecom_user(
    markdown_text: str,
    corp_id: str,
    agent_id: str,
    app_secret: str,
    user_id: str,
    document_url: str,
) -> None:
    """Send a Markdown digest to a WeCom member through a self-built app."""
    base_url = os.environ.get(
        "WECOM_API_BASE_URL", "https://qyapi.weixin.qq.com"
    ).rstrip("/")
    lines = [line.strip() for line in markdown_text.splitlines() if line.strip()]
    content = "每日健康简报\n" + "\n".join(lines[:12])
    if document_url:
        content += f"\n\n[查看飞书完整简报]({document_url})"
    if len(content) > 2048:
        content = content[:1980] + "\n\n内容较长，请查看完整简报。"

    with httpx.Client(timeout=30) as client:
        token_response = _request_with_retry(
            client,
            "GET",
            f"{base_url}/cgi-bin/gettoken",
            params={"corpid": corp_id, "corpsecret": app_secret},
        )
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if token_data.get("errcode", 0) != 0 or not access_token:
            raise RuntimeError(
                f"WeCom token error: {token_data.get('errmsg', 'unknown')}"
            )

        response = _request_with_retry(
            client,
            "POST",
            f"{base_url}/cgi-bin/message/send",
            params={"access_token": access_token},
            json={
                "touser": user_id,
                "msgtype": "markdown",
                "agentid": int(agent_id),
                "markdown": {"content": content},
                "safe": 0,
            },
        )
    result = response.json()
    if result.get("errcode", 0) != 0:
        raise RuntimeError(
            f"WeCom app message error: {result.get('errmsg', 'unknown')}"
        )
