import json
import os
import sys
import types
from pathlib import Path

import pytest

# Ensure repo root is on path for package imports
sys.path.insert(0, os.getcwd())
sys.modules.setdefault("yaml", types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {}))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))
if "pydantic" not in sys.modules:
    class _BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self) -> dict[str, object]:
            return dict(self.__dict__)

    def _field(default=None, **_kwargs):  # pragma: no cover - simple stub
        return default

    class _ValidationError(Exception):
        pass

    def _identity_validator(*_args, **_kwargs):  # pragma: no cover - simple stub
        def _decorator(func):
            return func

        return _decorator

    sys.modules["pydantic"] = types.SimpleNamespace(
        BaseModel=_BaseModel,
        Field=_field,
        ValidationError=_ValidationError,
        ConfigDict=dict,
        field_validator=_identity_validator,
        model_validator=_identity_validator,
        root_validator=_identity_validator,
        validator=_identity_validator,
    )

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
    binding_payload = {
        "id": "demo-profile",
        "display_name": "Demo Profile",
        "valid": True,
        "resume": {"path": "/tmp/demo-profile/resume.pdf", "exists": True},
        "user_data_dir": "/tmp/browser/demo-profile",
        "qa_overrides": {},
        "model_overrides": {},
        "browser": {},
        "errors": [],
    }
    record = store.start_demo_run(
        profile_id="demo-profile",
        profile_binding=binding_payload,
    )

    assert record.run_dir.exists()
    data = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    assert data["id"] == record.id
    assert data["profileId"] == "demo-profile"
    assert data["logsPath"].endswith("actions.log")
    assert data["status"] == "review"
    assert data["mode"] == "review"
    assert data["decisions"] == []
    assert data["queue"]["mode"] == "review"
    assert data["preview"]["summary"]
    assert data["preview"]["decision"] == "pending"
    assert data["metadata"]["profileLabel"] == "Demo Profile"
    assert data["metadata"]["mode"] == "demo"
    assert data["metadata"]["profileBinding"] == binding_payload
    screenshot_path = Path(data["preview"]["screenshotPath"])
    assert screenshot_path.exists()

    context = get_run_context()
    assert context is not None
    assert context.profile_binding == binding_payload

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
    writer.append_demo_entry(
        context,
        summary="Call +1 555-123-4567 to confirm.",
        decision="initialized",
    )

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

    actions_log = tmp_path / "runs"
    run_dir = next(actions_log.iterdir())
    guardrail_events = [
        json.loads(line)
        for line in (run_dir / "actions.log").read_text(encoding="utf-8").splitlines()
        if "guardrail.demo.no_network" in line
    ]
    assert guardrail_events, "guardrail event should be recorded in actions.log"


def test_record_submission_decision_hashes_rationale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="auditor")
    decision_payload = {
        "decisionId": "dec-42",
        "candidateId": "cand-1",
        "outcome": "approve",
        "mode": "human",
        "confidence": 0.87,
        "rationale": "Contact candidate via qa@example.com for confirmation.",
        "timestamp": "2025-01-02T00:00:00Z",
    }
    stored = store.record_submission_decision(record, decision_payload)
    assert stored["artifactPath"] == "decisions/dec-42.json"
    assert stored["rationaleHash"].startswith("sha256:")
    assert stored["rationaleRedacted"] is True
    assert stored["rationaleLength"] == len(decision_payload["rationale"])
    assert "{{REDACTED:EMAIL}}" in stored["rationalePreview"]

    artifact_path = record.run_dir / stored["artifactPath"]
    assert artifact_path.exists()
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_payload["rationaleHash"] == stored["rationaleHash"]

    run_data = store.load_run_payload(record)
    assert run_data["decisions"][0]["artifactPath"] == stored["artifactPath"]
    assert run_data["decisions"][0]["rationaleHash"] == stored["rationaleHash"]


def test_history_writer_decision_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa")
    context = get_run_context()
    assert context is not None

    decision = {
        "decisionId": "dec-100",
        "candidateId": "cand-9",
        "outcome": "approve",
        "mode": "human",
        "confidence": 0.9,
        "rationale": "Looks great, proceed with submission.",
        "timestamp": "2025-03-04T12:00:00Z",
    }
    stored = store.record_submission_decision(record, decision)
    queue_payload = store.load_queue_snapshot(record)
    queue_payload.setdefault("decided", []).append(stored)
    queue_payload["lastUpdated"] = stored["timestamp"]
    store.save_queue_snapshot(record, queue_payload)

    writer = HistoryWriter(base=tmp_path)
    run_payload = store.load_run_payload(record)
    writer.append_decision_summary(
        context,
        run_payload=run_payload,
        queue_payload=queue_payload,
        decision_payload=stored,
    )

    lines = writer.history_path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    assert entry["decisions"]["byOutcome"]["approve"] == 1
    assert entry["queueDepth"]["decided"] == 1
    assert entry["decision"]["rationaleHash"] == stored["rationaleHash"]
    assert entry["decision"]["rationaleRedacted"] is False
    assert entry["mode"] == run_payload["mode"]


def test_history_writer_atomic_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa")
    context = get_run_context()
    assert context is not None
    writer = HistoryWriter(base=tmp_path)
    writer.append_demo_entry(context, summary="First entry", decision="init")
    original = writer.history_path.read_text(encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr("apps.cli.history_store.os.replace", boom)
    with pytest.raises(OSError):
        writer.append_entry({"id": record.id, "status": "skipped"})

    assert writer.history_path.read_text(encoding="utf-8") == original
