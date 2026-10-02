"""Tests for customer delivery adapters."""

from condenseit.publishers.delivery import (
    _feishu_digest_blocks,
    publish_digest,
)


def test_feishu_blocks_split_long_lines_and_ignore_empty_lines() -> None:
    blocks = _feishu_digest_blocks("\n" + "x" * 1700 + "\n", "2026-10-02")
    contents = [
        block["text"]["elements"][0]["text_run"]["content"]
        for block in blocks[1:]
    ]
    assert [len(content) for content in contents] == [800, 800, 100]


def test_feishu_digest_uses_native_date_and_bold_titles() -> None:
    markdown = (
        "# 每日心脑健康简报\n\n2026-09-29\n\n"
        "### 2026-09-28｜别等胸痛才护心\n"
        "**来源：** 新华社\n"
        "**摘要：** 日常管理血压血脂，胸痛时及时就医。\n"
    )
    blocks = _feishu_digest_blocks(markdown, "2026-09-30")

    assert blocks[0] == {
        "block_type": 4,
        "heading2": {"elements": [{"text_run": {"content": "9月30日"}}]},
    }
    assert blocks[1]["block_type"] == 5
    assert blocks[1]["heading3"]["elements"][0]["text_run"] == {
        "content": "别等胸痛才护心",
        "text_element_style": {"bold": True},
    }
    assert blocks[2]["text"]["elements"][0]["text_run"]["content"] == "来源：新华社"
    assert blocks[3]["text"]["elements"][0]["text_run"]["content"].startswith("摘要：")


def test_delivery_reports_missing_destinations(monkeypatch) -> None:
    for key in (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "WECOM_WEBHOOK_URL",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_BITABLE_TABLE_ID",
        "WECOM_CORP_ID",
        "WECOM_AGENT_ID",
        "WECOM_APP_SECRET",
        "WECOM_TO_USER",
    ):
        monkeypatch.delenv(key, raising=False)
    assert publish_digest("briefing") == {
        "feishu": {"status": "not_configured"},
        "feishu_bitable": {"status": "not_configured"},
        "wecom": {"status": "not_configured"},
        "wecom_user": {"status": "not_configured"},
    }


def test_bitable_delivery_reports_created_record_count(monkeypatch) -> None:
    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "table")
    monkeypatch.setattr(
        "condenseit.publishers.delivery._publish_feishu",
        lambda *_args, **_kwargs: "https://feishu.example/docx/test",
    )
    monkeypatch.setattr(
        "condenseit.publishers.delivery._publish_bitable",
        lambda *_args, **_kwargs: 1,
    )

    report = publish_digest("briefing", articles=[{"url": "https://news.example/1"}])

    assert report["feishu_bitable"] == {"status": "sent", "records": 1}


def test_wecom_personal_delivery_uses_app_and_member_id(monkeypatch) -> None:
    import httpx

    monkeypatch.setenv("WECOM_CORP_ID", "corp")
    monkeypatch.setenv("WECOM_AGENT_ID", "100001")
    monkeypatch.setenv("WECOM_APP_SECRET", "secret")
    monkeypatch.setenv("WECOM_TO_USER", "member")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            data = (
                {"errcode": 0, "access_token": "token"}
                if url.endswith("gettoken")
                else {"errcode": 0}
            )
            return httpx.Response(200, json=data, request=httpx.Request(method, url))

    fake = FakeClient()
    monkeypatch.setattr(
        "condenseit.publishers.delivery.httpx.Client", lambda **kwargs: fake
    )
    monkeypatch.setattr(
        "condenseit.publishers.delivery._request_with_retry",
        lambda client, method, url, **kwargs: client.request(method, url, **kwargs),
    )

    report = publish_digest("# Today's health briefing")
    send = next(call for call in fake.calls if call[1].endswith("message/send"))
    assert report["wecom_user"] == {"status": "sent", "to": "member"}
    assert send[2]["json"]["touser"] == "member"
    assert send[2]["json"]["agentid"] == 100001
    assert send[2]["json"]["markdown"]["content"].startswith("每日健康简报")


