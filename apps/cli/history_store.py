"""Append-only writer for history/history.jsonl with crash-safe semantics."""

from __future__ import annotations

import json
import os
import shutil
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

try:  # pragma: no cover - exercised when portalocker is unavailable
    import portalocker
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard

    class _PortalockerLock:
        def __init__(self, path: Path | str, mode: str, *, flags: object | None = None):
            self._path = Path(path)
            self._mode = mode
            self._handle = None

        def __enter__(self):
            self._handle = open(self._path, self._mode)
            return self._handle

        def __exit__(self, exc_type, exc, tb) -> None:
            if self._handle:
                self._handle.close()

    portalocker = types.SimpleNamespace(  # type: ignore[assignment]
        Lock=lambda path, mode, **kwargs: _PortalockerLock(path, mode, **kwargs),
        LockFlags=types.SimpleNamespace(EXCLUSIVE=1),
    )

from .config_loader import ensure_runtime_dirs, get_base_dir
from .redaction import prepare_rationale_audit_fields, redact_event
from .runtime_state import RunContext
from .utils import log_event


class HistoryWriter:
    """Append history entries with Windows-friendly file locking."""

    def __init__(self, base: Optional[Path] = None) -> None:
        self.base = base or get_base_dir()
        ensure_runtime_dirs(self.base)
        self.history_path = self.base / "history" / "history.jsonl"

    def append_entry(self, entry: dict[str, object]) -> Path:
        """Append an arbitrary history entry to the JSONL file."""

        payload = dict(entry)
        payload.setdefault(
            "timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        redacted = redact_event(payload)
        self._append_jsonl(redacted)
        return self.history_path

    def append_decision_summary(
        self,
        context: RunContext,
        *,
        run_payload: Mapping[str, object],
        queue_payload: Mapping[str, object],
        decision_payload: Mapping[str, object],
    ) -> Path:
        """Append an audit entry summarising a queue decision."""

        posting = run_payload.get("posting") or {}
        posting_url = str(posting.get("postingUrl") or "")
        profile_id = (
            str(run_payload.get("profileId"))
            if run_payload.get("profileId")
            else (context.profile_id or "")
        )
        decision_ref = _compact_decision_reference(decision_payload)
        decisions_list = run_payload.get("decisions") or []
        summary = _summarise_decisions(decisions_list)
        queue_depth = _queue_depth_metrics(queue_payload)
        entry = {
            "id": run_payload.get("id") or context.id,
            "timestamp": decision_payload.get("timestamp")
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "profileId": profile_id,
            "postingUrl": posting_url,
            "jobTitle": posting.get("title"),
            "company": posting.get("company"),
            "location": posting.get("location"),
            "fingerprint": f"{context.id}:decision:{decision_ref.get('id') or 'unknown'}",
            "mode": _resolve_mode(run_payload),
            "status": _status_from_outcome(decision_payload.get("outcome")),
            "runPath": str(context.run_dir),
            "queuePath": str(context.run_dir / "queue.json"),
            "decisions": summary,
            "queueDepth": queue_depth,
            "decision": decision_ref,
        }
        return self.append_entry(entry)

    def append_demo_entry(
        self,
        context: RunContext,
        *,
        summary: str,
        decision: str,
        edits: Optional[str] = None,
        dry_run: bool = True,
    ) -> Path:
        """Append a demo-friendly history entry capturing preview outcomes."""

        payload: dict[str, object] = {
            "id": context.id,
            "timestamp": context.started_at.isoformat().replace("+00:00", "Z"),
            "profileId": context.profile_id or "",
            "status": "skipped",
            "runPath": str(context.run_dir),
            "postingUrl": "demo://placeholder",
            "fingerprint": context.id,
            "summary": summary,
            "decision": decision,
            "dryRun": dry_run,
        }
        if edits:
            payload["notes"] = edits
        return self.append_entry(payload)

    def append_form_plan(
        self,
        context: RunContext,
        *,
        profile_id: Optional[str],
        search_url: str,
        summary: Mapping[str, object],
        dry_run: bool,
    ) -> Path:
        """Append a history record summarising form mapping outcomes."""

        payload: dict[str, object] = {
            "id": context.id,
            "profileId": (profile_id or ""),
            "postingUrl": "simplyhired://quick-apply-form-plan",
            "searchUrl": search_url,
            "fingerprint": f"{context.id}:form-plan",
            "status": "skipped",
            "source": "simplyhired",
            "runPath": str(context.run_dir),
            "dryRun": dry_run,
            "summary": dict(summary),
        }
        return self.append_entry(payload)

    def plan_retention(self) -> None:
        """Placeholder retention planner logging a TODO event."""

        log_event(
            {
                "level": "info",
                "event": "history.retention.todo",
                "message": "History retention planning not yet implemented.",
            }
        )

    def append_form_fill(
        self,
        context: RunContext,
        *,
        profile_id: Optional[str],
        search_url: str,
        summary: Mapping[str, object],
        dry_run: bool,
    ) -> Path:
        """Append a history record for form filling outcomes."""

        payload: dict[str, object] = {
            "id": context.id,
            "profileId": profile_id or "",
            "postingUrl": "simplyhired://quick-apply-form-fill",
            "searchUrl": search_url,
            "fingerprint": f"{context.id}:form-fill",
            "status": "skipped",
            "source": "simplyhired",
            "runPath": str(context.run_dir),
            "dryRun": dry_run,
            "summary": dict(summary),
        }
        return self.append_entry(payload)

    def append_resume_upload(
        self,
        context: RunContext,
        *,
        profile_id: Optional[str],
        search_url: str,
        summary: Mapping[str, object],
        dry_run: bool,
    ) -> Path:
        """Append a resume upload history record."""

        summary_dict = dict(summary)
        payload: dict[str, object] = {
            "id": context.id,
            "profileId": profile_id or "",
            "postingUrl": "simplyhired://resume-upload",
            "searchUrl": search_url,
            "fingerprint": f"{context.id}:resume-upload",
            "status": "skipped",
            "source": "simplyhired",
            "runPath": str(context.run_dir),
            "dryRun": dry_run,
            "summary": {
                "status": summary_dict.get("status"),
                "attempts": summary_dict.get("attempts"),
                "simulated": summary_dict.get("simulated"),
            },
        }
        file_info = summary_dict.get("file")
        if isinstance(file_info, Mapping):
            payload["summary"]["file"] = {
                "name": file_info.get("name"),
                "sha256": file_info.get("sha256"),
                "sizeBytes": file_info.get("sizeBytes"),
            }
        if summary_dict.get("artifact"):
            payload["summary"]["artifact"] = summary_dict.get("artifact")
        return self.append_entry(payload)

    def append_preview_summary(
        self,
        context: RunContext,
        *,
        profile_id: Optional[str],
        search_url: str,
        summary: Mapping[str, object],
        screenshot: Mapping[str, object],
        dry_run: bool,
    ) -> Path:
        """Append a redacted preview summary entry to history."""

        summary_dict = dict(summary)
        headline = dict(summary_dict.get("headline") or {})
        form = dict(summary_dict.get("form") or {})
        payload: dict[str, object] = {
            "id": context.id,
            "profileId": profile_id or "",
            "postingUrl": headline.get("postingUrl") or search_url,
            "searchUrl": search_url,
            "fingerprint": f"{context.id}:summary",
            "status": "skipped",
            "source": "simplyhired",
            "runPath": str(context.run_dir),
            "dryRun": dry_run,
            "summary": {
                "title": headline.get("title"),
                "company": headline.get("company"),
                "location": headline.get("location"),
                "filled": form.get("filledFields"),
                "skipped": form.get("skippedFields"),
                "issues": form.get("issues"),
            },
        }
        screenshot_payload = dict(screenshot)
        if screenshot_payload.get("path"):
            payload["screenshots"] = [screenshot_payload["path"]]
        return self.append_entry(payload)

    def _append_jsonl(self, payload: dict[str, object]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False)
        history_dir = self.history_path.parent
        history_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.history_path.with_suffix(self.history_path.suffix + ".lock")
        temp_path = history_dir / f"{self.history_path.name}.tmp"
        with portalocker.Lock(lock_path, "a", flags=portalocker.LockFlags.EXCLUSIVE):
            try:
                with open(temp_path, "w", encoding="utf-8") as tmp:
                    if self.history_path.exists():
                        with open(self.history_path, "r", encoding="utf-8") as current:
                            shutil.copyfileobj(current, tmp)
                    tmp.write(serialized + "\n")
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(temp_path, self.history_path)
            except Exception:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
                raise


def _compact_decision_reference(decision: Mapping[str, object]) -> dict[str, object]:
    """Return a redacted decision reference suitable for history logging."""

    audit = prepare_rationale_audit_fields(
        decision.get("rationalePreview") or decision.get("rationale") or None
    )
    payload = {
        "id": decision.get("decisionId"),
        "candidateId": decision.get("candidateId"),
        "outcome": decision.get("outcome"),
        "mode": decision.get("mode"),
        "confidence": decision.get("confidence"),
        "timestamp": decision.get("timestamp"),
        "artifactPath": decision.get("artifactPath"),
        "rationaleHash": decision.get("rationaleHash") or audit["rationaleHash"],
        "rationaleRedacted": decision.get("rationaleRedacted", audit["rationaleRedacted"]),
        "rationaleTruncated": decision.get(
            "rationaleTruncated", audit["rationaleTruncated"]
        ),
        "rationaleLength": decision.get("rationaleLength", audit["rationaleLength"]),
    }
    preview = decision.get("rationalePreview") or audit["rationalePreview"]
    if preview:
        payload["rationalePreview"] = preview
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _summarise_decisions(decisions: Sequence[object]) -> dict[str, object]:
    """Aggregate decision outcomes for history analytics."""

    totals: dict[str, int] = {}
    latest: dict[str, str] = {}
    by_mode: dict[str, int] = {}
    last_timestamp: str | None = None
    for item in decisions:
        if not isinstance(item, Mapping):
            continue
        outcome = str(item.get("outcome")) if item.get("outcome") else "unknown"
        totals[outcome] = totals.get(outcome, 0) + 1
        timestamp = item.get("timestamp")
        if isinstance(timestamp, str):
            current_latest = latest.get(outcome)
            if current_latest is None or timestamp > current_latest:
                latest[outcome] = timestamp
            if last_timestamp is None or timestamp > last_timestamp:
                last_timestamp = timestamp
        mode = item.get("mode")
        if isinstance(mode, str):
            by_mode[mode] = by_mode.get(mode, 0) + 1
    return {
        "total": sum(totals.values()),
        "byOutcome": totals,
        "latest": latest,
        "byMode": by_mode,
        "lastDecisionAt": last_timestamp,
    }


def _queue_depth_metrics(queue_payload: Mapping[str, object]) -> dict[str, object]:
    """Return queue depth counters from a queue snapshot payload."""

    pending = queue_payload.get("pending") or []
    decided = queue_payload.get("decided") or []
    escalated = queue_payload.get("escalated") or []
    last_updated = queue_payload.get("lastUpdated")
    return {
        "pending": len(pending) if isinstance(pending, Sequence) else 0,
        "decided": len(decided) if isinstance(decided, Sequence) else 0,
        "escalated": len(escalated) if isinstance(escalated, Sequence) else 0,
        "lastUpdated": last_updated,
    }


def _resolve_mode(run_payload: Mapping[str, object]) -> str:
    """Derive the run mode from run.json payload fallbacks."""

    mode = run_payload.get("mode")
    if isinstance(mode, str) and mode:
        return mode
    metadata = run_payload.get("metadata")
    if isinstance(metadata, Mapping):
        meta_mode = metadata.get("mode")
        if isinstance(meta_mode, str) and meta_mode:
            return meta_mode
    return "review"


def _status_from_outcome(outcome: object) -> str:
    """Map decision outcomes to existing HistoryEntry status enums."""

    if outcome == "approve":
        return "submitted"
    if outcome == "abort":
        return "aborted"
    return "auto_review_pending"

