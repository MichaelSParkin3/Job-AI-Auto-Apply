"""Filesystem-backed helpers for provisioning run directories."""

from __future__ import annotations

import base64
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
    screenshot_path: Path

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
                "screenshotPath": str(self.screenshot_path),
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

    def load_run_payload(self, record: RunRecord) -> Dict[str, Any]:
        """Return the current run.json payload for the given record."""

        return self._load_run_json(record.run_json_path)

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

