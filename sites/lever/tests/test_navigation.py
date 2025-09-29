import os
import sys

sys.path.insert(0, os.getcwd())

from apps.browser import BrowserActionResult, BrowserActionStatus
from sites.lever.lever_google_discovery import LeverSerpResult
from sites.lever.navigation import LeverNavigator


class StubController:
    def __init__(
        self,
        *,
        html_sequence: list[str],
        url_sequence: list[str],
        click_status: BrowserActionStatus = BrowserActionStatus.OK,
    ) -> None:
        self.html_sequence = html_sequence
        self.url_sequence = url_sequence
        self.click_status = click_status
        self.open_calls: list[str] = []
        self.safe_click_calls: list[str] = []
        self.wait_calls: list[float] = []
        self._html_index = 0
        self._url_index = 0

    def open_url(self, url: str) -> BrowserActionResult:
        self.open_calls.append(url)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": {"opened": url}},
            telemetry={},
        )

    def wait_for_idle(self, timeout: float = 5.0) -> BrowserActionResult:
        self.wait_calls.append(timeout)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"timeout": timeout},
            telemetry={},
        )

    def get_page_html(self) -> BrowserActionResult:
        index = min(self._html_index, len(self.html_sequence) - 1)
        html = self.html_sequence[index]
        self._html_index += 1
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"html": html},
            telemetry={},
        )

    def safe_click(self, selector: str, timeout: float | None = None) -> BrowserActionResult:
        self.safe_click_calls.append(selector)
        if self.click_status is BrowserActionStatus.OK:
            return BrowserActionResult(
                status=BrowserActionStatus.OK,
                details={"response": {"selector": selector}},
                telemetry={},
            )
        return BrowserActionResult(
            status=self.click_status,
            details={"error": "click_failed"},
            telemetry={},
        )

    def get_current_url(self) -> BrowserActionResult:
        index = min(self._url_index, len(self.url_sequence) - 1)
        url = self.url_sequence[index]
        self._url_index += 1
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"url": url},
            telemetry={},
        )


def test_navigator_direct_apply_success():
    controller = StubController(
        html_sequence=["<form id='application-form'></form>"],
        url_sequence=["https://jobs.lever.co/acme/front-end/apply"],
    )
    navigator = LeverNavigator(controller)  # type: ignore[arg-type]
    result = LeverSerpResult(
        title="Front End Engineer",
        href="https://jobs.lever.co/acme/front-end/apply",
        mode="apply_direct",
    )

    outcome = navigator.open_result(result)

    assert outcome.status == "ok"
    assert outcome.apply_url == "https://jobs.lever.co/acme/front-end/apply"
    assert outcome.landing_url == "https://jobs.lever.co/acme/front-end/apply"
    assert controller.open_calls == ["https://jobs.lever.co/acme/front-end/apply"]


def test_navigator_job_page_clicks_apply() -> None:
    job_html = (
        "<div class='posting-headline'><h2>Role</h2></div>"
        "<a class='postings-btn template-btn-submit' href='/acme/role/apply'>Apply</a>"
    )
    apply_html = "<form id='application-form'><button id='btn-submit' data-qa='btn-submit'></button></form>"
    controller = StubController(
        html_sequence=[job_html, apply_html],
        url_sequence=[
            "https://jobs.lever.co/acme/role",
            "https://jobs.lever.co/acme/role/apply",
        ],
    )
    navigator = LeverNavigator(controller)  # type: ignore[arg-type]
    result = LeverSerpResult(
        title="Front End Engineer",
        href="https://jobs.lever.co/acme/role",
        mode="job_page",
    )

    outcome = navigator.open_result(result)

    assert outcome.status == "ok"
    assert outcome.apply_url == "https://jobs.lever.co/acme/role/apply"
    assert controller.safe_click_calls == ["a.postings-btn.template-btn-submit[href*='/apply']"]


def test_navigator_job_page_fallback_to_open() -> None:
    job_html = "<a class='postings-btn template-btn-submit' href='/acme/role/apply'>Apply</a>"
    apply_html = "<form id='application-form'></form>"
    controller = StubController(
        html_sequence=[job_html, apply_html],
        url_sequence=[
            "https://jobs.lever.co/acme/role",
            "https://jobs.lever.co/acme/role/apply",
        ],
        click_status=BrowserActionStatus.ERROR,
    )
    navigator = LeverNavigator(controller)  # type: ignore[arg-type]
    result = LeverSerpResult(
        title="Front End Engineer",
        href="https://jobs.lever.co/acme/role",
        mode="job_page",
    )

    outcome = navigator.open_result(result)

    assert outcome.status == "ok"
    assert outcome.apply_url == "https://jobs.lever.co/acme/role/apply"
    assert controller.open_calls.count("https://jobs.lever.co/acme/role/apply") == 1


def test_navigator_missing_apply_link() -> None:
    controller = StubController(
        html_sequence=["<div class='posting-headline'><h2>Role</h2></div>"],
        url_sequence=["https://jobs.lever.co/acme/role"],
    )
    navigator = LeverNavigator(controller)  # type: ignore[arg-type]
    result = LeverSerpResult(
        title="Front End Engineer",
        href="https://jobs.lever.co/acme/role",
        mode="job_page",
    )

    outcome = navigator.open_result(result)

    assert outcome.status == "apply_link_missing"
