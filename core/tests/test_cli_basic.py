import json
import json
import os
import sys
import types
from pathlib import Path

import pytest

try:  # pragma: no cover - exercised when typer is not installed
    from typer.testing import CliRunner
except ModuleNotFoundError:  # pragma: no cover - exercised in CI agents missing typer
    pytest.skip("typer not installed", allow_module_level=True)

# Ensure repo root is on path for package imports
sys.modules.setdefault("yaml", types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {}))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))
if "pydantic" not in sys.modules:
    class _BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self) -> dict[str, object]:
            return dict(self.__dict__)

    def _field(default=None, **_kwargs):  # pragma: no cover - simple stub
        return default

    class _ValidationError(Exception):
        pass

    def _identity_validator(*_args, **_kwargs):  # pragma: no cover
        def _decorator(func):
            return func

        return _decorator

    sys.modules["pydantic"] = types.SimpleNamespace(
        BaseModel=_BaseModel,
        Field=_field,
        ValidationError=_ValidationError,
        ConfigDict=dict,
        field_validator=_identity_validator,
        model_validator=_identity_validator,
        root_validator=_identity_validator,
        validator=_identity_validator,
    )
sys.path.insert(0, os.getcwd())
from apps.cli.history_store import HistoryWriter
from apps.cli.queue_manager import ApplicationCandidate, ReviewQueueManager
from apps.cli.main import app
from apps.cli.run_store import RunStore
from apps.cli.runtime_state import get_run_context, set_run_context


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


def test_history_summary_cli_outputs_json(tmp_path: Path, monkeypatch):
    """history summary surfaces decision aggregates with JSON output."""

    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa")
    context = get_run_context()
    assert context is not None
    decision = {
        "decisionId": "cli-1",
        "candidateId": "cand-json",
        "outcome": "approve",
        "mode": "human",
        "confidence": 0.8,
        "rationale": "Manual QA approval.",
        "timestamp": "2025-05-01T08:00:00Z",
    }
    stored = store.record_submission_decision(record, decision)
    queue_payload = store.load_queue_snapshot(record)
    queue_payload.setdefault("decided", []).append(stored)
    queue_payload["lastUpdated"] = stored["timestamp"]
    store.save_queue_snapshot(record, queue_payload)

    writer = HistoryWriter(base=tmp_path)
    run_payload = store.load_run_payload(record)
    writer.append_decision_summary(
        context,
        run_payload=run_payload,
        queue_payload=queue_payload,
        decision_payload=stored,
    )

    result = runner.invoke(app, ["history", "summary", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["approved"] == 1
    assert data[0]["needs_review"] == 0
    assert data[0]["escalated"] == 0
    assert data[0]["rationaleRedacted"] is False

    result_table = runner.invoke(app, ["history", "summary", "--last"])
    assert result_table.exit_code == 0
    assert "Approved" in result_table.stdout
    set_run_context(None)


def test_apply_queue_override_command(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa")
    manager = ReviewQueueManager(run_store=store, run_record=record)
    candidate = ApplicationCandidate(
        id="cand-override",
        posting={"postingUrl": "https://example.com"},
        form_plan_path=None,
        discovered_at="2025-01-01T00:00:00Z",
        state="awaiting_decision",
        assigned_mode="ai",
    )
    manager.enqueue(candidate)
    manager.assign_mode("cand-override", "ai", trigger="setup")

    result = runner.invoke(
        app,
        [
            "apply",
            "queue",
            "--run",
            record.id,
            "--candidate",
            "cand-override",
            "--action",
            "escalate",
            "--reason",
            "manual review",
        ],
    )
    assert result.exit_code == 0
    queue_payload = store.load_queue_snapshot(record)
    assert queue_payload["escalated"][0]["assignedMode"] == "human"
    run_payload = store.load_run_payload(record)
    overrides = run_payload.get("overrides", [])
    assert overrides and overrides[-1]["mode"] == "human"
