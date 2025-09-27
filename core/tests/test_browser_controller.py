import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.getcwd())
from apps.browser.controller import (
    BrowserActionStatus,
    BrowserLaunchConfig,
    BrowserUseController,
)


class StubClient:
    def __init__(self) -> None:
        self.open_calls: list[str] = []
        self.idle_calls: list[float] = []
        self.click_calls: list[tuple[str, float | None]] = []

    def open_url(self, url: str) -> dict[str, str]:
        self.open_calls.append(url)
        return {"url": url}

    def wait_for_idle(self, timeout: float = 5.0) -> dict[str, float]:
        self.idle_calls.append(timeout)
        return {"timeout": timeout}

    def safe_click(self, selector: str, timeout: float | None = None) -> dict[str, str | float | None]:
        self.click_calls.append((selector, timeout))
        return {"selector": selector, "timeout": timeout}


def test_browser_controller_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[dict[str, object]] = []

    def fake_log(event: dict[str, object]) -> None:
        events.append(event)

    monkeypatch.setattr("apps.browser.controller.log_event", fake_log)

    captured_config: dict[str, BrowserLaunchConfig] = {}

    def factory(config: BrowserLaunchConfig) -> StubClient:
        captured_config["config"] = config
        return StubClient()

    config = BrowserLaunchConfig(
        profile_id="frontend-dev",
        user_data_dir=tmp_path,
        model="profile-model",
        viewport_width=1366,
        viewport_height=768,
        locale="en-US",
        timezone="America/Los_Angeles",
    )
    controller = BrowserUseController(config, client_factory=factory)

    open_result = controller.open_url("https://example.com")
    assert open_result.status is BrowserActionStatus.OK
    assert captured_config["config"].keep_alive is True

    idle_result = controller.wait_for_idle(timeout=3.0)
    assert idle_result.status is BrowserActionStatus.OK

    click_result = controller.safe_click("button.apply", timeout=2.5)
    assert click_result.status is BrowserActionStatus.OK

    assert any(event["event"] == "browser.session.opened" for event in events)


def test_browser_controller_open_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_log(event: dict[str, object]) -> None:
        pass

    monkeypatch.setattr("apps.browser.controller.log_event", fake_log)

    class FailingClient:
        def open_url(self, url: str) -> None:
            raise RuntimeError("boom")

        def wait_for_idle(self, timeout: float = 5.0) -> None:
            raise AssertionError("should not be called")

        def safe_click(self, selector: str, timeout: float | None = None) -> None:
            raise AssertionError("should not be called")

    def factory(config: BrowserLaunchConfig) -> FailingClient:
        return FailingClient()

    config = BrowserLaunchConfig(
        profile_id="qa",
        user_data_dir=tmp_path,
        model="fallback",
        viewport_width=1280,
        viewport_height=720,
        locale="en-US",
        timezone="UTC",
    )
    controller = BrowserUseController(config, client_factory=factory)

    result = controller.open_url("https://example.com")
    assert result.status is BrowserActionStatus.ERROR
    assert "error" in result.details
