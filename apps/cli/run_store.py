"""Filesystem-backed helpers for provisioning run directories."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config_loader import ensure_runtime_dirs, get_base_dir
from .runtime_state import RunContext, set_run_context


@dataclass(frozen=True)
class RunRecord:
    """Persisted information about a run directory."""

    id: str
    started_at: datetime
    run_dir: Path
    run_json_path: Path
    logs_path: Path
    profile_id: Optional[str]

    def to_json_payload(self) -> dict[str, object]:
        """Return the JSON-serializable payload for the initial run stub."""

        return {
            "id": self.id,
            "startedAt": self.started_at.isoformat().replace("+00:00", "Z"),
            "profileId": self.profile_id,
            "status": "pending",
            "posting": {
                "postingUrl": "demo://placeholder",
                "descriptionText": "",
                "descriptionHtmlPath": "",
            },
            "preview": {"dryRun": True},
            "submission": {},
            "artifactsDir": str(self.run_dir),
            "logsPath": str(self.logs_path),
        }


class RunStore:
    """Create and manage filesystem-backed run directories."""

    def __init__(self, base: Optional[Path] = None) -> None:
        self.base = base or get_base_dir()
        ensure_runtime_dirs(self.base)
        self.runs_dir = self.base / "runs"

    def start_demo_run(self, profile_id: Optional[str] = None) -> RunRecord:
        """Provision a run directory for demo flows and seed run.json."""

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
        )
        run_json = record.to_json_payload()
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
            )
        )
        return record

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

