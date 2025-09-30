import json
import os
import sys
import types
from datetime import datetime, timezone
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
    assert snapshot.pending[0].assigned_mode == "human"
    raw_snapshot = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert raw_snapshot["pending"][0]["state"] == "discovered"
    assert raw_snapshot["pending"][0]["assignedMode"] == "human"

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
    stored_decision = store.record_submission_decision(record, decision.to_payload())
    raw_snapshot = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert raw_snapshot["pending"][0]["lastDecisionId"] == "dec-1"
    assert raw_snapshot["pending"][0]["state"] == "submitted"
    assert raw_snapshot["decided"][0]["decisionId"] == "dec-1"
    assert raw_snapshot["decided"][0]["rationaleHash"].startswith("sha256:")
    assert "rationale" not in raw_snapshot["decided"][0]

    manager.reload()
    assert manager.snapshot.pending[0].last_decision_id == "dec-1"
    assert manager.snapshot.pending[0].state == "submitted"
    assert manager.snapshot.decided[0].decision_id == "dec-1"
    payload = manager.snapshot.decided[0].to_payload()
    assert payload["rationaleHash"].startswith("sha256:")

    run_payload = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    decision_entry = run_payload["decisions"][0]
    assert decision_entry["artifactPath"].startswith("decisions/")
    assert decision_entry["rationaleHash"] == stored_decision["rationaleHash"]


def test_assign_mode_moves_candidate_and_persists(tmp_path: Path) -> None:
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa-tester")
    manager = ReviewQueueManager(run_store=store, run_record=record)

    candidate = ApplicationCandidate(
        id="cand-override",
        posting={"postingUrl": "https://example.com/job"},
        form_plan_path=None,
        discovered_at="2025-01-01T00:00:00Z",
        state="awaiting_decision",
        assigned_mode="ai",
    )
    manager.enqueue(candidate)
    manager.assign_mode("cand-override", "human", trigger="test")

    snapshot = manager.snapshot
    assert not any(c.id == "cand-override" for c in snapshot.pending)
    escalated = [c for c in snapshot.escalated if c.id == "cand-override"]
    assert escalated and escalated[0].assigned_mode == "human"

    payload = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert payload["escalated"][0]["assignedMode"] == "human"


def test_watchdog_reassigns_stalled_candidates(tmp_path: Path) -> None:
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa-tester")
    manager = ReviewQueueManager(run_store=store, run_record=record)

    candidate = ApplicationCandidate(
        id="cand-ai",
        posting={"postingUrl": "https://example.com"},
        form_plan_path=None,
        discovered_at="2025-01-01T00:00:00Z",
        state="awaiting_decision",
        assigned_mode="ai",
        updated_at="2025-01-01T00:00:00Z",
    )
    manager.enqueue(candidate)
    manager.assign_mode("cand-ai", "ai", trigger="test", reason="assign")
    manager.snapshot.pending[0].updated_at = "2025-01-01T00:00:00Z"

    now = datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc)
    reassigned = manager.enforce_watchdog(30, now=now)
    assert reassigned == ["cand-ai"]
    assert manager.snapshot.escalated[0].assigned_mode == "human"
    payload = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert payload["escalated"][0]["assignedMode"] == "human"
