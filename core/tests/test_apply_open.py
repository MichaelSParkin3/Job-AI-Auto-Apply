import json
import json
import os
import sys
from pathlib import Path

import pytest

try:  # pragma: no cover - optional dependency guard
    from typer.testing import CliRunner
except ModuleNotFoundError:  # pragma: no cover - executed only when typer missing
    pytest.skip("typer not installed", allow_module_level=True)

sys.path.insert(0, os.getcwd())
from apps.browser import BrowserLaunchError, SessionBackupManager
from apps.cli.main import app


runner = CliRunner()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTOR_SOURCE = (
    PROJECT_ROOT / "sites" / "simplyhired" / "selectors" / "search-readiness.json"
)
FIXTURES_DIR = PROJECT_ROOT / "core" / "tests" / "fixtures" / "simplyhired" / "search"
QUICK_APPLY_SELECTOR_SOURCE = (
    PROJECT_ROOT / "sites" / "simplyhired" / "selectors" / "quick-apply.json"
)
QUICK_APPLY_FIXTURES_DIR = (
    PROJECT_ROOT / "core" / "tests" / "fixtures" / "simplyhired" / "quick_apply"
)


def _parse_last_json(output: str) -> dict:
    lines = [line for line in output.splitlines() if line.strip()]
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip().startswith(("{", "[")):
            payload = "\n".join(lines[idx:])
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No JSON payload found in output: {output!r}")


