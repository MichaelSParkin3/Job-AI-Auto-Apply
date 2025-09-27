import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.getcwd())
from apps.browser.controller import (  # noqa: E402
    BrowserActionStatus,
    BrowserLaunchConfig,
    BrowserUseController,
)
from apps.browser.guardrails import NavigationGuardrails  # noqa: E402


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


def build_guardrails(events: list[dict[str, Any]]) -> NavigationGuardrails:
    return NavigationGuardrails(
        allowed_domains=("*.example.com",),
        wait_jitter_ms=(0, 0),
        think_time_range_s=(0.0, 0.0),
        event_logger=events.append,
        sleep=lambda _: None,
    )


def test_browser_controller_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []

    def fake_log(event: dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr("apps.browser.controller.log_event", fake_log)

    captured: dict[str, Any] = {}

    def factory(config: BrowserLaunchConfig) -> StubClient:
        captured["config"] = config
        client = StubClient()
        captured["client"] = client
        return client

    config = BrowserLaunchConfig(
        profile_id="frontend-dev",
        user_data_dir=tmp_path,
        model="profile-model",
        viewport_width=1366,
        viewport_height=768,
        locale="en-US",
        timezone="America/Los_Angeles",
        guardrail_domains=("*.example.com",),
        wait_jitter_ms=(0, 0),
        think_time_range_s=(0.0, 0.0),
    )
    controller = BrowserUseController(
        config,
        client_factory=factory,
        guardrails=build_guardrails(events),
    )

    open_result = controller.open_url("https://jobs.example.com/listing")
    assert open_result.status is BrowserActionStatus.OK
    assert captured["config"].keep_alive is True
    assert captured["client"].open_calls == ["https://jobs.example.com/listing"]
    assert open_result.telemetry["guardrailEvent"]["event"] == "guardrail.browser.NAVIGATE"

    idle_result = controller.wait_for_idle(timeout=3.0)
    assert idle_result.status is BrowserActionStatus.OK

    click_result = controller.safe_click("button.apply", timeout=2.5, think_time=True)
    assert click_result.status is BrowserActionStatus.OK

    guardrail_events = [evt for evt in events if evt.get("event", "").startswith("guardrail.browser")]
    assert any(evt["event"] == "guardrail.browser.NAVIGATE" for evt in guardrail_events)
    assert any(evt["event"] == "guardrail.browser.THINK_TIME" for evt in guardrail_events)
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
        guardrail_domains=("*.example.com",),
        wait_jitter_ms=(0, 0),
        think_time_range_s=(0.0, 0.0),
    )
    controller = BrowserUseController(
        config,
        client_factory=factory,
        guardrails=build_guardrails([]),
    )

    result = controller.open_url("https://example.com")
    assert result.status is BrowserActionStatus.ERROR
    assert "error" in result.details


def test_browser_controller_blocks_off_domain(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []

    def fake_log(event: dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr("apps.browser.controller.log_event", fake_log)

    captured = StubClient()

    def factory(config: BrowserLaunchConfig) -> StubClient:
        return captured

    config = BrowserLaunchConfig(
        profile_id="frontend-dev",
        user_data_dir=tmp_path,
        model="profile-model",
        viewport_width=1280,
        viewport_height=720,
        locale="en-US",
        timezone="UTC",
        guardrail_domains=("*.example.com",),
        wait_jitter_ms=(0, 0),
        think_time_range_s=(0.0, 0.0),
    )
    controller = BrowserUseController(
        config,
        client_factory=factory,
        guardrails=build_guardrails(events),
    )

    result = controller.open_url("https://evil.com")
    assert result.status is BrowserActionStatus.ERROR
    assert result.details["error"] == "blocked_domain"
    assert result.telemetry["guardrailEvent"]["event"] == "guardrail.browser.BLOCKED_DOMAIN"
    assert captured.open_calls == []


def test_browser_controller_blocks_new_tab(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []

    def fake_log(event: dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr("apps.browser.controller.log_event", fake_log)

    stub = StubClient()

    def factory(config: BrowserLaunchConfig) -> StubClient:
        return stub

    config = BrowserLaunchConfig(
        profile_id="frontend-dev",
        user_data_dir=tmp_path,
        model="profile-model",
        viewport_width=1366,
        viewport_height=768,
        locale="en-US",
        timezone="America/Los_Angeles",
        guardrail_domains=("*.example.com",),
        wait_jitter_ms=(0, 0),
        think_time_range_s=(0.0, 0.0),
    )
    controller = BrowserUseController(
        config,
        client_factory=factory,
        guardrails=build_guardrails(events),
    )

    result = controller.open_url("https://jobs.example.com", allow_new_tab=True)
    assert result.status is BrowserActionStatus.ERROR
    assert result.details["error"] == "new_tab_blocked"
    assert result.telemetry["guardrailEvent"]["event"] == "guardrail.browser.NEW_TAB_ATTEMPT"
    assert stub.open_calls == []


def test_guardrails_maintain_single_tab_count_after_blocked_attempts() -> None:
    events: list[dict[str, Any]] = []
    guardrails = build_guardrails(events)

    first = guardrails.block_new_tab({}, reason="popup")
    assert first.event["guardrails"]["tabCount"] == 1
    assert first.event["guardrails"]["blockedTabAttempts"] == 1

    second = guardrails.block_new_tab({}, reason="window")
    assert second.event["guardrails"]["tabCount"] == 1
    assert second.event["guardrails"]["blockedTabAttempts"] == 2

    decision = guardrails.before_navigation("https://jobs.example.com/listing", {})
    assert decision.allowed is True
    assert decision.event["guardrails"]["tabCount"] == 1
    assert decision.event["guardrails"]["blockedTabAttempts"] == 2
