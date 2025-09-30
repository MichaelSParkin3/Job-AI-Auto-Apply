import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path.cwd()))

from apps.browser import BrowserActionResult, BrowserActionStatus  # noqa: E402
from core.autofill.executor import (  # noqa: E402
    AutofillExecutor,
    LeverAutofillField,
    LeverAutofillPlan,
)
from apps.browser import (
    BrowserUseController,
    BrowserLaunchConfig,
    NavigationGuardrails,
)
import types


class StubController:
    def __init__(self) -> None:
        self.focus_calls: list[str] = []
        self.fill_calls: list[tuple[str, str]] = []
        self.wait_calls: int = 0
        self.select_calls: list[tuple[str, str]] = []
        self.checkbox_calls: list[tuple[str, bool]] = []
        self.upload_calls: list[tuple[str, Path]] = []
        self._html_counter = 0
        self.screenshot_calls: list[tuple[str, Path]] = []
        self.fail_selectors: set[str] = set()
        self.screenshot_fail_selectors: set[str] = set()

    def focus(self, selector: str) -> BrowserActionResult:
        self.focus_calls.append(selector)
        return BrowserActionResult(
            status=BrowserActionStatus.OK, details={}, telemetry={}
        )

    def fill_text(self, selector: str, value: str) -> BrowserActionResult:
        self.fill_calls.append((selector, value))
        if selector in self.fail_selectors:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": "fill_failed"},
                telemetry={},
            )
        return BrowserActionResult(
            status=BrowserActionStatus.OK, details={}, telemetry={}
        )

    def wait_for_idle(self, timeout: float | None = None) -> BrowserActionResult:
        self.wait_calls += 1
        return BrowserActionResult(
            status=BrowserActionStatus.OK, details={"timeout": timeout}, telemetry={}
        )

    def get_page_html(self) -> BrowserActionResult:
        self._html_counter += 1
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"html": f"<div data-counter=\"{self._html_counter}\"></div>"},
            telemetry={},
        )

    def set_select_value(self, selector: str, value: str) -> BrowserActionResult:
        self.select_calls.append((selector, value))
        return BrowserActionResult(
            status=BrowserActionStatus.OK, details={}, telemetry={}
        )

    def set_checkbox_state(self, selector: str, checked: bool) -> BrowserActionResult:
        self.checkbox_calls.append((selector, checked))
        return BrowserActionResult(
            status=BrowserActionStatus.OK, details={}, telemetry={}
        )

    def upload_file(
        self,
        *,
        selector: str,
        file_path: Path,
        dry_run: bool = False,
    ) -> BrowserActionResult:
        self.upload_calls.append((selector, file_path))
        details: dict[str, Any] = {"response": {"simulated": dry_run}}
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details=details,
            telemetry={},
        )

    def capture_element_screenshot(
        self, selector: str, output_path: Path
    ) -> BrowserActionResult:
        self.screenshot_calls.append((selector, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if selector in self.screenshot_fail_selectors:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": "capture_failed"},
                telemetry={},
            )
        output_path.write_bytes(b"binary")
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"path": str(output_path)},
            telemetry={},
        )


def _build_plan(field: LeverAutofillField) -> LeverAutofillPlan:
    return LeverAutofillPlan(candidate_id="cand-1", fields=[field])


def test_executor_fills_text_field(tmp_path: Path) -> None:
    controller = StubController()
    events: list[dict[str, Any]] = []

    def record(event: dict[str, Any]) -> None:
        events.append(event)

    executor = AutofillExecutor(
        controller=controller,
        run_dir=tmp_path,
        telemetry_callback=record,
        dry_run=False,
    )
    field = LeverAutofillField(
        key="fullName",
        value_key="fullName",
        label="Full name",
        selector="input#name",
        field_type="text",
        strategy="profile_answer",
    )
    plan = _build_plan(field)
    result = executor.execute(plan, answers={"fullName": "Ada Lovelace"})

    assert controller.focus_calls == ["input#name"]
    assert controller.fill_calls == [("input#name", "Ada Lovelace")]
    assert controller.wait_calls >= 1
    payload = result.to_payload()
    assert payload["filled"] == 1
    assert payload["skipped"] == 0
    assert any(event["event"] == "AUTOFILL_FIELD_FILLED" for event in events)
    screenshot_dir = tmp_path / "autofill" / "screenshots"
    html_dir = tmp_path / "autofill" / "html"
    assert list(screenshot_dir.glob("*.png")), "Expected field screenshot artifact"
    assert sorted(html_dir.glob("*.html")), "Expected before/after HTML artifacts"


def test_executor_skips_missing_answer(tmp_path: Path) -> None:
    controller = StubController()
    events: list[dict[str, Any]] = []

    def record(event: dict[str, Any]) -> None:
        events.append(event)

    executor = AutofillExecutor(
        controller=controller,
        run_dir=tmp_path,
        telemetry_callback=record,
        dry_run=False,
    )
    field = LeverAutofillField(
        key="email",
        value_key="email",
        label="Email",
        selector="input#email",
        field_type="email",
        strategy="profile_answer",
    )
    plan = _build_plan(field)
    result = executor.execute(plan, answers={})

    assert result.to_payload()["skipped"] == 1
    assert any(event["event"] == "AUTOFILL_FIELD_SKIPPED" for event in events)


