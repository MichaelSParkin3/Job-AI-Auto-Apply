"""Tests for profile management CLI commands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, os.getcwd())
from apps.cli.config_loader import Settings
from apps.cli.main import app


runner = CliRunner()


def _init_profile(tmp_path: Path, profile_id: str = "frontend-dev") -> Path:
    """Create a profile template and seed identity fields."""

    profile_path = tmp_path / "data" / "profiles" / f"{profile_id}.yaml"
    if not profile_path.exists():
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        display = profile_id.replace("-", " ").title()
        profile_yaml = f"""
id: {json.dumps(profile_id)}
display_name: {json.dumps(display)}
identity:
  full_name: "Alex Example"
  email: "alex@example.com"
  phone: null
  location: null
  portfolio: []
documents:
  resume_path: data/resumes/{profile_id}/resume.pdf
model_overrides: {{}}
qa_overrides: {{}}
links: {{}}
user_data_dir: .local/browser/profiles/{profile_id}
browser: {{}}
"""
        profile_path.write_text(profile_yaml.strip() + "\n", encoding="utf-8")
    return profile_path


def _parse_json_output(output: str) -> dict:
    """Parse the trailing JSON object from CLI output."""

    lines = [line for line in output.splitlines() if line.strip()]
    for idx in range(len(lines) - 1, -1, -1):
        candidate = lines[idx].strip()
        if candidate.startswith("{") or candidate.startswith("["):
            payload = "\n".join(lines[idx:])
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No JSON payload found in output: {output!r}")


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
    assert summary["valid"] is True
    assert summary["resume"]["exists"] is True
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
    assert payload["profile"]["id"] == "frontend-dev"
    assert payload["profile"]["valid"] is True

    settings = Settings.load(base=Path(str(tmp_path)))
    assert settings.active_profile == "frontend-dev"

    current = runner.invoke(app, ["profiles", "current"], color=False)
    assert current.exit_code == 0
    current_payload = _parse_json_output(current.stdout)
    assert current_payload["id"] == "frontend-dev"
    assert current_payload["valid"] is True
    assert current_payload["browser"] == {}

    listing = runner.invoke(app, ["profiles", "list"], color=False)
    assert listing.exit_code == 0
    entries = _parse_json_output(listing.stdout)
    assert entries[0]["id"] == "frontend-dev"
    assert entries[0]["active"] is True
