"""Filesystem-backed helpers for provisioning run directories."""

from __future__ import annotations

import base64
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from apps.preview.constants import (
    PLACEHOLDER_NOTES,
    PLACEHOLDER_SCREENSHOT_BASE64,
    PLACEHOLDER_SUMMARY,
)

from .config_loader import ensure_runtime_dirs, get_base_dir
from .runtime_state import RunContext, set_run_context


def format_profile_label(profile_id: Optional[str]) -> str:
    """Return a human-friendly label for the given profile identifier."""

    if not profile_id:
        return "Demo profile"
    cleaned = re.split(r"[-_\s]+", profile_id)
    words = [word for word in cleaned if word]
    if not words:
        return "Demo profile"
    titled = " ".join(word.capitalize() for word in words)
    if titled.lower().endswith("profile"):
        return titled
    return f"{titled} profile"


@dataclass(frozen=True)
class RunRecord:
    """Persisted information about a run directory."""

    id: str
    started_at: datetime
    run_dir: Path
    run_json_path: Path
    logs_path: Path
    profile_id: Optional[str]
    screenshot_path: Path | None

    @property
    def queue_path(self) -> Path:
        """Return the filesystem path of the queue snapshot for the run."""

        return self.run_dir / "queue.json"

    def to_json_payload(self) -> dict[str, object]:
        """Return the JSON-serializable payload for the initial run stub."""

        return {
            "id": self.id,
            "startedAt": self.started_at.isoformat().replace("+00:00", "Z"),
            "profileId": self.profile_id,
            "status": "review",
            "posting": {
                "postingUrl": "demo://placeholder",
                "title": "Automation Review Demo",
                "company": "Job AI Auto Apply",
                "location": "Remote",
                "descriptionText": (
                    "This placeholder job description is generated for demo flows. "
                    "No network activity occurs during this run."
                ),
                "descriptionHtmlPath": "",
            },
            "preview": {
                "dryRun": True,
                "approved": False,
                "decision": "pending",
                "summary": PLACEHOLDER_SUMMARY,
                "notes": PLACEHOLDER_NOTES,
                "screenshotPath": str(self.screenshot_path) if self.screenshot_path else "",
            },
            "submission": {},
            "artifactsDir": str(self.run_dir),
            "logsPath": str(self.logs_path),
            "metadata": {
                "mode": "demo",
                "profileLabel": format_profile_label(self.profile_id),
            },
        }


