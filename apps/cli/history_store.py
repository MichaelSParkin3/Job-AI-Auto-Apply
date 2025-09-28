"""Append-only writer for history/history.jsonl with crash-safe semantics."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

import portalocker

from .config_loader import ensure_runtime_dirs, get_base_dir
from .redaction import redact_event
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
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(
            self.history_path, "a", flags=portalocker.LockFlags.EXCLUSIVE
        ) as handle:
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())

