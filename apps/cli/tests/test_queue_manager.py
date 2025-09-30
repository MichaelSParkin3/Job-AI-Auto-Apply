import json
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, os.getcwd())
sys.modules.setdefault("yaml", types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {}))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))

from apps.cli.queue_manager import (
    ApplicationCandidate,
    ReviewQueueManager,
    SubmissionDecision,
)
from apps.cli.run_store import RunStore


def test_queue_manager_persists_transitions(tmp_path: Path) -> None:
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa-tester")

    candidate_dir = record.run_dir / "candidate-1"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    plan_path = candidate_dir / "form-plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    manager = ReviewQueueManager(run_store=store, run_record=record)

    candidate = ApplicationCandidate(
        id="candidate-1",
        posting={"postingUrl": "https://example.com", "title": "QA Engineer"},
        form_plan_path=str(plan_path),
        discovered_at="2025-01-01T00:00:00Z",
        state="discovered",
    )

    snapshot = manager.enqueue(candidate)
    assert snapshot.pending and snapshot.pending[0].id == "candidate-1"
    raw_snapshot = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert raw_snapshot["pending"][0]["state"] == "discovered"

    manager.update_state("candidate-1", "planned", form_plan_path=str(plan_path))
    raw_snapshot = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert raw_snapshot["pending"][0]["state"] == "planned"
    assert raw_snapshot["pending"][0]["formPlanPath"] == str(plan_path)

    decision = SubmissionDecision(
        decision_id="dec-1",
        candidate_id="candidate-1",
        outcome="approve",
        mode="human",
        confidence=0.95,
        rationale="Ready to submit",
        timestamp="2025-01-01T00:10:00Z",
    )

    manager.record_decision(decision)
    raw_snapshot = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert raw_snapshot["pending"][0]["lastDecisionId"] == "dec-1"
    assert raw_snapshot["pending"][0]["state"] == "decided"
    assert raw_snapshot["decided"][0]["decisionId"] == "dec-1"

    manager.reload()
    assert manager.snapshot.pending[0].last_decision_id == "dec-1"
    assert manager.snapshot.decided[0].decision_id == "dec-1"
