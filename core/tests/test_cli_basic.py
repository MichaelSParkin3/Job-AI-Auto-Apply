import json
import os
import sys
from pathlib import Path

from typer.testing import CliRunner

# Ensure repo root is on path for package imports
sys.path.insert(0, os.getcwd())
from apps.cli.main import app


runner = CliRunner()


def test_help_lists_core_commands(tmp_path: Path, monkeypatch):
    """Verify that the main --help output lists all core commands."""
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    # Expect top-level subcommands present
    for cmd in ["apply", "profiles", "config", "history"]:
        assert cmd in out


def test_config_init_creates_files_and_dirs(tmp_path: Path, monkeypatch):
    """Verify that `config init` creates the necessary files and directories."""
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    # Run config init
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    # Validate dirs
    for d in [
        tmp_path / "config",
        tmp_path / "data" / "profiles",
        tmp_path / "data" / "resumes",
        tmp_path / ".local",
        tmp_path / ".local" / "browser",
        tmp_path / ".local" / "browser" / "profiles",
        tmp_path / ".local" / "state",
        tmp_path / "runs",
        tmp_path / "history",
    ]:
        assert d.exists() and d.is_dir()
    # Validate config file
    cfg = tmp_path / "config" / "config.yaml"
    assert cfg.exists()


def test_env_loading_missing_and_present(tmp_path: Path, monkeypatch):
    """Verify that settings load correctly with and without a .env.local file."""
    from apps.cli.config_loader import Settings

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    # Missing .env.local should not crash
    s = Settings.load()
    assert s.OPENROUTER_API_KEY is None

    # Present .env.local should be read
    env_file = tmp_path / ".env.local"
    env_file.write_text("OPENROUTER_API_KEY=abc123\nOPENROUTER_MODEL=demo-model", encoding="utf-8")
    s2 = Settings.load()
    assert s2.OPENROUTER_API_KEY == "abc123"
    assert s2.OPENROUTER_MODEL == "demo-model"


def test_settings_browser_overrides_from_config(tmp_path: Path, monkeypatch):
    """Nested browser keys in config.yaml and CLI overrides are respected."""
    from apps.cli.config_loader import Settings, ensure_runtime_dirs, config_path

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    ensure_runtime_dirs(tmp_path)
    cfg = config_path(tmp_path)
    cfg.write_text(
        """
browser:
  model: nested-model
  locale: en-GB
  timezone: Europe/London
  viewport:
    width: 1440
    height: 900
""",
        encoding="utf-8",
    )

    settings = Settings.load(base=tmp_path)
    assert settings.browser_model == "nested-model"
    assert settings.browser_locale == "en-GB"
    assert settings.browser_timezone == "Europe/London"
    assert settings.browser_viewport_width == 1440
    assert settings.browser_viewport_height == 900

    override_settings = Settings.load(
        base=tmp_path, overrides={"browser.model": "cli-model", "browser.viewport_width": 1600}
    )
    assert override_settings.browser_model == "cli-model"
    assert override_settings.browser_viewport_width == 1600