def test_feishu_sharing_requires_link_read_permission(monkeypatch, tmp_path) -> None:
    import httpx
    import pytest

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if "/auth/" in url:
                data = {"code": 0, "tenant_access_token": "token"}
            elif method == "POST" and url.endswith("/documents"):
                data = {"code": 0, "data": {"document": {"document_id": "doc-1"}}}
            elif "/blocks/" in url:
                data = {"code": 0}
            elif method == "PATCH":
                data = {"code": 0}
            elif method == "GET":
                data = {
                    "code": 0,
                    "data": {
                        "permission_public": {"link_share_entity": "anyone_readable"}
                    },
                }
            else:
                pytest.fail(f"Unexpected Feishu request: {method} {url}")
            return httpx.Response(200, json=data, request=httpx.Request(method, url))

    fake = FakeClient()
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "condenseit.publishers.delivery.httpx.Client", lambda **kwargs: fake
    )
    monkeypatch.setattr(
        "condenseit.publishers.delivery._request_with_retry",
        lambda client, method, url, **kwargs: client.request(method, url, **kwargs),
    )
    from condenseit.publishers.delivery import _publish_feishu

    assert _publish_feishu(
        "briefing", "app", "secret", published_at="2026-09-24T00:00:00Z"
    ).endswith("/docx/doc-1")
    create_call = next(call for call in fake.calls if call[1].endswith("/documents"))
    assert create_call[2]["json"]["title"] == "每日健康简报 | 2026-09"
    content_call = next(call for call in fake.calls if "/blocks/" in call[1])
    assert content_call[2]["json"]["index"] == 0
    patch_call = next(call for call in fake.calls if call[0] == "PATCH")
    assert patch_call[2]["json"]["link_share_entity"] == "anyone_readable"
    assert patch_call[2]["json"] == {"link_share_entity": "anyone_readable"}


def test_feishu_sharing_verification_rejects_private_document(
    monkeypatch, tmp_path
) -> None:
    import httpx
    import pytest

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            if "/auth/" in url:
                data = {"code": 0, "tenant_access_token": "token"}
            elif method == "POST" and url.endswith("/documents"):
                data = {"code": 0, "data": {"document": {"document_id": "doc-1"}}}
            elif "/blocks/" in url:
                data = {"code": 0}
            elif method == "PATCH":
                data = {"code": 0}
            else:
                data = {
                    "code": 0,
                    "data": {
                        "permission_public": {"link_share_entity": "tenant_readable"}
                    },
                }
            return httpx.Response(200, json=data, request=httpx.Request(method, url))

    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "condenseit.publishers.delivery.httpx.Client", lambda **kwargs: FakeClient()
    )
    monkeypatch.setattr(
        "condenseit.publishers.delivery._request_with_retry",
        lambda client, method, url, **kwargs: client.request(method, url, **kwargs),
    )
    from condenseit.publishers.delivery import _publish_feishu

    with pytest.raises(RuntimeError, match="anyone-with-link read access"):
        _publish_feishu("briefing", "app", "secret")


def test_fixed_feishu_document_prepends_without_creating_monthly_docs(
    monkeypatch, tmp_path
) -> None:
    import json

    import httpx

    from condenseit.publishers.delivery import _publish_feishu

    calls = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            if url.endswith("tenant_access_token/internal"):
                data = {"code": 0, "tenant_access_token": "token"}
            elif url.endswith("/blocks/fixed-doc/children"):
                data = {"code": 0}
            else:
                raise AssertionError(f"Unexpected request: {method} {url}")
            return httpx.Response(200, json=data, request=httpx.Request(method, url))

    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FEISHU_DIGEST_DOCUMENT_ID", "fixed-doc")
    monkeypatch.setenv("FEISHU_DIGEST_DOCUMENT_URL", "https://example.com/base/doc")
    monkeypatch.setattr(
        "condenseit.publishers.delivery.httpx.Client", lambda **_: FakeClient()
    )

    first = "2026-10-02T00:00:00Z"
    assert _publish_feishu("briefing", "app", "secret", published_at=first) == (
        "https://example.com/base/doc"
    )
    assert _publish_feishu("briefing", "app", "secret", published_at=first) == (
        "https://example.com/base/doc"
    )
    assert _publish_feishu(
        "next briefing", "app", "secret", published_at="2026-10-03T00:00:00Z"
    ) == "https://example.com/base/doc"

    inserts = [call for call in calls if "/blocks/" in call[1]]
    assert len(inserts) == 2
    assert all(call[2]["json"]["index"] == 0 for call in inserts)
    registry = json.loads((tmp_path / "feishu_monthly_docs.json").read_text("utf-8"))
    assert registry["daily"] == {
        "document_id": "fixed-doc",
        "published_days": ["2026-10-02", "2026-10-03"],
    }
