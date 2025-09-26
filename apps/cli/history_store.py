"""Append-only writer for history/history.jsonl with crash-safe semantics."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

    def append_demo_entry(self, context: RunContext, summary: str) -> Path:
        """Append a minimal demo history entry aligned with Story 1.4."""

        payload: dict[str, object] = {
            "id": context.id,
            "timestamp": context.started_at.isoformat().replace("+00:00", "Z"),
            "profileId": context.profile_id or "",
            # Demo sessions never submit, so we align with the schema's
            # "skipped" status to satisfy downstream validators.
            "status": "skipped",
            "runPath": str(context.run_dir),
            "postingUrl": "demo://placeholder",
            "fingerprint": context.id,
            "summary": summary,
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

    def _append_jsonl(self, payload: dict[str, object]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(
            self.history_path, "a", flags=portalocker.LockFlags.EXCLUSIVE
        ) as handle:
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())

