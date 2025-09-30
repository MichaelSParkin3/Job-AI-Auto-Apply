"""Domain models and persistence helpers for the review queue."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Mapping, Optional

from .run_store import RunRecord, RunStore
from .utils import log_event

CandidateState = str
QueueMode = str
DecisionOutcome = str
DecisionMode = str


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class ApplicationCandidate:
    """Canonical representation of a candidate awaiting review."""

    id: str
    posting: Mapping[str, object]
    form_plan_path: Optional[str]
    discovered_at: str
    state: CandidateState = "discovered"
    last_decision_id: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "id": self.id,
            "posting": dict(self.posting),
            "discoveredAt": self.discovered_at,
            "state": self.state,
        }
        if self.form_plan_path:
            payload["formPlanPath"] = self.form_plan_path
        if self.last_decision_id:
            payload["lastDecisionId"] = self.last_decision_id
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ApplicationCandidate":
        return cls(
            id=str(payload.get("id")),
            posting=dict(payload.get("posting", {})),
            form_plan_path=payload.get("formPlanPath") or None,
            discovered_at=str(payload.get("discoveredAt")),
            state=str(payload.get("state", "discovered")),
            last_decision_id=payload.get("lastDecisionId") or None,
        )

    def update_from(self, other: "ApplicationCandidate") -> None:
        self.posting = dict(other.posting)
        self.form_plan_path = other.form_plan_path or self.form_plan_path
        self.discovered_at = other.discovered_at
        self.state = other.state
        if other.last_decision_id:
            self.last_decision_id = other.last_decision_id


@dataclass
class SubmissionDecision:
    """Structured outcome for a queue candidate."""

    decision_id: str
    candidate_id: str
    outcome: DecisionOutcome
    mode: DecisionMode
    confidence: float
    rationale: str
    timestamp: str
    requested_changes: Optional[List[Mapping[str, object]]] = None

    def to_payload(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "decisionId": self.decision_id,
            "candidateId": self.candidate_id,
            "outcome": self.outcome,
            "mode": self.mode,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "timestamp": self.timestamp,
        }
        if self.requested_changes is not None:
            payload["requestedChanges"] = [dict(item) for item in self.requested_changes]
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SubmissionDecision":
        requested = payload.get("requestedChanges")
        return cls(
            decision_id=str(payload.get("decisionId")),
            candidate_id=str(payload.get("candidateId")),
            outcome=str(payload.get("outcome")),
            mode=str(payload.get("mode")),
            confidence=float(payload.get("confidence", 0.0)),
            rationale=str(payload.get("rationale", "")),
            timestamp=str(payload.get("timestamp")),
            requested_changes=list(requested) if isinstance(requested, Iterable) else None,
        )


@dataclass
class ReviewQueueSnapshot:
    """Aggregate representation persisted to queue.json."""

    mode: QueueMode
    pending: List[ApplicationCandidate] = field(default_factory=list)
    decided: List[SubmissionDecision] = field(default_factory=list)
    escalated: List[ApplicationCandidate] = field(default_factory=list)
    last_updated: str = field(default_factory=_now_iso)

    def to_payload(self) -> Dict[str, object]:
        return {
            "mode": self.mode,
            "pending": [candidate.to_payload() for candidate in self.pending],
            "decided": [decision.to_payload() for decision in self.decided],
            "escalated": [candidate.to_payload() for candidate in self.escalated],
            "lastUpdated": self.last_updated,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ReviewQueueSnapshot":
        pending_payload = payload.get("pending") or []
        decided_payload = payload.get("decided") or []
        escalated_payload = payload.get("escalated") or []
        snapshot = cls(
            mode=str(payload.get("mode", "review")),
            pending=[ApplicationCandidate.from_payload(item) for item in pending_payload],
            decided=[SubmissionDecision.from_payload(item) for item in decided_payload],
            escalated=[ApplicationCandidate.from_payload(item) for item in escalated_payload],
            last_updated=str(payload.get("lastUpdated", _now_iso())),
        )
        return snapshot

    def find_candidate(self, candidate_id: str) -> Optional[ApplicationCandidate]:
        for candidate in self.pending:
            if candidate.id == candidate_id:
                return candidate
        for candidate in self.escalated:
            if candidate.id == candidate_id:
                return candidate
        return None


class ReviewQueueManager:
    """Manage review queue state transitions and persistence."""

    def __init__(
        self,
        *,
        run_store: RunStore,
        run_record: RunRecord,
        mode: QueueMode = "review",
        telemetry: Callable[[Mapping[str, object]], None] | None = None,
    ) -> None:
        self._run_store = run_store
        self._run_record = run_record
        payload = run_store.load_queue_snapshot(run_record)
        snapshot = ReviewQueueSnapshot.from_payload(payload)
        snapshot.mode = mode or snapshot.mode
        self._snapshot = snapshot
        self._telemetry = telemetry or log_event

    @property
    def snapshot(self) -> ReviewQueueSnapshot:
        return self._snapshot

    def enqueue(self, candidate: ApplicationCandidate) -> ReviewQueueSnapshot:
        existing = self._snapshot.find_candidate(candidate.id)
        if existing:
            existing.update_from(candidate)
        else:
            self._snapshot.pending.append(candidate)
        self._touch(reason="candidate.enqueued")
        return self._persist()

    def update_state(
        self,
        candidate_id: str,
        state: CandidateState,
        *,
        form_plan_path: Optional[str] = None,
    ) -> ReviewQueueSnapshot:
        candidate = self._snapshot.find_candidate(candidate_id)
        if not candidate:
            raise KeyError(candidate_id)
        candidate.state = state
        if form_plan_path:
            candidate.form_plan_path = form_plan_path
        self._touch(reason=f"candidate.state.{state}")
        return self._persist()

    def record_decision(
        self,
        decision: SubmissionDecision,
        *,
        candidate_state: Optional[CandidateState] = None,
    ) -> ReviewQueueSnapshot:
        existing: Optional[SubmissionDecision] = None
        for idx, current in enumerate(self._snapshot.decided):
            if current.decision_id == decision.decision_id:
                existing = current
                self._snapshot.decided[idx] = decision
                break
        if not existing:
            self._snapshot.decided.append(decision)

        candidate = self._snapshot.find_candidate(decision.candidate_id)
        if not candidate:
            raise KeyError(decision.candidate_id)
        candidate.last_decision_id = decision.decision_id
        if candidate_state:
            candidate.state = candidate_state
        elif decision.outcome == "abort":
            candidate.state = "shelved"
        elif decision.outcome == "approve":
            candidate.state = "submitted"
        else:
            candidate.state = "decided"
        self._touch(reason="candidate.decision.recorded")
        return self._persist()

    def escalate(self, candidate_id: str) -> ReviewQueueSnapshot:
        candidate = self._snapshot.find_candidate(candidate_id)
        if not candidate:
            raise KeyError(candidate_id)
        self._snapshot.pending = [c for c in self._snapshot.pending if c.id != candidate_id]
        candidate.state = "awaiting_decision"
        self._snapshot.escalated.append(candidate)
        self._touch(reason="candidate.escalated")
        return self._persist()

    def reload(self) -> ReviewQueueSnapshot:
        payload = self._run_store.load_queue_snapshot(self._run_record)
        self._snapshot = ReviewQueueSnapshot.from_payload(payload)
        return self._snapshot

    def _touch(self, *, reason: str) -> None:
        self._snapshot.last_updated = _now_iso()
        if self._telemetry:
            self._telemetry(
                {
                    "event": "queue.transition",
                    "reason": reason,
                    "pending": len(self._snapshot.pending),
                    "decided": len(self._snapshot.decided),
                    "escalated": len(self._snapshot.escalated),
                    "lastUpdated": self._snapshot.last_updated,
                }
            )

    def _persist(self) -> ReviewQueueSnapshot:
        payload = self._snapshot.to_payload()
        self._run_store.save_queue_snapshot(self._run_record, payload)
        return self._snapshot