def _prepare_search_selectors(base: Path) -> Path:
    target = base / "sites" / "simplyhired" / "selectors"
    target.mkdir(parents=True, exist_ok=True)
    destination = target / "search-readiness.json"
    destination.write_text(SELECTOR_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _prepare_quick_apply_selectors(base: Path) -> Path:
    target = base / "sites" / "simplyhired" / "selectors"
    target.mkdir(parents=True, exist_ok=True)
    destination = target / "quick-apply.json"
    destination.write_text(
        QUICK_APPLY_SELECTOR_SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return destination


def _load_quick_apply_fixture(name: str) -> str:
    return (QUICK_APPLY_FIXTURES_DIR / name).read_text(encoding="utf-8")


def _bootstrap_profile(
    base: Path,
    profile_id: str = "frontend-dev",
    *,
    display_name: str | None = None,
    model: str = "profile-model",
    locale: str = "en-GB",
    timezone: str = "Europe/London",
    viewport: tuple[int, int] = (1440, 900),
    allowed_domains: list[str] | None = None,
) -> Path:
    profile_path = base / "data" / "profiles" / f"{profile_id}.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    display = display_name or profile_id.replace("-", " ").title()
    allowed = allowed_domains if allowed_domains is not None else [
        "*.simplyhired.com",
        "example.com",
    ]
    allowed_yaml = "\n".join(f"    - {json.dumps(domain)}" for domain in allowed)
    profile_yaml = f"""
identity:
  full_name: "Alex Example"
  email: "alex@example.com"
  phone: null
  location: "Remote"
  portfolio: []
documents:
  resume_path: data/resumes/{profile_id}/resume.pdf
id: {json.dumps(profile_id)}
display_name: {json.dumps(display)}
model_overrides:
  llm: {json.dumps(model)}
qa_overrides: {{}}
links: {{}}
user_data_dir: .local/browser/profiles/{profile_id}
browser:
  model: {json.dumps(model)}
  locale: {json.dumps(locale)}
  timezone: {json.dumps(timezone)}
  viewport:
    width: {viewport[0]}
    height: {viewport[1]}
  chrome_path: "C:/Program Files/Google/Chrome/Application/chrome.exe"
  allowed_domains:
{allowed_yaml}
"""
    profile_path.write_text(profile_yaml.strip() + "\n", encoding="utf-8")
    resume = base / "data" / "resumes" / profile_id / "resume.pdf"
    resume.parent.mkdir(parents=True, exist_ok=True)
    resume.write_bytes(b"%PDF-1.4\n")
    return profile_path


class RecordingClient:
    def __init__(
        self,
        *,
        snapshots: list[str] | None = None,
        idle_failures: set[int] | None = None,
    ) -> None:
        self.open_calls: list[str] = []
        self._snapshots = snapshots or [""]
        self._snapshot_index = 0
        self._idle_failures = set(idle_failures or set())
        self.wait_for_idle_calls = 0
        self.safe_click_calls: list[tuple[str, float | None]] = []

    def open_url(self, url: str) -> dict[str, str]:
        self.open_calls.append(url)
        return {"opened": url}

    def wait_for_idle(self, timeout: float = 5.0) -> dict[str, float]:
        self.wait_for_idle_calls += 1
        if self.wait_for_idle_calls in self._idle_failures:
            raise RuntimeError("idle failed")
        return {"timeout": timeout}

    def get_page_content(self) -> str:
        index = min(self._snapshot_index, len(self._snapshots) - 1)
        html = self._snapshots[index]
        if self._snapshot_index < len(self._snapshots) - 1:
            self._snapshot_index += 1
        return html

    def safe_click(self, selector: str, timeout: float | None = None) -> dict[str, str | float | None]:
        self.safe_click_calls.append((selector, timeout))
        return {"selector": selector, "timeout": timeout}


def test_apply_open_uses_profile_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _prepare_search_selectors(tmp_path)
    _prepare_quick_apply_selectors(tmp_path)
    _bootstrap_profile(tmp_path)

    captured_config: dict[str, object] = {}

    baseline_html = _load_fixture("baseline.html")

    def factory(config):
        client = RecordingClient(snapshots=[baseline_html])
        captured_config["config"] = config
        captured_config["client"] = client
        return client

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)
    monkeypatch.setattr("apps.cli.main.time.sleep", lambda *_args, **_kwargs: None)

    result_use = runner.invoke(app, ["profiles", "use", "frontend-dev"], color=False)
    assert result_use.exit_code == 0

    result = runner.invoke(app, ["apply", "open", "https://example.com/search?q=python"], color=False)
    assert result.exit_code == 0, result.stdout
    payload = _parse_last_json(result.stdout)

    assert payload["profileId"] == "frontend-dev"
    assert payload["viewport"] == {"width": 1440, "height": 900}
    assert payload["locale"] == "en-GB"
    assert payload["timezone"] == "Europe/London"
    assert payload["model"] == "profile-model"
    assert Path(payload["userDataDir"]).exists()
    assert captured_config["client"].open_calls == ["https://example.com/search?q=python"]
    assert payload["guardrails"]["allowedDomains"] == ["*.simplyhired.com", "example.com"]
    assert payload["guardrails"]["pacing"]["waitJitterMs"] == [100, 600]
    assert payload["telemetry"]["guardrailEvent"]["event"] == "guardrail.browser.NAVIGATE"
    assert payload["profile"]["id"] == "frontend-dev"
    assert payload["profile"]["valid"] is True
    assert payload["profile"]["resume"]["exists"] is True
    assert payload["profile"]["resume"]["path"].endswith(os.path.join("frontend-dev", "resume.pdf"))
    assert payload["profile"]["browser"]["allowed_domains"] == [
        "*.simplyhired.com",
        "example.com",
    ]
    assert payload["telemetry"]["profile"]["id"] == "frontend-dev"
    assert payload["telemetry"]["profile"]["resume"]["exists"] is True
    assert payload["telemetry"]["profile"]["qaOverrideKeys"] == []

    readiness = payload["readiness"]
    assert readiness["status"] == "ready"
    assert readiness["attempts"][0]["ok"] is True
    assert Path(readiness["artifacts"]["html"][-1]).exists()
    assert payload["telemetry"]["searchReadiness"]["status"] == "ready"

    assert payload["limit"] == 2
    discovery = payload["discovery"]
    assert discovery["summary"]["processedCount"] == 0
    assert discovery["summary"]["openedCount"] == 0
    assert discovery["summary"]["limitRequested"] == 2
    assert discovery["summary"]["limitRemaining"] == 2
    assert discovery["selectors"]["base"].endswith("quick-apply.json")
    assert payload["telemetry"]["quickApplyDiscovery"]["processed"] == 0
    assert payload["telemetry"]["quickApplyDiscovery"]["opened"] == 0

    run_dir = Path(payload["run"]["artifactsDir"])
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "quick_apply_discovery"
    assert run_json["discovery"]["summary"]["processedCount"] == 0
    backups = payload["backups"]
    assert backups["enabled"] is True
    assert backups["retention"] == 2
    assert backups["restoreAttempt"] is None
    last_backup = backups["lastBackup"]
    assert last_backup["status"] == "created"
    assert Path(last_backup["path"]).exists()
    session_backup = run_json["sessionBackup"]
    assert session_backup["enabled"] is True
    assert session_backup["retention"] == 2
    assert session_backup["lastBackup"]["status"] == "created"
    assert session_backup.get("restore") is None

    config = captured_config["config"]
    assert str(config.user_data_dir).endswith("frontend-dev")
    assert config.viewport_width == 1440
    assert config.viewport_height == 900
    assert config.locale == "en-GB"
    assert config.timezone == "Europe/London"
    assert "Chrome" in (config.chrome_path or "")
    assert config.profile_binding["id"] == "frontend-dev"
    assert config.profile_metadata["id"] == "frontend-dev"

    result_override = runner.invoke(
        app,
        [
            "apply",
            "open",
            "https://example.com/override",
            "--model",
            "cli-model",
            "--profile",
            "frontend-dev",
        ],
        color=False,
    )
    assert result_override.exit_code == 0, result_override.stdout
    payload_override = _parse_last_json(result_override.stdout)
    assert payload_override["model"] == "cli-model"
    assert payload_override["readiness"]["status"] == "ready"


def test_apply_open_runs_quick_apply_discovery(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _prepare_search_selectors(tmp_path)
    _prepare_quick_apply_selectors(tmp_path)
    _bootstrap_profile(tmp_path)

    snapshots = [
        _load_fixture("baseline.html"),
        _load_quick_apply_fixture("page-list-1.html"),
        _load_quick_apply_fixture("detail-modal-job-1.html"),
        _load_quick_apply_fixture("detail-missing-job-2.html"),
        _load_quick_apply_fixture("page-list-2.html"),
        _load_quick_apply_fixture("detail-inline-job-3.html"),
    ]

    captured: dict[str, RecordingClient] = {}

    def factory(config):
        client = RecordingClient(snapshots=snapshots)
        captured["client"] = client
        return client

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)
    monkeypatch.setattr("apps.cli.main.time.sleep", lambda *_args, **_kwargs: None)

    runner.invoke(app, ["profiles", "use", "frontend-dev"], color=False)

    result = runner.invoke(
        app,
        [
            "apply",
            "open",
            "https://simplyhired.com/search?q=qa",
            "--limit",
            "2",
        ],
        color=False,
    )
    assert result.exit_code == 0, result.stdout
    payload = _parse_last_json(result.stdout)

    discovery = payload["discovery"]
    summary = discovery["summary"]
    assert summary["processedCount"] == 3
    assert summary["openedCount"] == 2
    assert summary["missingCount"] == 1
    assert summary["duplicateCount"] == 1
    assert summary["limitRequested"] == 2
    assert summary["limitRemaining"] == 0
    assert summary["limitReached"] is True
    assert summary["pagesVisited"] == 2
    assert summary["paginationEvents"] == ["PAGINATED_NEXT"]

    candidates = discovery["candidates"]
    assert [candidate["status"] for candidate in candidates] == [
        "opened",
        "missing",
        "opened",
    ]
    assert candidates[0]["mode"] == "modal"
    assert candidates[1].get("mode") is None
    assert candidates[2]["mode"] == "inline"

    artifacts = discovery["artifacts"]
    assert len(artifacts) == 3
    for artifact in artifacts:
        assert Path(artifact).exists()

    telemetry = payload["telemetry"]["quickApplyDiscovery"]
    assert telemetry["opened"] == 2
    assert telemetry["missing"] == 1
    assert telemetry["duplicates"] == 1
    assert telemetry["limitRemaining"] == 0

    client = captured["client"]
    selectors_clicked = [call[0] for call in client.safe_click_calls]
    assert len(selectors_clicked) >= 6
    assert selectors_clicked[0].startswith("div[data-testid=searchSerpJob]")
    assert selectors_clicked[2].startswith("div[data-testid=searchSerpJob]")
    assert "pagination-next" in selectors_clicked[4]
    assert selectors_clicked[5].startswith("div[data-testid=searchSerpJob]")
    assert client.wait_for_idle_calls >= 5

    run_dir = Path(payload["run"]["artifactsDir"])
    discovery_dir = run_dir / "quick-apply"
    assert discovery_dir.exists()

    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["discovery"]["summary"]["openedCount"] == 2


def test_apply_open_blocks_when_resume_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _prepare_search_selectors(tmp_path)
    _prepare_quick_apply_selectors(tmp_path)
    _bootstrap_profile(tmp_path, profile_id="frontend-dev")
    resume_path = tmp_path / "data" / "resumes" / "frontend-dev" / "resume.pdf"
    resume_path.unlink()

    def factory(config):  # pragma: no cover - defensive assertion
        raise AssertionError("browser client should not be created when resume missing")

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)

    result = runner.invoke(
        app,
        [
            "apply",
            "open",
            "https://example.com/search?q=python",
            "--profile",
            "frontend-dev",
        ],
        color=False,
    )
    assert result.exit_code == 1
    error_payload = _parse_last_json(result.stdout)
    assert error_payload["error"]["code"] == "profiles.validation_failed"
    assert any(
        detail.get("code") == "profiles.resume_missing"
        for detail in error_payload["error"]["details"]["errors"]
    )


