"""Unit tests for the SessionBackupManager utility."""

from __future__ import annotations

import json
from pathlib import Path

from apps.browser.session_backup import SessionBackupManager


def _create_session_dir(base: Path, name: str, *, preferences: str = "{}") -> Path:
    session_dir = base / name
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "Preferences").write_text(preferences, encoding="utf-8")
    (session_dir / "Local State").write_text("{}", encoding="utf-8")
    (session_dir / "Visited Links").write_text("seed", encoding="utf-8")
    nested = session_dir / "Default" / "Cache"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "f.txt").write_text("payload", encoding="utf-8")
    return session_dir


def test_create_backup_and_rotation(tmp_path: Path):
    events: list[dict] = []
    manager = SessionBackupManager(
        tmp_path,
        enabled=True,
        retention=2,
        event_logger=events.append,
    )
    session_dir = _create_session_dir(tmp_path, "session")

    summary1 = manager.create_backup("alpha", session_dir, run_id="run-1")
    summary2 = manager.create_backup("alpha", session_dir, run_id="run-2")
    summary3 = manager.create_backup("alpha", session_dir, run_id="run-3")

    backups_dir = tmp_path / ".local" / "browser" / "backups" / "alpha"
    backups = [child for child in backups_dir.iterdir() if child.is_dir()]

    assert summary3.status == "created"
    assert len(backups) == 2
    metadata_path = summary3.path / "metadata.json"  # type: ignore[union-attr]
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["runId"] == "run-3"
    assert metadata["bytes"] > 0
    rotation_events = [event for event in events if event.get("event") == "SESSION_BACKUP_CREATED"]
    assert rotation_events, "Expected SESSION_BACKUP_CREATED events"


def test_restore_latest(tmp_path: Path):
    manager = SessionBackupManager(tmp_path, enabled=True, retention=2)
    session_dir = _create_session_dir(tmp_path, "active")
    manager.create_backup("beta", session_dir, run_id="seed")

    # Corrupt the active session directory then restore
    for child in session_dir.iterdir():
        if child.is_file():
            child.unlink()

    summary = manager.restore_latest("beta", session_dir, run_id="restored-run")
    assert summary.status == "restored"
    assert (session_dir / "Preferences").exists()
    assert (session_dir / "Default" / "Cache" / "f.txt").exists()


def test_backup_disabled_reports_skip(tmp_path: Path):
    events: list[dict] = []
    manager = SessionBackupManager(
        tmp_path,
        enabled=False,
        retention=2,
        event_logger=events.append,
    )
    session_dir = _create_session_dir(tmp_path, "disabled")

    summary = manager.create_backup("gamma", session_dir, run_id="run-0")
    assert summary.status == "skipped"
    assert summary.reason == "disabled"
    restore_summary = manager.restore_latest("gamma", session_dir, run_id="run-0")
    assert restore_summary.status == "skipped"
    assert restore_summary.reason == "disabled"
    skip_events = {event["event"] for event in events}
    assert "SESSION_BACKUP_SKIPPED" in skip_events
    assert "SESSION_RESTORE_SKIPPED" in skip_events
