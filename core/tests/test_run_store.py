import json
import os
import sys
from pathlib import Path

import pytest

# Ensure repo root is on path for package imports
sys.path.insert(0, os.getcwd())

from apps.cli.history_store import HistoryWriter
from apps.cli.main import preview_demo
from apps.cli.run_store import RunStore
from apps.cli.runtime_state import get_run_context, set_run_context
from apps.cli.utils import log_event


@pytest.fixture(autouse=True)
def reset_context():
    """Reset the run context before and after each test."""

    previous = set_run_context(None)
    yield
    set_run_context(previous)


def test_run_store_creates_seeded_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """RunStore should create a deterministic folder with seeded run.json."""

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="demo-profile")

    assert record.run_dir.exists()
    data = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    assert data["id"] == record.id
    assert data["profileId"] == "demo-profile"
    assert data["logsPath"].endswith("actions.log")

    log_event(
        {
            "event": "test.piiredaction",
            "message": "Reach out at alice@example.com for updates.",
        }
    )
    log_lines = record.logs_path.read_text(encoding="utf-8").splitlines()
    assert log_lines, "actions.log should receive entries"
    last_entry = json.loads(log_lines[-1])
    assert last_entry["runId"] == record.id
    assert "{{REDACTED:EMAIL}}" in last_entry["message"]


def test_history_writer_appends_redacted_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """HistoryWriter appends demo entries with redacted summaries."""

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    store.start_demo_run(profile_id=None)
    context = get_run_context()
    assert context is not None
    writer = HistoryWriter(base=tmp_path)
    writer.append_demo_entry(context, summary="Call +1 555-123-4567 to confirm.")

    history_lines = writer.history_path.read_text(encoding="utf-8").splitlines()
    assert history_lines, "history.jsonl should accumulate entries"
    entry = json.loads(history_lines[-1])
    assert entry["status"] == "skipped"
    assert entry["runPath"].endswith(context.id)
    assert entry["summary"].endswith("{{REDACTED:PHONE}} to confirm.")


def test_preview_demo_records_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """preview demo should append a history entry for QA traceability."""

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "apps.cli.main.run_preview_service", lambda *args, **kwargs: None
    )

    preview_demo(no_browser=True, port=None)

    history_file = tmp_path / "history" / "history.jsonl"
    assert history_file.exists(), "preview demo should create history.jsonl"
    entry = json.loads(history_file.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["status"] == "skipped"
    assert entry["runPath"].startswith(str((tmp_path / "runs").resolve()))
    assert "Preview demo session" in entry["summary"]
