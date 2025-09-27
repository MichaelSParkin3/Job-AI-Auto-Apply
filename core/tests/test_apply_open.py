import json
import os
import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, os.getcwd())
from apps.cli.main import app


runner = CliRunner()


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
    def __init__(self) -> None:
        self.open_calls: list[str] = []

    def open_url(self, url: str) -> dict[str, str]:
        self.open_calls.append(url)
        return {"opened": url}

    def wait_for_idle(self, timeout: float = 5.0) -> dict[str, float]:
        return {"timeout": timeout}

    def safe_click(self, selector: str, timeout: float | None = None) -> dict[str, str | float | None]:
        return {"selector": selector, "timeout": timeout}


def test_apply_open_uses_profile_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _bootstrap_profile(tmp_path)

    captured_config: dict[str, object] = {}

    def factory(config):
        client = RecordingClient()
        captured_config["config"] = config
        captured_config["client"] = client
        return client

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)

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
    assert payload["profile"]["resume"]["path"].endswith("frontend-dev/resume.pdf")
    assert payload["profile"]["browser"]["allowed_domains"] == [
        "*.simplyhired.com",
        "example.com",
    ]
    assert payload["telemetry"]["profile"]["id"] == "frontend-dev"
    assert payload["telemetry"]["profile"]["resume"]["exists"] is True
    assert payload["telemetry"]["profile"]["qaOverrideKeys"] == []

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


def test_apply_open_blocks_when_resume_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
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


def test_apply_open_switch_profiles_isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
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

    def factory(config):
        client = RecordingClient()
        launches.append((config, client))
        return client

    monkeypatch.setattr("apps.browser.controller.create_browser_client", factory)

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
    assert first_dir != second_dir

    assert len(launches) == 2
    first_config, _ = launches[0]
    second_config, _ = launches[1]
    assert first_config.profile_binding["id"] == "frontend-dev"
    assert second_config.profile_binding["id"] == "data-analyst"
    assert first_config.user_data_dir != second_config.user_data_dir
