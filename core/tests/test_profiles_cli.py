"""Tests for profile management CLI commands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

sys.path.insert(0, os.getcwd())
from apps.cli.config_loader import Settings
from apps.cli.main import app


runner = CliRunner()


def _init_profile(tmp_path: Path, profile_id: str = "frontend-dev") -> Path:
    """Create a profile template and seed identity fields."""

    profile_path = tmp_path / "data" / "profiles" / f"{profile_id}.yaml"
    if not profile_path.exists():
        result = runner.invoke(app, ["profiles", "new", profile_id], color=False)
        assert result.exit_code == 0, result.stdout
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    data.setdefault("identity", {})
    data["identity"]["full_name"] = "Alex Example"
    data["identity"]["email"] = "alex@example.com"
    profile_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return profile_path


def _parse_json_output(output: str) -> dict:
    """Parse the trailing JSON object from CLI output."""

    lines = [line for line in output.splitlines() if line.strip()]
    start_idx = None
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip().startswith("{") or lines[idx].strip().startswith("["):
            start_idx = idx
            break
    if start_idx is None:
        raise ValueError(f"No JSON payload found in output: {output!r}")
    json_payload = "\n".join(lines[start_idx:])
    return json.loads(json_payload)


def test_profiles_validate_requires_resume(tmp_path: Path, monkeypatch):
    """`profiles validate` fails until a resume is present."""

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    profile_path = _init_profile(tmp_path)

    result_missing = runner.invoke(app, ["profiles", "validate", "frontend-dev"], color=False)
    assert result_missing.exit_code == 1
    payload = json.loads(result_missing.stdout.strip())
    assert payload["error"]["code"] == "profiles.validation_failed"
    assert any(err["code"] == "profiles.resume_missing" for err in payload["error"]["details"]["errors"])

    resume_file = tmp_path / "data" / "resumes" / "frontend-dev" / "resume.pdf"
    resume_file.parent.mkdir(parents=True, exist_ok=True)
    resume_file.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    result_ok = runner.invoke(app, ["profiles", "validate", "frontend-dev"], color=False)
    assert result_ok.exit_code == 0
    summary = _parse_json_output(result_ok.stdout)
    assert summary["id"] == "frontend-dev"
    assert summary["user_data_dir"].endswith("frontend-dev")
    assert summary["browser"] == {}


def test_profiles_use_sets_active_marker(tmp_path: Path, monkeypatch):
    """`profiles use` persists the active profile and updates settings."""

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _init_profile(tmp_path, "frontend-dev")
    resume_file = tmp_path / "data" / "resumes" / "frontend-dev" / "resume.pdf"
    resume_file.parent.mkdir(parents=True, exist_ok=True)
    resume_file.write_bytes(b"%PDF-1.4\n")

    result_use = runner.invoke(app, ["profiles", "use", "frontend-dev"], color=False)
    assert result_use.exit_code == 0
    payload = _parse_json_output(result_use.stdout)
    marker_path = Path(payload["marker"])
    assert marker_path.exists()

    settings = Settings.load(base=Path(str(tmp_path)))
    assert settings.active_profile == "frontend-dev"

    current = runner.invoke(app, ["profiles", "current"], color=False)
    assert current.exit_code == 0
    current_payload = json.loads(current.stdout.strip())
    assert current_payload["id"] == "frontend-dev"
    assert current_payload["valid"] is True
    assert current_payload["browser"] == {}

    listing = runner.invoke(app, ["profiles", "list"], color=False)
    assert listing.exit_code == 0
    entries = json.loads(listing.stdout)
    assert entries[0]["id"] == "frontend-dev"
    assert entries[0]["active"] is True