def test_executor_handles_upload_success(tmp_path: Path) -> None:
    controller = StubController()
    events: list[dict[str, Any]] = []

    def record(event: dict[str, Any]) -> None:
        events.append(event)

    executor = AutofillExecutor(
        controller=controller,
        run_dir=tmp_path,
        telemetry_callback=record,
        dry_run=False,
    )
    field = LeverAutofillField(
        key="resume",
        value_key="resumePath",
        label="Resume",
        selector="input[type=file]",
        field_type="upload",
        strategy="profile_resume",
    )
    plan = _build_plan(field)
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4\n")

    result = executor.execute(plan, answers={"resumePath": resume_path})

    assert controller.upload_calls == [("input[type=file]", resume_path)]
    assert result.to_payload()["filled"] == 1
    assert any(event["event"] == "AUTOFILL_UPLOAD_SUCCESS" for event in events)


def test_executor_emits_skip_telemetry_on_selector_exhaustion(tmp_path: Path) -> None:
    controller = StubController()
    controller.fail_selectors.add("input#name")
    controller.screenshot_fail_selectors.add("input#name-fallback")
    events: list[dict[str, Any]] = []

    def record(event: dict[str, Any]) -> None:
        events.append(event)

    executor = AutofillExecutor(
        controller=controller,
        run_dir=tmp_path,
        telemetry_callback=record,
        dry_run=False,
    )
    field = LeverAutofillField(
        key="fullName",
        value_key="fullName",
        label="Full name",
        selector="input#name",
        field_type="text",
        strategy="profile_answer",
        fallback_selector="input#name-fallback",
    )
    plan = _build_plan(field)
    result = executor.execute(plan, answers={"fullName": "Ada Lovelace"})

    assert controller.fill_calls  # attempted fills
    assert controller.screenshot_calls
    execution = result.fields[0]
    assert execution.status == "skipped"
    assert execution.reason == "screenshot_failed"
    assert execution.value_hash is not None
    assert any(
        event["event"] == "AUTOFILL_FIELD_SKIPPED" and event.get("valueHash")
        for event in events
    )


def test_autofill_blocks_and_emits_guardrail_on_disallowed_domain(tmp_path: Path) -> None:
    """Executor should surface guardrail BLOCKED_DOMAIN and skip when page is off-allowlist."""

    # Collect guardrail telemetry
    guardrail_events: list[dict[str, Any]] = []

    def record_guardrail(event: dict[str, Any]) -> None:
        guardrail_events.append(event)

    # Allowed domains restricted to Lever only
    guardrails = NavigationGuardrails(
        allowed_domains=("jobs.lever.co",),
        wait_jitter_ms=(0, 0),
        think_time_range_s=(0.0, 0.0),
        event_logger=record_guardrail,
    )

    # Stub Browser-Use client reporting an off-domain current URL
    class GuardrailTestClient:
        def __init__(self) -> None:
            self.page = types.SimpleNamespace(url="https://evil.example.com/")

        def focus(self, selector: str, timeout: float | None = None) -> dict:
            return {"ok": True}

        def fill_text(self, selector: str, value: str, *, clear: bool = True) -> dict:
            return {"ok": True}

        def wait_for_idle(self, timeout: float = 5.0) -> dict:
            return {"readyState": "idle"}

        def get_page_content(self) -> str:
            return "<html></html>"

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    launch = BrowserLaunchConfig(
        profile_id="p1",
        user_data_dir=profile_dir,
        model="test-model",
        viewport_width=1200,
        viewport_height=800,
        locale="en-US",
        timezone="America/Los_Angeles",
        guardrail_domains=("jobs.lever.co",),
    )
    controller = BrowserUseController(
        launch,
        client_factory=lambda _cfg: GuardrailTestClient(),
        guardrails=guardrails,
    )

    # Telemetry from executor
    exec_events: list[dict[str, Any]] = []

    def record_exec(event: dict[str, Any]) -> None:
        exec_events.append(event)

    executor = AutofillExecutor(
        controller=controller,
        run_dir=tmp_path,
        telemetry_callback=record_exec,
        dry_run=False,
    )
    field = LeverAutofillField(
        key="fullName",
        value_key="fullName",
        label="Full name",
        selector="input#name",
        field_type="text",
        strategy="profile_answer",
    )
    plan = LeverAutofillPlan(candidate_id="cand-1", fields=[field])
    result = executor.execute(plan, answers={"fullName": "Ada"})

    # The controller should detect off-domain and block the action; executor skips the field
    assert result.fields[0].status == "skipped"
    assert result.fields[0].reason == "blocked_domain"
    # Guardrail event must be present
    assert any(e.get("event") == "guardrail.browser.BLOCKED_DOMAIN" for e in guardrail_events)

