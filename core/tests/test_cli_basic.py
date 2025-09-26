from pathlib import Path
import sys
import os
import json
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
        tmp_path / ".local",
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
    # Missing .env.local should not crash
    s = Settings.load()
    assert s.OPENROUTER_API_KEY is None

    # Present .env.local should be read
    env_file = tmp_path / ".env.local"
    env_file.write_text("OPENROUTER_API_KEY=abc123\nOPENROUTER_MODEL=demo-model", encoding="utf-8")
    s2 = Settings.load()
    assert s2.OPENROUTER_API_KEY == "abc123"
    assert s2.OPENROUTER_MODEL == "demo-model"