def test_apply_open_readiness_failure_records_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _prepare_search_selectors(tmp_path)
    _prepare_quick_apply_selectors(tmp_path)
    _bootstrap_profile(tmp_path, profile_id="frontend-dev")

    spinner_html = _load_fixture("spinner.html")

    def factory(config):
        return RecordingClient(snapshots=[spinner_html, spinner_html])

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)
    monkeypatch.setattr("apps.cli.main.time.sleep", lambda *_args, **_kwargs: None)

    result_use = runner.invoke(app, ["profiles", "use", "frontend-dev"], color=False)
    assert result_use.exit_code == 0

    result = runner.invoke(app, ["apply", "open", "https://example.com/search?q=python"], color=False)
    assert result.exit_code == 1, result.stdout
    payload = _parse_last_json(result.stdout)
    readiness = payload["readiness"]
    assert readiness["status"] == "unready"
    assert len(readiness["attempts"]) == 2
    assert readiness["attempts"][-1]["ok"] is False
    assert readiness["reason"] in {"insufficient_cards", "missing_detail"}
    for artifact in readiness["artifacts"]["html"]:
        assert Path(artifact).exists()

    run_dir = Path(payload["run"]["artifactsDir"])
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "search_unready"
    assert run_json["readiness"]["status"] == "unready"
    backups = payload["backups"]
    assert backups["enabled"] is True
    assert backups["restoreAttempt"] is None
    assert "lastBackup" not in backups
    session_backup = run_json["sessionBackup"]
    assert session_backup["enabled"] is True
    assert "lastBackup" not in session_backup


