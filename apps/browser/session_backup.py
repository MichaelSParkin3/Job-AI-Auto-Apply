"""Session backup management utilities for Browser-Use profiles."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Files/directories that are safe to skip in backups to avoid permission errors
BACKUP_IGNORE_PATTERNS = (
    "metadata.json",
    # Chrome caches (often locked while browser runs)
    "Cache_Data*",
    "Code Cache*",
    "DawnCache*",
    "GPUCache*",
    "ShaderCache*",
    "GrShaderCache*",
    "Service Worker*",
    "VideoDecodeStats*",
    # Locks
    "lockfile",
    "SingletonLock",
)

from apps.cli.utils import log_event


@dataclass(frozen=True)
class BackupSummary:
    """Represents the outcome of a backup or restore operation."""

    status: str
    profile_id: str
    path: Optional[Path]
    created_at: Optional[str]
    bytes: Optional[int]
    run_id: Optional[str]
    rotation: Dict[str, List[str]] | None = None
    reason: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": self.status,
            "profileId": self.profile_id,
        }
        if self.path is not None:
            payload["path"] = str(self.path)
        if self.created_at is not None:
            payload["createdAt"] = self.created_at
        if self.bytes is not None:
            payload["bytes"] = self.bytes
        if self.rotation is not None:
            payload["rotation"] = {
                "kept": [str(value) for value in self.rotation.get("kept", [])],
                "removed": [str(value) for value in self.rotation.get("removed", [])],
            }
        if self.run_id is not None:
            payload["runId"] = self.run_id
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


class SessionBackupManager:
    """Create, rotate, and restore Browser-Use session backups."""

    def __init__(
        self,
        base: Path,
        *,
        enabled: bool = True,
        retention: int = 2,
        event_logger: Callable[[Dict[str, Any]], None] = log_event,
    ) -> None:
        self.base = base
        self.enabled = enabled
        self.retention = max(1, int(retention))
        self._event_logger = event_logger
        self.backups_root = self.base / ".local" / "browser" / "backups"
        self.backups_root.mkdir(parents=True, exist_ok=True)

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create_backup(
        self,
        profile_id: str,
        session_dir: Path,
        *,
        run_id: str | None = None,
    ) -> BackupSummary:
        """Snapshot the provided session directory."""

        if not self.enabled:
            summary = BackupSummary(
                status="skipped",
                profile_id=profile_id,
                path=None,
                created_at=None,
                bytes=None,
                run_id=run_id,
                reason="disabled",
            )
            self._event_logger(
                {
                    "event": "SESSION_BACKUP_SKIPPED",
                    "profileId": profile_id,
                    "reason": "disabled",
                    "runId": run_id,
                }
            )
            return summary

        profile_root = self.backups_root / profile_id
        profile_root.mkdir(parents=True, exist_ok=True)

        if not session_dir.exists():
            summary = BackupSummary(
                status="skipped",
                profile_id=profile_id,
                path=None,
                created_at=None,
                bytes=None,
                run_id=run_id,
                reason="missing_session",
            )
            self._event_logger(
                {
                    "level": "warning",
                    "event": "SESSION_BACKUP_SKIPPED",
                    "profileId": profile_id,
                    "reason": "missing_session",
                    "runId": run_id,
                }
            )
            return summary

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        final_dir = profile_root / f"{timestamp}-{uuid.uuid4().hex[:6]}"
        temp_dir = Path(
            tempfile.mkdtemp(prefix=".tmp-backup-", dir=str(profile_root))
        )

        start_time = time.monotonic()
        try:
            shutil.copytree(
                session_dir,
                temp_dir,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*BACKUP_IGNORE_PATTERNS),
            )
            size_bytes = _directory_size(temp_dir)
            metadata = {
                "profileId": profile_id,
                "createdAt": _iso_now(),
                "bytes": size_bytes,
                "runId": run_id,
                "source": str(session_dir),
            }
            (temp_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_dir.replace(final_dir)
        except Exception as exc:  # pragma: no cover - defensive path
            self._event_logger(
                {
                    "level": "error",
                    "event": "SESSION_BACKUP_FAILED",
                    "profileId": profile_id,
                    "runId": run_id,
                    "error": str(exc),
                }
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return BackupSummary(
                status="failed",
                profile_id=profile_id,
                path=None,
                created_at=None,
                bytes=None,
                run_id=run_id,
                reason=str(exc),
            )

        elapsed = round(time.monotonic() - start_time, 3)
        rotation = self._enforce_retention(profile_root)

        metadata_payload = self._load_metadata(final_dir)
        created_at = metadata_payload.get("createdAt")
        size_bytes = metadata_payload.get("bytes")

        summary = BackupSummary(
            status="created",
            profile_id=profile_id,
            path=final_dir,
            created_at=created_at,
            bytes=size_bytes,
            run_id=run_id,
            rotation=rotation,
        )

        self._event_logger(
            {
                "event": "SESSION_BACKUP_CREATED",
                "profileId": profile_id,
                "runId": run_id,
                "path": str(final_dir),
                "bytes": size_bytes,
                "elapsedSeconds": elapsed,
                "rotation": {
                    "kept": [str(value) for value in rotation.get("kept", [])],
                    "removed": [str(value) for value in rotation.get("removed", [])],
                },
            }
        )
        return summary

    def restore_latest(
        self,
        profile_id: str,
        target_dir: Path,
        *,
        run_id: str | None = None,
    ) -> BackupSummary:
        """Restore the most recent backup into the target directory."""

        if not self.enabled:
            summary = BackupSummary(
                status="skipped",
                profile_id=profile_id,
                path=None,
                created_at=None,
                bytes=None,
                run_id=run_id,
                reason="disabled",
            )
            self._event_logger(
                {
                    "event": "SESSION_RESTORE_SKIPPED",
                    "profileId": profile_id,
                    "runId": run_id,
                    "reason": "disabled",
                }
            )
            return summary

        latest = self._latest_backup_dir(profile_id)
        if latest is None:
            summary = BackupSummary(
                status="missing",
                profile_id=profile_id,
                path=None,
                created_at=None,
                bytes=None,
                run_id=run_id,
                reason="no_backups",
            )
            self._event_logger(
                {
                    "level": "warning",
                    "event": "SESSION_RESTORE_UNAVAILABLE",
                    "profileId": profile_id,
                    "runId": run_id,
                    "reason": "no_backups",
                }
            )
            return summary

        metadata = self._load_metadata(latest)
        created_at = metadata.get("createdAt")
        bytes_copied = metadata.get("bytes")

        try:
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            temp_dir = Path(
                tempfile.mkdtemp(prefix=".tmp-restore-", dir=str(target_dir.parent))
            )
            shutil.copytree(
                latest,
                temp_dir,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("metadata.json"),
            )
            if target_dir.exists():
                shutil.rmtree(target_dir)
            temp_dir.replace(target_dir)
        except Exception as exc:  # pragma: no cover - defensive
            shutil.rmtree(temp_dir, ignore_errors=True)
            self._event_logger(
                {
                    "level": "error",
                    "event": "SESSION_RESTORE_FAILED",
                    "profileId": profile_id,
                    "runId": run_id,
                    "path": str(latest),
                    "error": str(exc),
                }
            )
            return BackupSummary(
                status="failed",
                profile_id=profile_id,
                path=latest,
                created_at=created_at,
                bytes=bytes_copied,
                run_id=run_id,
                reason=str(exc),
            )

        summary = BackupSummary(
            status="restored",
            profile_id=profile_id,
            path=latest,
            created_at=created_at,
            bytes=bytes_copied,
            run_id=run_id,
        )
        self._event_logger(
            {
                "event": "SESSION_RESTORED",
                "profileId": profile_id,
                "runId": run_id,
                "path": str(latest),
                "createdAt": created_at,
                "bytes": bytes_copied,
            }
        )
        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _latest_backup_dir(self, profile_id: str) -> Path | None:
        profile_root = self.backups_root / profile_id
        if not profile_root.exists():
            return None
        backups = sorted(
            (
                child
                for child in profile_root.iterdir()
                if child.is_dir() and not child.name.startswith(".tmp-")
            ),
            key=lambda item: item.name,
            reverse=True,
        )
        return backups[0] if backups else None

    def _load_metadata(self, directory: Path) -> Dict[str, Any]:
        metadata_path = directory / "metadata.json"
        if metadata_path.exists():
            try:
                return json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _enforce_retention(self, profile_root: Path) -> Dict[str, List[str]]:
        backups = sorted(
            (
                child
                for child in profile_root.iterdir()
                if child.is_dir() and not child.name.startswith(".tmp-")
            ),
            key=lambda item: item.name,
            reverse=True,
        )
        kept = backups[: self.retention]
        removed = backups[self.retention :]
        for directory in removed:
            shutil.rmtree(directory, ignore_errors=True)
        return {"kept": kept, "removed": removed}

