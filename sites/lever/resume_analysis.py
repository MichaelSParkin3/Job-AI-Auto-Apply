"""Helpers for waiting on Lever resume analysis states."""

from __future__ import annotations

import hashlib
import hashlib
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

try:  # pragma: no cover - dependency optional in some environments
    import yaml
except ModuleNotFoundError:  # pragma: no cover - graceful fallback when PyYAML missing
    yaml = None  # type: ignore[assignment]

from apps.browser import BrowserActionResult, BrowserActionStatus, BrowserUseController
from apps.cli.utils import log_event


@dataclass(slots=True)
class ResumeAnalysisSettings:
    """Configuration controlling resume analysis polling behaviour."""

    success_selectors: Sequence[str] = field(default_factory=tuple)
    working_selectors: Sequence[str] = field(default_factory=tuple)
    failure_selectors: Sequence[str] = field(default_factory=tuple)
    max_wait_seconds: float = 15.0
    # Only allow DOM-stability fallback after at least this many seconds
    # (does not delay explicit success/failure selectors)
    min_wait_seconds: float = 3.0
    poll_interval_ms: int = 300


@dataclass(slots=True)
class ResumeAnalysisResult:
    """Outcome of waiting for Lever's resume analysis to stabilise."""

    status: str
    waited_ms: int
    reason: str
    selector: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "waitedMs": self.waited_ms,
            "reason": self.reason,
        }
        if self.selector:
            payload["selector"] = self.selector
        return payload

    def telemetry_payload(self) -> dict[str, object]:
        payload = {
            "status": self.status,
            "waitedMs": self.waited_ms,
            "reason": self.reason,
        }
        if self.selector:
            payload["selector"] = self.selector
        return payload


_DEFAULT_SETTINGS = ResumeAnalysisSettings(
    success_selectors=(
        "span.resume-upload-success",
        "div.resume-upload-success",
        "input#resume-upload-input.application-file-input[value]",
    ),
    working_selectors=(
        "div.resume-upload-spinner",
        "div.resume-upload-progress",
    ),
    failure_selectors=(
        "div.resume-upload-error",
        "div.resume-upload-failure",
    ),
    max_wait_seconds=15.0,
    min_wait_seconds=3.0,
    poll_interval_ms=300,
)


def load_resume_analysis_settings(base: Path | None = None) -> ResumeAnalysisSettings:
    """Return resume analysis settings loaded from sites/lever/config.yaml."""

    base = base or Path.cwd()
    config_path = base / "sites" / "lever" / "config.yaml"
    if not config_path.exists():
        return _DEFAULT_SETTINGS
    if yaml is None:
        return _DEFAULT_SETTINGS
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return _DEFAULT_SETTINGS
    resume_data: Mapping[str, object] | None = None
    if isinstance(data, Mapping):
        raw_resume = data.get("resume")
        if isinstance(raw_resume, Mapping):
            resume_data = raw_resume
    if resume_data is None:
        return _DEFAULT_SETTINGS
    success = _extract_selector_list(resume_data, "success_selectors") or _DEFAULT_SETTINGS.success_selectors
    working = _extract_selector_list(resume_data, "working_selectors") or _DEFAULT_SETTINGS.working_selectors
    failure = _extract_selector_list(resume_data, "failure_selectors") or _DEFAULT_SETTINGS.failure_selectors
    max_wait = _coerce_number(resume_data.get("max_wait_seconds"), default=_DEFAULT_SETTINGS.max_wait_seconds)
    min_wait = _coerce_number(resume_data.get("min_wait_seconds"), default=_DEFAULT_SETTINGS.min_wait_seconds)
    poll_interval = int(
        _coerce_number(resume_data.get("poll_interval_ms"), default=_DEFAULT_SETTINGS.poll_interval_ms)
    )
    return ResumeAnalysisSettings(
        success_selectors=tuple(success),
        working_selectors=tuple(working),
        failure_selectors=tuple(failure),
        max_wait_seconds=float(max_wait),
        min_wait_seconds=float(min_wait),
        poll_interval_ms=max(50, poll_interval),
    )