def test_apply_open_switch_profiles_isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _prepare_search_selectors(tmp_path)
    _prepare_quick_apply_selectors(tmp_path)
    _bootstrap_profile(tmp_path, profile_id="frontend-dev")
    _bootstrap_profile(
        tmp_path,
        profile_id="data-analyst",
        model="analyst-model",
        locale="en-US",
        timezone="America/New_York",
        viewport=(1280, 720),
        allowed_domains=["*.simplyhired.com", "data.example.com"],
    )

    launches: list[tuple[object, RecordingClient]] = []
    baseline_html = _load_fixture("baseline.html")

    def factory(config):
        client = RecordingClient(snapshots=[baseline_html])
        launches.append((config, client))
        return client

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)
    monkeypatch.setattr("apps.cli.main.time.sleep", lambda *_args, **_kwargs: None)

    result_use_first = runner.invoke(app, ["profiles", "use", "frontend-dev"], color=False)
    assert result_use_first.exit_code == 0

    first_run = runner.invoke(
        app,
        ["apply", "open", "https://example.com/search?q=python"],
        color=False,
    )
    assert first_run.exit_code == 0, first_run.stdout
    payload_first = _parse_last_json(first_run.stdout)
    first_dir = Path(payload_first["userDataDir"])
    assert payload_first["profile"]["id"] == "frontend-dev"
    assert payload_first["profile"]["browser"]["allowed_domains"] == [
        "*.simplyhired.com",
        "example.com",
    ]
    assert payload_first["readiness"]["status"] == "ready"

    result_use_second = runner.invoke(app, ["profiles", "use", "data-analyst"], color=False)
    assert result_use_second.exit_code == 0, result_use_second.stdout

    second_run = runner.invoke(
        app,
        [
            "apply",
            "open",
            "https://data.example.com/search?q=data+analyst",
        ],
        color=False,
    )
    assert second_run.exit_code == 0, second_run.stdout
    payload_second = _parse_last_json(second_run.stdout)
    second_dir = Path(payload_second["userDataDir"])
    assert payload_second["profile"]["id"] == "data-analyst"
    assert payload_second["profile"]["browser"]["allowed_domains"] == [
        "*.simplyhired.com",
        "data.example.com",
    ]
    assert payload_second["telemetry"]["profile"]["model"] == "analyst-model"
    assert payload_second["readiness"]["status"] == "ready"
    assert first_dir != second_dir

    assert len(launches) == 2
    first_config, _ = launches[0]
    second_config, _ = launches[1]
    assert first_config.profile_binding["id"] == "frontend-dev"
    assert second_config.profile_binding["id"] == "data-analyst"
    assert first_config.user_data_dir != second_config.user_data_dir


