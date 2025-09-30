import types
from pathlib import Path
from typing import Any

import pytest

from apps.browser import BrowserActionResult, BrowserActionStatus
from sites.lever.resume_analysis import (
    ResumeAnalysisResult,
    ResumeAnalysisSettings,
    load_resume_analysis_settings,
    wait_for_analysis,
)


class StubController:
    def __init__(self, *, success_after: int = 1, idle_ok: bool = True) -> None:
        self.config = types.SimpleNamespace(wait_jitter_ms=(0, 0))
        self._success_after = success_after
        self._calls = 0
        self._idle_ok = idle_ok

    def wait_for_idle(self, timeout: float = 5.0) -> BrowserActionResult:
        status = BrowserActionStatus.OK if self._idle_ok else BrowserActionStatus.ERROR
        details = {"response": {"timeout": timeout}} if self._idle_ok else {"error": "not_idle"}
        return BrowserActionResult(status=status, details=details, telemetry={"event": "stub.idle"})

    def get_page_html(self) -> BrowserActionResult:
        self._calls += 1
        html = f"<html><body><div data-call='{self._calls}'></div></body></html>"
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"html": html},
            telemetry={"event": "stub.html"},
        )

    def query_selector(self, selector: str) -> BrowserActionResult:
        exists = self._calls >= self._success_after
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"exists": exists, "response": {"exists": exists, "count": 1 if exists else 0}},
            telemetry={"event": "stub.selector"},
        )


def test_wait_for_analysis_detects_success_and_logs_events() -> None:
    controller = StubController(success_after=2)
    settings = ResumeAnalysisSettings(
        success_selectors=("div.resume-upload-success",),
        working_selectors=(),
        failure_selectors=(),
        max_wait_seconds=2.0,
        poll_interval_ms=50,
    )
    events: list[dict[str, Any]] = []

    def record(event: dict[str, Any]) -> None:
        events.append(event)

    result = wait_for_analysis(controller, settings, telemetry_callback=record)

    assert isinstance(result, ResumeAnalysisResult)
    assert result.status == "ok"
    assert result.reason in {"selector", "dom_stable", "idle"}
    assert any(event["event"] == "RESUME_ANALYSIS_STARTED" for event in events)
    assert any(event["event"] == "RESUME_ANALYSIS_DONE" for event in events)


def test_wait_for_analysis_times_out_when_selector_absent() -> None:
    controller = StubController(success_after=999, idle_ok=False)
    settings = ResumeAnalysisSettings(
        success_selectors=("div.resume-upload-success",),
        working_selectors=(),
        failure_selectors=(),
        max_wait_seconds=0.1,
        poll_interval_ms=50,
    )
    events: list[dict[str, Any]] = []

    def record(event: dict[str, Any]) -> None:
        events.append(event)

    result = wait_for_analysis(controller, settings, telemetry_callback=record)

    assert result.status == "timeout"
    assert any(event["event"] == "RESUME_ANALYSIS_TIMEOUT" for event in events)


def test_load_resume_analysis_settings_falls_back(tmp_path: Path) -> None:
    settings = load_resume_analysis_settings(base=tmp_path)
    assert isinstance(settings, ResumeAnalysisSettings)
    assert settings.success_selectors
