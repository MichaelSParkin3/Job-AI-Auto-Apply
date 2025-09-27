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
        if lines[idx].strip().startswith("{"):
            payload = "\n".join(lines[idx:])
            return json.loads(payload)
    raise ValueError(f"No JSON payload found in output: {output!r}")


def _bootstrap_profile(base: Path) -> Path:
    profile_path = base / "data" / "profiles" / "frontend-dev.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        """
identity:
  full_name: Alex Example
  email: alex@example.com
  phone: null
  location: Remote
  portfolio: []
documents:
  resume_path: data/resumes/frontend-dev/resume.pdf
id: frontend-dev
display_name: Frontend Dev
model_overrides:
  llm: profile-model
tools: {}
qa_overrides: {}
links: {}
user_data_dir: .local/browser/profiles/frontend-dev
browser:
  model: profile-model
  locale: en-GB
  timezone: Europe/London
  viewport:
    width: 1440
    height: 900
  chrome_path: C:/Program Files/Google/Chrome/Application/chrome.exe
  allowed_domains:
    - "*.simplyhired.com"
    - example.com
""",
        encoding="utf-8",
    )
    resume = base / "data" / "resumes" / "frontend-dev" / "resume.pdf"
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

    config = captured_config["config"]
    assert str(config.user_data_dir).endswith("frontend-dev")
    assert config.viewport_width == 1440
    assert config.viewport_height == 900
    assert config.locale == "en-GB"
    assert config.timezone == "Europe/London"
    assert "Chrome" in (config.chrome_path or "")

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