def wait_for_analysis(
    controller: BrowserUseController,
    settings: ResumeAnalysisSettings,
    *,
    telemetry_callback: Callable[[dict[str, object]], None] | None = None,
) -> ResumeAnalysisResult:
    """Block until resume analysis signals readiness or a timeout occurs."""

    telemetry = telemetry_callback or log_event
    selectors_payload = {
        "success": list(settings.success_selectors),
        "working": list(settings.working_selectors),
        "failure": list(settings.failure_selectors),
    }
    telemetry(
        {
            "event": "RESUME_ANALYSIS_STARTED",
            "selectors": selectors_payload,
            "timeoutMs": int(settings.max_wait_seconds * 1000),
            "pollIntervalMs": settings.poll_interval_ms,
        }
    )
    start = time.monotonic()
    last_hash: str | None = None
    stable_since: float | None = None
    seen_working: set[str] = set()
    poll_interval = max(settings.poll_interval_ms / 1000.0, 0.05)
    wait_jitter = getattr(controller.config, "wait_jitter_ms", (0, 0))
    timeout_at = start + settings.max_wait_seconds

    while time.monotonic() < timeout_at:
        idle = controller.wait_for_idle(timeout=min(settings.max_wait_seconds, 3.0))
        idle_ok = idle.status is BrowserActionStatus.OK

        failure_selector = _check_selectors(controller, settings.failure_selectors, require_visible=True)
        if failure_selector:
            duration_ms = int((time.monotonic() - start) * 1000)
            telemetry(
                {
                    "event": "RESUME_ANALYSIS_DONE",
                    "status": "failed",
                    "reason": "failure_selector",
                    "selector": failure_selector,
                    "durationMs": duration_ms,
                }
            )
            return ResumeAnalysisResult(
                status="failed",
                waited_ms=duration_ms,
                reason="failure_selector",
                selector=failure_selector,
            )

        success_selector = _check_selectors(controller, settings.success_selectors, require_visible=True)
        if success_selector:
            duration_ms = int((time.monotonic() - start) * 1000)
            telemetry(
                {
                    "event": "RESUME_ANALYSIS_DONE",
                    "status": "ok",
                    "reason": "selector",
                    "selector": success_selector,
                    "durationMs": duration_ms,
                }
            )
            return ResumeAnalysisResult(
                status="ok",
                waited_ms=duration_ms,
                reason="selector",
                selector=success_selector,
            )

        working_visible_now = False
        for selector in settings.working_selectors:
            if selector in seen_working:
                continue
            if _query_exists(controller, selector, visible=True):
                seen_working.add(selector)
                working_visible_now = True
                telemetry(
                    {
                        "event": "RESUME_ANALYSIS_PROGRESS",
                        "selector": selector,
                        "elapsedMs": int((time.monotonic() - start) * 1000),
                    }
                )
        # Also consider currently-visible working selectors (even if previously seen)
        if not working_visible_now:
            # Check again across the list to detect ongoing progress visibility
            for selector in settings.working_selectors:
                if _query_exists(controller, selector, visible=True):
                    working_visible_now = True
                    break

        html_result = controller.get_page_html()
        if html_result.status is BrowserActionStatus.OK:
            html = html_result.details.get("html")
            if isinstance(html, str) and html:
                digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
                if digest == last_hash:
                    if stable_since is None:
                        stable_since = time.monotonic()
                    elif time.monotonic() - stable_since >= poll_interval:
                        # Only allow DOM-stable fallback if:
                        #  - minimum wait window elapsed, and
                        #  - no working indicators are currently visible
                        if (
                            (time.monotonic() - start) >= settings.min_wait_seconds
                            and not working_visible_now
                        ):
                            duration_ms = int((time.monotonic() - start) * 1000)
                            telemetry(
                                {
                                    "event": "RESUME_ANALYSIS_DONE",
                                    "status": "ok",
                                    "reason": "dom_stable",
                                    "durationMs": duration_ms,
                                }
                            )
                            return ResumeAnalysisResult(
                                status="ok",
                                waited_ms=duration_ms,
                                reason="dom_stable",
                            )
                else:
                    last_hash = digest
                    stable_since = None

        # Treat network-idle as completion only after we've observed analysis activity
        # (i.e., a working selector showed up). This avoids immediately exiting on
        # static forms where Browser-Use reports idle even though analysis hasn't run.
        if idle_ok and len(seen_working) > 0 and not working_visible_now and (time.monotonic() - start) >= settings.min_wait_seconds:
            duration_ms = int((time.monotonic() - start) * 1000)
            telemetry(
                {
                    "event": "RESUME_ANALYSIS_DONE",
                    "status": "ok",
                    "reason": "idle",
                    "durationMs": duration_ms,
                }
            )
            return ResumeAnalysisResult(
                status="ok",
                waited_ms=duration_ms,
                reason="idle",
            )

        sleep_seconds = poll_interval
        if isinstance(wait_jitter, Iterable):
            jitter_values = list(wait_jitter)
            if len(jitter_values) == 2:
                low, high = jitter_values
                if isinstance(low, (int, float)) and isinstance(high, (int, float)) and high >= low:
                    sleep_seconds += random.uniform(float(low), float(high)) / 1000.0
        time.sleep(min(sleep_seconds, max(0.05, timeout_at - time.monotonic())))

    waited_ms = int((time.monotonic() - start) * 1000)
    telemetry(
        {
            "event": "RESUME_ANALYSIS_TIMEOUT",
            "waitedMs": waited_ms,
            "selectors": selectors_payload,
        }
    )
    return ResumeAnalysisResult(status="timeout", waited_ms=waited_ms, reason="timeout")


def _extract_selector_list(data: Mapping[str, object], key: str) -> list[str]:
    value = data.get(key)
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        selectors: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                selectors.append(item)
        return selectors
    return []


def _coerce_number(value: object, *, default: float) -> float:
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            return float(value.strip())
    except (TypeError, ValueError):
        return float(default)
    return float(default)


def _query_exists(controller: BrowserUseController, selector: str, *, visible: bool) -> bool:
    if visible:
        query = getattr(controller, "query_selector_visible", None)
        if callable(query):
            result = query(selector)
            if result.status is BrowserActionStatus.OK:
                response = result.details.get("response")
                if isinstance(response, Mapping):
                    vis = response.get("visible")
                    if isinstance(vis, bool):
                        return vis
                return _selector_exists(result)
    result = controller.query_selector(selector)
    return result.status is BrowserActionStatus.OK and _selector_exists(result)


def _check_selectors(
    controller: BrowserUseController, selectors: Sequence[str], *, require_visible: bool = False
) -> str | None:
    for selector in selectors:
        if _query_exists(controller, selector, visible=require_visible):
            return selector
    return None


def _selector_exists(result: BrowserActionResult) -> bool:
    response = result.details.get("response")
    if isinstance(response, Mapping):
        exists = response.get("exists")
        if isinstance(exists, bool):
            return exists
        if isinstance(exists, (int, float)):
            return bool(exists)
    exists_flag = result.details.get("exists")
    if isinstance(exists_flag, bool):
        return exists_flag
    if isinstance(exists_flag, (int, float)):
        return bool(exists_flag)
    return False


__all__ = [
    "ResumeAnalysisResult",
    "ResumeAnalysisSettings",
    "load_resume_analysis_settings",
    "wait_for_analysis",
]
