import json
import os
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

sys.path.insert(0, os.getcwd())
sys.modules.setdefault("yaml", types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {}))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))

from apps.cli.queue_manager import ApplicationCandidate, ReviewQueueManager
from apps.cli.run_store import RunStore
from apps.preview.main import create_app


@pytest.fixture()
def queue_context(tmp_path: Path):
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa-tester")

    candidate_dir = record.run_dir / "cand-1"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    plan_path = candidate_dir / "form-plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    manager = ReviewQueueManager(run_store=store, run_record=record)
    candidate = ApplicationCandidate(
        id="cand-1",
        posting={"postingUrl": "https://example.com/role", "title": "QA Analyst"},
        form_plan_path=str(plan_path),
        discovered_at="2025-01-01T00:00:00Z",
        state="discovered",
    )
    manager.enqueue(candidate)
    manager.update_state("cand-1", "awaiting_decision")

    app = create_app(demo=False, run_store=store, run_record=record)
    client = TestClient(app)
    return {"client": client, "store": store, "record": record}


def test_queue_get_returns_snapshot(queue_context):
    client: TestClient = queue_context["client"]
    record = queue_context["record"]

    response = client.get(f"/api/queue/{record.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["pending"], "queue endpoint should expose pending candidates"
    assert data["pending"][0]["state"] == "awaiting_decision"


def test_queue_decision_persists_and_updates(queue_context):
    client: TestClient = queue_context["client"]
    record = queue_context["record"]

    payload = {
        "decisionId": "dec-1",
        "candidateId": "cand-1",
        "outcome": "approve",
        "mode": "human",
        "confidence": 0.9,
        "rationale": "Looks good",
        "timestamp": "2025-01-01T00:10:00Z",
    }

    response = client.post(f"/api/queue/{record.id}/decision", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"]["decisionId"] == "dec-1"
    assert data["queue"]["pending"][0]["state"] == "submitted"

    run_payload = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    decisions = run_payload.get("decisions", [])
    assert decisions and decisions[0]["decisionId"] == "dec-1"

    queue_file = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert queue_file["decided"], "queue persistence should store decisions"


def test_queue_decision_missing_candidate_returns_error(queue_context):
    client: TestClient = queue_context["client"]
    record = queue_context["record"]

    payload = {
        "decisionId": "dec-404",
        "candidateId": "missing",
        "outcome": "abort",
        "mode": "human",
        "confidence": 0.5,
        "rationale": "Not found",
    }

    response = client.post(f"/api/queue/{record.id}/decision", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "candidate_not_found"