class RunStore:
    """Create and manage filesystem-backed run directories."""

    def __init__(self, base: Optional[Path] = None) -> None:
        self.base = base or get_base_dir()
        ensure_runtime_dirs(self.base)
        self.runs_dir = self.base / "runs"

    def start_demo_run(
        self,
        profile_id: Optional[str] = None,
        *,
        profile_binding: Optional[Dict[str, Any]] = None,
    ) -> RunRecord:
        """Provision a run directory for demo flows and seed run.json."""

        timestamp = datetime.now(timezone.utc)
        slug = secrets.token_hex(4)
        run_id = f"{timestamp:%Y%m%d-%H%M%S}-{slug}"
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        logs_path = run_dir / "actions.log"
        logs_path.touch(exist_ok=True)
        screenshot_path = run_dir / "preview-placeholder.png"
        self._write_placeholder_screenshot(screenshot_path)
        record = RunRecord(
            id=run_id,
            started_at=timestamp,
            run_dir=run_dir,
            run_json_path=run_dir / "run.json",
            logs_path=logs_path,
            profile_id=profile_id,
            screenshot_path=screenshot_path,
        )
        run_json = record.to_json_payload()
        if profile_binding is not None:
            metadata = run_json.setdefault("metadata", {})
            metadata["profileBinding"] = profile_binding
        record.run_json_path.write_text(
            json.dumps(run_json, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        set_run_context(
            RunContext(
                id=record.id,
                started_at=record.started_at,
                run_dir=record.run_dir,
                run_json_path=record.run_json_path,
                logs_path=record.logs_path,
                profile_id=record.profile_id,
                profile_binding=profile_binding,
            )
        )
        return record

    def start_search_readiness_run(
        self,
        *,
        profile_id: Optional[str],
        search_url: str,
        dry_run: bool,
        profile_binding: Optional[Dict[str, Any]] = None,
    ) -> RunRecord:
        """Provision a run directory for search readiness checks."""

        timestamp = datetime.now(timezone.utc)
        slug = secrets.token_hex(4)
        run_id = f"{timestamp:%Y%m%d-%H%M%S}-{slug}"
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        logs_path = run_dir / "actions.log"
        logs_path.touch(exist_ok=True)
        record = RunRecord(
            id=run_id,
            started_at=timestamp,
            run_dir=run_dir,
            run_json_path=run_dir / "run.json",
            logs_path=logs_path,
            profile_id=profile_id,
            screenshot_path=None,
        )
        metadata: Dict[str, Any] = {
            "mode": "cli",
            "profileLabel": format_profile_label(profile_id),
        }
        if profile_binding is not None:
            metadata["profileBinding"] = profile_binding
        run_payload = {
            "id": record.id,
            "startedAt": record.started_at.isoformat().replace("+00:00", "Z"),
            "status": "search_ready_pending",
            "profileId": profile_id,
            "automation": {
                "command": "apply.open",
                "searchUrl": search_url,
                "dryRun": dry_run,
            },
            "preview": {
                "dryRun": dry_run,
                "decision": "pending",
            },
            "readiness": {"status": "pending"},
            "artifactsDir": str(run_dir),
            "logsPath": str(logs_path),
            "metadata": metadata,
        }
        record.run_json_path.write_text(
            json.dumps(run_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        set_run_context(
            RunContext(
                id=record.id,
                started_at=record.started_at,
                run_dir=record.run_dir,
                run_json_path=record.run_json_path,
                logs_path=record.logs_path,
                profile_id=record.profile_id,
                profile_binding=profile_binding,
            )
        )
        return record

    def start_lever_run(
        self,
        *,
        profile_id: str,
        mode: str,
        dry_run: bool,
        source: str,
        plan_payload: Mapping[str, Any],
        profile_binding: Optional[Dict[str, Any]] = None,
    ) -> RunRecord:
        """Create a run directory for Lever apply execution flows."""

        timestamp = datetime.now(timezone.utc)
        slug = secrets.token_hex(4)
        run_id = f"{timestamp:%Y%m%d-%H%M%S}-{slug}"
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        logs_path = run_dir / "actions.log"
        logs_path.touch(exist_ok=True)
        record = RunRecord(
            id=run_id,
            started_at=timestamp,
            run_dir=run_dir,
            run_json_path=run_dir / "run.json",
            logs_path=logs_path,
            profile_id=profile_id,
            screenshot_path=None,
        )
        lever_dir = run_dir / "lever"
        lever_dir.mkdir(parents=True, exist_ok=True)

        queue_snapshot = _empty_queue_snapshot(mode)
        metadata: Dict[str, Any] = {
            "mode": mode,
            "profileLabel": format_profile_label(profile_id),
            "source": source,
        }
        if profile_binding is not None:
            metadata["profileBinding"] = profile_binding

        payload: Dict[str, Any] = {
            "id": record.id,
            "startedAt": record.started_at.isoformat().replace("+00:00", "Z"),
            "profileId": profile_id,
            "mode": mode,
            "status": "pending",
            "preview": {
                "dryRun": dry_run,
                "decision": "pending",
                "approved": False,
            },
            "artifactsDir": str(run_dir),
            "logsPath": str(logs_path),
            "metadata": metadata,
            "lever": {
                "source": source,
                "plan": dict(plan_payload.get("plan", {})),
                "search": plan_payload.get("search"),
                "notes": list(plan_payload.get("notes", [])),
                "candidates": {},
            },
            "queue": queue_snapshot,
        }
        self._write_run_json(record.run_json_path, payload)
        record.queue_path.write_text(
            json.dumps(queue_snapshot, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        set_run_context(
            RunContext(
                id=record.id,
                started_at=record.started_at,
                run_dir=record.run_dir,
                run_json_path=record.run_json_path,
                logs_path=record.logs_path,
                profile_id=record.profile_id,
                profile_binding=profile_binding,
            )
        )
        return record

    def start_lever_plan_discovery(
        self,
        *,
        profile_id: Optional[str],
        source: str,
        plan_payload: Mapping[str, Any],
        guardrails: Sequence[str],
        discovery_mode: str,
        profile_binding: Optional[Dict[str, Any]] = None,
    ) -> RunRecord:
        """Create a run directory for Lever plan discovery flows."""

        timestamp = datetime.now(timezone.utc)
        slug = secrets.token_hex(4)
        run_id = f"{timestamp:%Y%m%d-%H%M%S}-{slug}"
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        plan_dir = run_dir / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        logs_path = run_dir / "actions.log"
        logs_path.touch(exist_ok=True)
        record = RunRecord(
            id=run_id,
            started_at=timestamp,
            run_dir=run_dir,
            run_json_path=run_dir / "run.json",
            logs_path=logs_path,
            profile_id=profile_id,
            screenshot_path=None,
        )
        plan_map = plan_payload.get("plan") if isinstance(plan_payload.get("plan"), Mapping) else {}
        plan_urls: Sequence[str] = []
        plan_pages = None
        if isinstance(plan_map, Mapping):
            urls_value = plan_map.get("urls")
            if isinstance(urls_value, Sequence):
                plan_urls = [str(url) for url in urls_value]
            pages_value = plan_map.get("pages")
            if isinstance(pages_value, (int, float)):
                plan_pages = int(pages_value)
        metadata: Dict[str, Any] = {
            "mode": "plan",
            "profileLabel": format_profile_label(profile_id),
            "source": source,
            "discoveryMode": discovery_mode,
        }
        if profile_binding is not None:
            metadata["profileBinding"] = profile_binding
        plan_section: Dict[str, Any] = {
            "source": source,
            "search": plan_payload.get("search"),
            "guardrails": list(guardrails),
            "mode": discovery_mode,
            "urls": list(plan_urls),
            "artifacts": [],
            "results": [],
        }
        if plan_pages is not None:
            plan_section["pages"] = plan_pages
        if plan_payload.get("notes"):
            plan_section["notes"] = list(plan_payload.get("notes", []))
        if plan_payload.get("profile"):
            plan_section["profile"] = plan_payload.get("profile")
        payload: Dict[str, Any] = {
            "id": record.id,
            "startedAt": record.started_at.isoformat().replace("+00:00", "Z"),
            "status": "plan_pending",
            "profileId": profile_id,
            "artifactsDir": str(run_dir),
            "logsPath": str(logs_path),
            "metadata": metadata,
            "plan": plan_section,
        }
        self._write_run_json(record.run_json_path, payload)
        set_run_context(
            RunContext(
                id=record.id,
                started_at=record.started_at,
                run_dir=record.run_dir,
                run_json_path=record.run_json_path,
                logs_path=record.logs_path,
                profile_id=record.profile_id,
                profile_binding=profile_binding,
            )
        )
        return record

    # region Demo mutation helpers

    def bootstrap_demo_preview(
        self,
        record: RunRecord,
        *,
        limit: int,
        profile_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Populate the run.json preview payload with canned demo metadata."""

        data = self._load_run_json(record.run_json_path)
        data["status"] = "review"
        if profile_id:
            data["profileId"] = profile_id
        preview = data.setdefault("preview", {})
        preview.update(
            {
                "dryRun": True,
                "approved": False,
                "decision": preview.get("decision", "pending") or "pending",
                "summary": preview.get("summary") or PLACEHOLDER_SUMMARY,
                "notes": preview.get("notes") or PLACEHOLDER_NOTES,
                "screenshotPath": str(record.screenshot_path),
            }
        )
        metadata = data.setdefault("metadata", {})
        metadata.update(
            {
                "limit": limit,
                "mode": "demo",
                "profileLabel": metadata.get("profileLabel")
                or format_profile_label(data.get("profileId")),
            }
        )
        self._write_run_json(record.run_json_path, data)
        return data

    def record_demo_edit(self, record: RunRecord, text: str) -> Dict[str, Any]:
        """Persist a requested edit for the demo preview."""

        data = self._load_run_json(record.run_json_path)
        preview = data.setdefault("preview", {})
        preview["edits"] = text
        preview["lastEditAt"] = _now_iso()
        preview["decision"] = "editing"
        data["status"] = "review"
        self._write_run_json(record.run_json_path, data)
        return data

    def record_demo_decision(
        self, record: RunRecord, decision: str
    ) -> Dict[str, Any]:
        """Persist an approve/abort decision for the demo preview."""

        data = self._load_run_json(record.run_json_path)
        preview = data.setdefault("preview", {})
        preview["decision"] = decision
        preview["decidedAt"] = _now_iso()
        preview["approved"] = decision == "approved"
        data["status"] = "approved" if decision == "approved" else "aborted"
        self._write_run_json(record.run_json_path, data)
        return data

    def record_search_readiness(
        self, record: RunRecord, readiness_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Persist readiness results for the given run."""

        data = self._load_run_json(record.run_json_path)
        data["readiness"] = readiness_payload
        status = readiness_payload.get("status")
        if status == "ready":
            data["status"] = "search_ready"
        elif status == "unready":
            data["status"] = "search_unready"
        else:
            data["status"] = "search_ready_pending"
        self._write_run_json(record.run_json_path, data)
        return data

    def record_session_backup(
        self,
        record: RunRecord,
        *,
        enabled: bool,
        retention: int,
        last_backup: Dict[str, Any] | None = None,
        restore: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Persist session backup metadata for the run."""

        data = self._load_run_json(record.run_json_path)
        session_backup = data.setdefault("sessionBackup", {})
        session_backup["enabled"] = enabled
        session_backup["retention"] = retention
        if restore is not None:
            session_backup["restore"] = restore
        if last_backup is not None:
            session_backup["lastBackup"] = last_backup
        self._write_run_json(record.run_json_path, data)
        return data

    def record_quick_apply_discovery(
        self, record: RunRecord, discovery_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Persist Quick Apply discovery results for the given run."""

        data = self._load_run_json(record.run_json_path)
        data["discovery"] = discovery_payload
        data["status"] = "quick_apply_discovery"
        self._write_run_json(record.run_json_path, data)
        return data

    def record_plan_discovery(
        self, record: RunRecord, discovery_payload: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Persist plan discovery metadata and results for the given run."""

        data = self._load_run_json(record.run_json_path)
        plan_section = data.setdefault("plan", {})
        if discovery_payload.get("guardrails") is not None:
            plan_section["guardrails"] = list(discovery_payload.get("guardrails", []))
        if discovery_payload.get("artifacts") is not None:
            plan_section["artifacts"] = list(discovery_payload.get("artifacts", []))
        if discovery_payload.get("results") is not None:
            plan_section["results"] = list(discovery_payload.get("results", []))
        if discovery_payload.get("mode"):
            plan_section["mode"] = discovery_payload["mode"]
        if discovery_payload.get("summary"):
            plan_section["summary"] = discovery_payload["summary"]
        data["plan"] = plan_section
        if discovery_payload.get("metadata"):
            metadata = data.setdefault("metadata", {})
            metadata.update(discovery_payload["metadata"])
        data["status"] = discovery_payload.get("status", "plan_completed")
        self._write_run_json(record.run_json_path, data)
        return plan_section

    def record_form_plan(
        self, record: RunRecord, form_plan_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Persist the form fill plan alongside discovery metadata."""

        data = self._load_run_json(record.run_json_path)
        data["formPlan"] = form_plan_payload
        self._write_run_json(record.run_json_path, data)
        return data

    def record_form_fill(
        self, record: RunRecord, form_fill_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Persist the form fill summary to run.json."""

        data = self._load_run_json(record.run_json_path)
        data["formFill"] = form_fill_payload
        self._write_run_json(record.run_json_path, data)
        return data

    def record_resume_upload(
        self, record: RunRecord, resume_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Persist the resume upload result to run.json."""

        data = self._load_run_json(record.run_json_path)
        data["resumeUpload"] = resume_payload
        self._write_run_json(record.run_json_path, data)
        return data

    def record_preview_summary(
        self,
        record: RunRecord,
        *,
        summary: Mapping[str, Any],
        screenshot: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Persist the submission preview summary and screenshot metadata."""

        data = self._load_run_json(record.run_json_path)
        preview = data.setdefault("preview", {})
        preview["summary"] = dict(summary)
        screenshot_payload = dict(screenshot)
        if "path" in screenshot_payload:
            preview["screenshotPath"] = str(screenshot_payload["path"])
        preview["screenshot"] = screenshot_payload
        data["status"] = "review"
        self._write_run_json(record.run_json_path, data)
        return data

    def load_run_payload(self, record: RunRecord) -> Dict[str, Any]:
        """Return the current run.json payload for the given record."""

        return self._load_run_json(record.run_json_path)

    def load_queue_snapshot(self, record: RunRecord) -> Dict[str, Any]:
        """Load the queue snapshot for the given run."""

        payload = self._load_run_json(record.run_json_path)
        mode = (
            payload.get("metadata", {}).get("mode")
            or payload.get("mode")
            or "review"
        )
        if record.queue_path.exists():
            queue_payload = json.loads(record.queue_path.read_text(encoding="utf-8"))
            if "mode" not in queue_payload:
                queue_payload["mode"] = mode
            payload["queue"] = queue_payload
            self._write_run_json(record.run_json_path, payload)
            return queue_payload
        queue = payload.get("queue") or _empty_queue_snapshot(mode)
        queue.setdefault("mode", mode)
        payload["queue"] = queue
        self._write_run_json(record.run_json_path, payload)
        record.queue_path.write_text(
            json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return queue

    def save_queue_snapshot(
        self, record: RunRecord, snapshot: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Persist the provided queue snapshot to queue.json and run.json."""

        payload = self._load_run_json(record.run_json_path)
        payload["queue"] = dict(snapshot)
        self._write_run_json(record.run_json_path, payload)
        record.queue_path.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return payload["queue"]

    def record_submission_decision(
        self, record: RunRecord, decision: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Append or update a submission decision for the given run."""

        payload = self._load_run_json(record.run_json_path)
        decisions = payload.setdefault("decisions", [])
        decision_payload = json.loads(json.dumps(decision, ensure_ascii=False))
        for index, existing in enumerate(decisions):
            if existing.get("decisionId") == decision_payload.get("decisionId"):
                decisions[index] = decision_payload
                break
        else:
            decisions.append(decision_payload)
        self._write_run_json(record.run_json_path, payload)
        return decision_payload

    def upsert_lever_candidate(
        self, record: RunRecord, candidate_id: str, payload: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Insert or update a Lever candidate payload inside run.json."""

        data = self._load_run_json(record.run_json_path)
        lever_section = data.setdefault("lever", {})
        candidates = lever_section.setdefault("candidates", {})
        candidates[candidate_id] = json.loads(
            json.dumps(payload, ensure_ascii=False)
        )
        self._write_run_json(record.run_json_path, data)
        return candidates[candidate_id]

    def plan_retention(self) -> None:
        """Placeholder for future retention planning logic."""

        from .utils import log_event

        log_event(
            {
                "level": "info",
                "event": "runs.retention.todo",
                "message": "Run retention planning not yet implemented.",
            }
        )

    # endregion

    def _write_placeholder_screenshot(self, path: Path) -> None:
        """Write a minimal placeholder PNG for demo preview runs."""

        if path.exists():
            return
        raw = base64.b64decode(PLACEHOLDER_SCREENSHOT_BASE64)
        path.write_bytes(raw)

    def _load_run_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_run_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _empty_queue_snapshot(mode: str) -> Dict[str, Any]:
    """Return an empty queue snapshot conforming to the data model."""

    return {
        "mode": mode,
        "pending": [],
        "decided": [],
        "escalated": [],
        "lastUpdated": _now_iso(),
    }

