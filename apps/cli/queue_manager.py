"""Domain models and persistence helpers for the review queue."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Mapping, Optional

from .run_store import RunRecord, RunStore
from .redaction import prepare_rationale_audit_fields
from .utils import log_event

CandidateState = str
QueueMode = str
DecisionOutcome = str
DecisionMode = str
CandidateAssignment = str


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_iso8601(value: str) -> datetime:
    """Parse a subset of ISO-8601 strings ending with `Z` for UTC."""

    cleaned = value.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned)


@dataclass
class ApplicationCandidate:
    """Canonical representation of a candidate awaiting review."""

    id: str
    posting: Mapping[str, object]
    form_plan_path: Optional[str]
    discovered_at: str
    state: CandidateState = "discovered"
    last_decision_id: Optional[str] = None
    assigned_mode: CandidateAssignment = "human"
    updated_at: str = field(default_factory=_now_iso)

    def to_payload(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "id": self.id,
            "posting": dict(self.posting),
            "discoveredAt": self.discovered_at,
            "state": self.state,
            "assignedMode": self.assigned_mode,
            "updatedAt": self.updated_at,
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
            assigned_mode=str(payload.get("assignedMode", "human")),
            updated_at=str(payload.get("updatedAt", _now_iso())),
        )

    def update_from(self, other: "ApplicationCandidate") -> None:
        self.posting = dict(other.posting)
        self.form_plan_path = other.form_plan_path or self.form_plan_path
        self.discovered_at = other.discovered_at
        self.state = other.state
        if other.last_decision_id:
            self.last_decision_id = other.last_decision_id
        self.assigned_mode = other.assigned_mode or self.assigned_mode
        self.updated_at = other.updated_at or self.updated_at


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
    rationale_hash: Optional[str] = None
    rationale_redacted: Optional[bool] = None
    rationale_length: Optional[int] = None
    rationale_truncated: Optional[bool] = None

    def to_payload(self) -> Dict[str, object]:
        metadata = self._ensure_rationale_metadata()
        payload: Dict[str, object] = {
            "decisionId": self.decision_id,
            "candidateId": self.candidate_id,
            "outcome": self.outcome,
            "mode": self.mode,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }
        if self.requested_changes is not None:
            payload["requestedChanges"] = [dict(item) for item in self.requested_changes]
        if metadata["rationaleHash"]:
            payload["rationaleHash"] = metadata["rationaleHash"]
            payload["rationaleRedacted"] = metadata["rationaleRedacted"]
            payload["rationaleLength"] = metadata["rationaleLength"]
            payload["rationaleTruncated"] = metadata["rationaleTruncated"]
        if metadata["rationalePreview"]:
            payload["rationalePreview"] = metadata["rationalePreview"]
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SubmissionDecision":
        requested = payload.get("requestedChanges")
        rationale_value = payload.get("rationalePreview") or payload.get("rationale") or ""
        return cls(
            decision_id=str(payload.get("decisionId")),
            candidate_id=str(payload.get("candidateId")),
            outcome=str(payload.get("outcome")),
            mode=str(payload.get("mode")),
            confidence=float(payload.get("confidence", 0.0)),
            rationale=str(rationale_value),
            timestamp=str(payload.get("timestamp")),
            requested_changes=list(requested) if isinstance(requested, Iterable) else None,
            rationale_hash=(
                str(payload.get("rationaleHash")) if payload.get("rationaleHash") else None
            ),
            rationale_redacted=bool(payload.get("rationaleRedacted", False)),
            rationale_length=(
                int(payload.get("rationaleLength"))
                if payload.get("rationaleLength") is not None
                else None
            ),
            rationale_truncated=bool(payload.get("rationaleTruncated", False)),
        )

    def _ensure_rationale_metadata(self) -> Dict[str, object]:
        """Compute and cache hashed rationale metadata for persistence."""

        if self.rationale_hash and self.rationale_length is not None:
            return {
                "rationaleHash": self.rationale_hash,
                "rationalePreview": self.rationale or None,
                "rationaleRedacted": bool(self.rationale_redacted),
                "rationaleTruncated": bool(self.rationale_truncated),
                "rationaleLength": self.rationale_length,
            }

        audit = prepare_rationale_audit_fields(self.rationale or "")
        self.rationale_hash = audit["rationaleHash"]
        self.rationale_redacted = audit["rationaleRedacted"]
        self.rationale_length = audit["rationaleLength"]
        self.rationale_truncated = audit["rationaleTruncated"]
        preview = audit["rationalePreview"]
        if preview is not None:
            self.rationale = preview
        elif self.rationale:
            self.rationale = ""
        return audit


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
            target = existing
        else:
            self._snapshot.pending.append(candidate)
            target = candidate
        timestamp = self._touch(reason="candidate.enqueued")
        target.updated_at = timestamp
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
        timestamp = self._touch(reason=f"candidate.state.{state}")
        candidate.updated_at = timestamp
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
        timestamp = self._touch(reason="candidate.decision.recorded")
        candidate.updated_at = timestamp
        return self._persist()

    def escalate(self, candidate_id: str) -> ReviewQueueSnapshot:
        return self.assign_mode(
            candidate_id,
            "human",
            trigger="manual_escalate",
            reason="escalate",
        )

    def reload(self) -> ReviewQueueSnapshot:
        payload = self._run_store.load_queue_snapshot(self._run_record)
        self._snapshot = ReviewQueueSnapshot.from_payload(payload)
        return self._snapshot

    def assign_mode(
        self,
        candidate_id: str,
        assigned_mode: CandidateAssignment,
        *,
        trigger: str = "manual_override",
        reason: Optional[str] = None,
    ) -> ReviewQueueSnapshot:
        assigned_mode = assigned_mode.lower()
        if assigned_mode not in {"human", "ai"}:
            raise ValueError(assigned_mode)

        existing = self._snapshot.find_candidate(candidate_id)
        if not existing:
            raise KeyError(candidate_id)
        if existing.assigned_mode == assigned_mode:
            return self._snapshot

        candidate, source = self._pop_candidate(candidate_id)
        candidate.state = "awaiting_decision"
        destination: List[ApplicationCandidate]
        if assigned_mode == "human":
            destination = self._snapshot.escalated
            telemetry_event = "AUTO_OVERRIDE" if trigger != "watchdog" else "AUTO_FAILSAFE_TRIGGERED"
        else:
            destination = self._snapshot.pending
            telemetry_event = "queue.transition"
        candidate.assigned_mode = assigned_mode
        timestamp = self._touch(
            reason=f"candidate.mode.{assigned_mode}",
            telemetry_event=telemetry_event,
            telemetry_extra={
                "candidateId": candidate.id,
                "trigger": trigger,
                "assignedMode": assigned_mode,
                "source": source,
                "reason": reason or "",
            },
        )
        candidate.updated_at = timestamp
        if assigned_mode == "ai":
            if candidate not in destination:
                destination.append(candidate)
            # remove duplicates from escalated when returning to AI mode
            self._snapshot.escalated = [c for c in self._snapshot.escalated if c.id != candidate.id]
        else:
            if candidate not in destination:
                destination.append(candidate)
            self._snapshot.pending = [c for c in self._snapshot.pending if c.id != candidate.id]
        return self._persist()

    def enforce_watchdog(
        self,
        timeout_seconds: int,
        *,
        now: Optional[datetime] = None,
    ) -> List[str]:
        """Reassign stalled AI candidates back to the human lane."""

        if timeout_seconds <= 0:
            return []
        threshold = timedelta(seconds=timeout_seconds)
        current_time = now or datetime.now(timezone.utc)
        reassigned: List[str] = []
        for candidate in list(self._snapshot.pending):
            if candidate.assigned_mode != "ai":
                continue
            try:
                updated_at = _parse_iso8601(candidate.updated_at)
            except ValueError:
                updated_at = current_time - threshold
            if current_time - updated_at >= threshold:
                self.assign_mode(
                    candidate.id,
                    "human",
                    trigger="watchdog",
                    reason="timeout",
                )
                reassigned.append(candidate.id)
        return reassigned

    def _touch(
        self,
        *,
        reason: str,
        telemetry_event: Optional[str] = None,
        telemetry_extra: Optional[Mapping[str, object]] = None,
    ) -> str:
        timestamp = _now_iso()
        self._snapshot.last_updated = timestamp
        if self._telemetry:
            payload: Dict[str, object] = {
                "event": telemetry_event or "queue.transition",
                "reason": reason,
                "pending": len(self._snapshot.pending),
                "decided": len(self._snapshot.decided),
                "escalated": len(self._snapshot.escalated),
                "lastUpdated": timestamp,
            }
            if telemetry_extra:
                payload.update(telemetry_extra)
            self._telemetry(payload)
        return timestamp

    def _persist(self) -> ReviewQueueSnapshot:
        payload = self._snapshot.to_payload()
        self._run_store.save_queue_snapshot(self._run_record, payload)
        return self._snapshot

    def _pop_candidate(
        self, candidate_id: str
    ) -> tuple[ApplicationCandidate, str]:
        for collection_name in ("pending", "escalated"):
            collection = getattr(self._snapshot, collection_name)
            for index, candidate in enumerate(collection):
                if candidate.id == candidate_id:
                    del collection[index]
                    return candidate, collection_name
        raise KeyError(candidate_id)

