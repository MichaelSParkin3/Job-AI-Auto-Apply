import os
import sys
import types
from pathlib import Path

sys.path.insert(0, os.getcwd())
sys.modules.setdefault("yaml", types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {}))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))

from apps.cli.queue_manager import ApplicationCandidate, ReviewQueueManager, SubmissionDecision
from apps.cli.run_store import RunStore


def test_queue_snapshot_survives_restart(tmp_path: Path) -> None:
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa-tester")

    manager = ReviewQueueManager(run_store=store, run_record=record)

    for index in range(2):
        candidate_dir = record.run_dir / f"cand-{index}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        plan_path = candidate_dir / "form-plan.json"
        plan_path.write_text("{}", encoding="utf-8")
        candidate = ApplicationCandidate(
            id=f"cand-{index}",
            posting={"postingUrl": f"https://example.com/{index}", "title": "Role"},
            form_plan_path=str(plan_path),
            discovered_at=f"2025-01-01T00:0{index}:00Z",
            state="discovered",
        )
        manager.enqueue(candidate)
        manager.update_state(candidate.id, "planned", form_plan_path=str(plan_path))

    decision = SubmissionDecision(
        decision_id="dec-1",
        candidate_id="cand-0",
        outcome="approve",
        mode="human",
        confidence=0.9,
        rationale="Ship it",
        timestamp="2025-01-01T00:10:00Z",
    )
    manager.record_decision(decision)

    restart_store = RunStore(base=tmp_path)
    restart_manager = ReviewQueueManager(run_store=restart_store, run_record=record)

    snapshot = restart_manager.snapshot
    assert {candidate.id for candidate in snapshot.pending} == {"cand-0", "cand-1"}
    states = {candidate.id: candidate.state for candidate in snapshot.pending}
    assert states["cand-0"] == "submitted"
    assert states["cand-1"] == "planned"
    assert snapshot.decided and snapshot.decided[0].decision_id == "dec-1"
