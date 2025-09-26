import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.cli.history_store import HistoryWriter
from apps.cli.run_store import RunStore
from apps.cli.runtime_state import get_run_context, set_run_context
from apps.preview.main import create_app


@pytest.fixture(autouse=True)
def reset_context():
    previous = set_run_context(None)
    yield
    set_run_context(previous)


def test_preview_flow_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="demo-profile")
    store.bootstrap_demo_preview(record, limit=1, profile_id="demo-profile")
    context = get_run_context()
    assert context is not None
    writer = HistoryWriter(base=tmp_path)

    app = create_app(
        static_dir=tmp_path,
        demo=True,
        run_store=store,
        run_record=record,
        history_writer=writer,
        run_context=context,
    )
    client = TestClient(app)

    create = client.post("/api/run/preview", json={"dryRun": True, "limit": 1})
    assert create.status_code == 200
    data = create.json()
    run_id = data["runId"]
    assert data["dryRun"] is True
    assert data["metadata"]["profileId"] == "demo-profile"
    assert data["metadata"]["profileLabel"] == "Demo Profile"
    assert data["metadata"]["mode"] == "demo"
    assert "screenshotUrl" in data["preview"]

    edit = client.post(f"/api/run/{run_id}/edit", json={"text": "Needs tweak"})
    assert edit.status_code == 200
    run_payload = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    assert run_payload["preview"]["edits"] == "Needs tweak"
    assert run_payload["status"] == "review"

    approve = client.post(f"/api/run/{run_id}/approve")
    assert approve.status_code == 200
    run_payload = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    assert run_payload["status"] == "approved"
    assert run_payload["preview"]["decision"] == "approved"
    assert run_payload["preview"]["decidedAt"]

    history_lines = writer.history_path.read_text(encoding="utf-8").splitlines()
    assert history_lines
    history_entry = json.loads(history_lines[-1])
    assert history_entry["decision"] == "approved"
    assert history_entry["notes"] == "Needs tweak"

    updates = client.get(f"/api/run/{run_id}/updates")
    assert updates.status_code == 200
    events = updates.json()["events"]
    assert any(event["type"] == "preview.approved" for event in events)


def test_missing_ui_returns_hint(tmp_path: Path):
    empty_dir = tmp_path / "static"
    empty_dir.mkdir()
    app = create_app(static_dir=empty_dir, demo=True)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "missing_ui"