def test_apply_open_restores_session_on_launch_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _prepare_search_selectors(tmp_path)
    _prepare_quick_apply_selectors(tmp_path)
    _bootstrap_profile(tmp_path, profile_id="frontend-dev")

    session_dir = tmp_path / ".local" / "browser" / "profiles" / "frontend-dev"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "Preferences").write_text("{}", encoding="utf-8")
    manager = SessionBackupManager(tmp_path, enabled=True, retention=2)
    manager.create_backup("frontend-dev", session_dir, run_id="seed-run")
    (session_dir / "Preferences").unlink()

    baseline_html = _load_fixture("baseline.html")
    attempts = {"count": 0}

    def factory(config):
        if attempts["count"] == 0:
            attempts["count"] += 1
            raise BrowserLaunchError("corrupt profile")
        attempts["count"] += 1
        return RecordingClient(snapshots=[baseline_html])

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)
    monkeypatch.setattr("apps.cli.main.time.sleep", lambda *_args, **_kwargs: None)

    result_use = runner.invoke(app, ["profiles", "use", "frontend-dev"], color=False)
    assert result_use.exit_code == 0

    result = runner.invoke(app, ["apply", "open", "https://example.com/search?q=python"], color=False)
    assert result.exit_code == 0, result.stdout
    payload = _parse_last_json(result.stdout)

    assert attempts["count"] >= 2
    restore_attempt = payload["backups"]["restoreAttempt"]
    assert restore_attempt["status"] == "restored"
    assert restore_attempt["detectedReason"] in {"missing_preferences", "launch_error"}
    last_backup = payload["backups"]["lastBackup"]
    assert last_backup["status"] == "created"

    run_dir = Path(payload["run"]["artifactsDir"])
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    session_backup = run_json["sessionBackup"]
    assert session_backup["restore"]["status"] == "restored"
    assert session_backup["lastBackup"]["status"] == "created"


def test_apply_open_backup_disabled_skips(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _prepare_search_selectors(tmp_path)
    _prepare_quick_apply_selectors(tmp_path)
    _bootstrap_profile(tmp_path, profile_id="frontend-dev")

    baseline_html = _load_fixture("baseline.html")

    def factory(config):
        return RecordingClient(snapshots=[baseline_html])

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)
    monkeypatch.setattr("apps.cli.main.time.sleep", lambda *_args, **_kwargs: None)

    result_use = runner.invoke(app, ["profiles", "use", "frontend-dev"], color=False)
    assert result_use.exit_code == 0

    result = runner.invoke(
        app,
        [
            "apply",
            "open",
            "https://example.com/search?q=python",
            "--no-session-backups",
        ],
        color=False,
    )
    assert result.exit_code == 0, result.stdout
    payload = _parse_last_json(result.stdout)

    backups = payload["backups"]
    assert backups["enabled"] is False
    last_backup = backups["lastBackup"]
    assert last_backup["status"] == "skipped"
    assert last_backup["reason"] == "disabled"

    run_dir = Path(payload["run"]["artifactsDir"])
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    session_backup = run_json["sessionBackup"]
    assert session_backup["enabled"] is False
    assert session_backup["lastBackup"]["status"] == "skipped"
    backups_dir = tmp_path / ".local" / "browser" / "backups" / "frontend-dev"
    assert not backups_dir.exists()
