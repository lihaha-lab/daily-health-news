from pathlib import Path

import pytest

from condenseit.services.digest_runner import execute_digest
from condenseit.store.database import ContentStore


def test_dry_run_keeps_audit_without_replacing_latest_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "health_review:\n  enabled: true\n"
        "feeds: []\ngoogle_news: []\n"
        "llm:\n  provider: ollama\n"
        "output:\n  path: " + str(tmp_path / "output").replace("\\", "/") + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONDENSEIT_DATA_DIR", str(data_dir))

    result = execute_digest(str(config_path), dry_run=True, skip_deploy=True)

    store = ContentStore(db_path=data_dir / "condenseit.db")
    assert result["digest_id"] is None
    assert store.latest_digest() is None
    assert store.latest_candidate_audit() is not None
    assert not (tmp_path / "output" / "latest.md").exists()
    store.close()
