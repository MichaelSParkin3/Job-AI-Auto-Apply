"""Shared CLI utilities such as structured logging and API error helpers."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import portalocker

from .redaction import redact_event
from .runtime_state import get_run_context


def log_event(event: Dict[str, Any]) -> None:
    """Log a structured JSON event to stdout and the active run's actions.log."""

    record: Dict[str, Any] = dict(event)
    record.setdefault("level", "info")
    record.setdefault(
        "timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    context = get_run_context()
    if context:
        record.setdefault("runId", context.id)
    redacted = redact_event(record)
    line = json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    print(line)
    if context:
        _append_actions_log(context.logs_path, line)


@dataclass
class ApiError:
    """Represents a structured error message, aligned with REST API errors."""

    code: str
    message: str
    details: Dict[str, Any] | None = None
    timestamp: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    requestId: str = uuid.uuid4().hex

    def to_json(self) -> str:
        """Serialize the error object to a JSON string, nested under an 'error' key."""

        return json.dumps({"error": asdict(self)}, ensure_ascii=False)


def _append_actions_log(path: Path, line: str) -> None:
    """Append a JSONL line to the actions.log file with crash-safe semantics."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with portalocker.Lock(path, "a", flags=portalocker.LockFlags.EXCLUSIVE) as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())

