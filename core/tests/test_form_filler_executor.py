from types import SimpleNamespace
import os
import sys

import pytest

pytest.importorskip("portalocker")
pytest.importorskip("yaml")

sys.path.insert(0, os.getcwd())

from apps.browser.controller import BrowserActionResult, BrowserActionStatus
from apps.cli.profiles import ResolvedAnswer
from sites.simplyhired.form_filler import FormFillExecutor
from sites.simplyhired.form_mapper import (
    FormFillPlan,
    FormFillPlanField,
    FormFillPlanStep,
)


class DummyResolver:
    def __init__(self, answers: dict[str, ResolvedAnswer]) -> None:
        self._answers = answers

    def resolve(self, *, profile_field: str, **_: object) -> ResolvedAnswer:
        return self._answers.get(
            profile_field,
            ResolvedAnswer(value=None, status="missing", source=profile_field, reason="missing"),
        )


class DummyController:
    def __init__(self) -> None:
        self.config = SimpleNamespace(profile_id="profile-1")
        self.actions: list[tuple[str, str, object]] = []

    def fill_text(self, selector: str, value: str, *, clear: bool = True) -> BrowserActionResult:
        self.actions.append(("text", selector, value))
        return BrowserActionResult(BrowserActionStatus.OK, {"response": {"ok": True}}, {})

    def set_select_value(self, selector: str, value: str) -> BrowserActionResult:
        self.actions.append(("select", selector, value))
        return BrowserActionResult(BrowserActionStatus.OK, {"response": {"value": value}}, {})

    def set_radio_value(self, selector: str, value: str) -> BrowserActionResult:
        self.actions.append(("radio", selector, value))
        return BrowserActionResult(BrowserActionStatus.ERROR, {"error": "option_missing"}, {})

    def set_checkbox_state(self, selector: str, checked: bool) -> BrowserActionResult:
        self.actions.append(("checkbox", selector, checked))
        return BrowserActionResult(BrowserActionStatus.OK, {"response": {"checked": checked}}, {})

    def get_field_state(self, selector: str, widget_type: str) -> BrowserActionResult:
        if "full" in selector:
            return BrowserActionResult(
                BrowserActionStatus.OK,
                {"state": {"ok": True, "empty": False}},
                {},
            )
        return BrowserActionResult(
            BrowserActionStatus.OK,
            {"state": {"ok": True, "empty": True}},
            {},
        )


def test_executor_fills_and_skips_fields() -> None:
    resolver = DummyResolver(
        {
            "fullName": ResolvedAnswer(value="Alex Example", status="resolved", source="identity"),
            "experienceLevel": ResolvedAnswer(value="Senior", status="resolved", source="qa_override"),
            "relocation": ResolvedAnswer(value="yes", status="resolved", source="qa_override"),
        }
    )
    controller = DummyController()

    plan = FormFillPlan(
        steps=[
            FormFillPlanStep(
                step_id="contact",
                title="Contact",
                mapped=[
                    FormFillPlanField(
                        profile_field="fullName",
                        step="contact",
                        selector="input.full",
                        widget_type="text",
                        required=True,
                        label="Full name",
                        confidence=1.0,
                        options=[],
                        diagnostics={},
                    ),
                    FormFillPlanField(
                        profile_field="experienceLevel",
                        step="contact",
                        selector="select.level",
                        widget_type="select",
                        required=False,
                        label="Experience",
                        confidence=0.9,
                        options=[{"value": "Junior", "label": "Junior"}, {"value": "Senior", "label": "Senior"}],
                        diagnostics={},
                    ),
                    FormFillPlanField(
                        profile_field="workAuthorization",
                        step="contact",
                        selector="input.auth",
                        widget_type="radio",
                        required=True,
                        label="Authorization",
                        confidence=0.8,
                        options=[{"value": "yes", "label": "Yes"}],
                        diagnostics={},
                    ),
                    FormFillPlanField(
                        profile_field="relocation",
                        step="contact",
                        selector="input.relocate",
                        widget_type="checkbox",
                        required=True,
                        label="Relocation",
                        confidence=0.8,
                        options=[],
                        diagnostics={},
                    ),
                ],
                unmapped=[],
            )
        ]
    )

    executor = FormFillExecutor(controller, resolver)
    result = executor.execute(plan, artifact="artifact.html")

    assert result.filled_count() == 3  # radio fails, other three filled
    assert result.skipped_count() == 1
    contact_step = result.steps[0]
    assert any(outcome.profile_field == "workAuthorization" for outcome in contact_step.skipped)
    assert contact_step.issues  # checkbox validation returns empty -> issue recorded
    assert controller.actions[0] == ("text", "input.full", "Alex Example")
    assert controller.actions[1] == ("select", "select.level", "Senior")
    assert controller.actions[-1] == ("checkbox", "input.relocate", True)
