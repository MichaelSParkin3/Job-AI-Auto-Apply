from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from apps.browser import BrowserActionResult, BrowserActionStatus, BrowserUseController
from apps.cli.profiles import ProfileAnswerResolver
from apps.cli.redaction import redact_value
from apps.cli.utils import log_event

from .form_mapper import FormFillPlan, FormFillPlanField, FormFillPlanStep


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _preview_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "checked" if value else "unchecked"
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return ""
    truncated = text[:12]
    if len(text) > 12:
        truncated += "…"
    masked = "".join("•" if ch.isalnum() else ch for ch in truncated)
    return str(redact_value(masked))


@dataclass(slots=True)
class FieldFillOutcome:
    profile_field: str
    step: str
    selector: str
    widget_type: str
    status: str
    value_preview: str | None = None
    reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profileField": self.profile_field,
            "step": self.step,
            "selector": self.selector,
            "widgetType": self.widget_type,
            "status": self.status,
        }
        if self.value_preview is not None:
            payload["valuePreview"] = self.value_preview
        if self.reason:
            payload["reason"] = self.reason
        if self.diagnostics:
            payload["diagnostics"] = dict(self.diagnostics)
        return payload


@dataclass(slots=True)
class StepFillResult:
    step_id: str
    title: str
    filled: list[FieldFillOutcome] = field(default_factory=list)
    skipped: list[FieldFillOutcome] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.step_id,
            "title": self.title,
            "filled": [entry.to_payload() for entry in self.filled],
            "skipped": [entry.to_payload() for entry in self.skipped],
            "issues": [dict(issue) for issue in self.issues],
        }


@dataclass(slots=True)
class FormFillResult:
    artifact: str | None
    profile_id: str | None
    steps: list[StepFillResult]

    def filled_count(self) -> int:
        return sum(len(step.filled) for step in self.steps)

    def skipped_count(self) -> int:
        return sum(len(step.skipped) for step in self.steps)

    def issue_count(self) -> int:
        return sum(len(step.issues) for step in self.steps)

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "profileId": self.profile_id,
            "steps": [step.to_payload() for step in self.steps],
            "summary": {
                "filledFields": self.filled_count(),
                "skippedFields": self.skipped_count(),
                "issues": self.issue_count(),
            },
        }


class FormFillExecutor:
    """Execute a deterministic fill pass against a persisted plan."""

    def __init__(
        self,
        controller: BrowserUseController,
        resolver: ProfileAnswerResolver,
        *,
        max_retries: int = 1,
    ) -> None:
        self._controller = controller
        self._resolver = resolver
        self._max_retries = max(0, max_retries)
        self._profile_id = controller.config.profile_id

    def execute(
        self,
        plan: FormFillPlan,
        *,
        artifact: str | None = None,
    ) -> FormFillResult:
        steps: list[StepFillResult] = []
        for step in plan.steps:
            step_result = self._process_step(step)
            steps.append(step_result)
        log_event(
            {
                "event": "FORM_FILL_COMPLETE",
                "profileId": self._profile_id,
                "artifact": artifact,
                "filled": sum(len(step.filled) for step in steps),
                "skipped": sum(len(step.skipped) for step in steps),
                "issues": sum(len(step.issues) for step in steps),
            }
        )
        return FormFillResult(artifact=artifact, profile_id=self._profile_id, steps=steps)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _process_step(self, step: FormFillPlanStep) -> StepFillResult:
        result = StepFillResult(step_id=step.step_id, title=step.title)
        filled_pairs: list[tuple[FormFillPlanField, FieldFillOutcome]] = []
        for field in step.mapped:
            outcome = self._process_field(step, field)
            if outcome.status == "filled":
                result.filled.append(outcome)
                filled_pairs.append((field, outcome))
            else:
                result.skipped.append(outcome)
        issues = self._validate_fields(filled_pairs)
        if issues:
            result.issues.extend(issues)
        return result

    def _process_field(
        self,
        step: FormFillPlanStep,
        field: FormFillPlanField,
    ) -> FieldFillOutcome:
        resolution = self._resolver.resolve(
            profile_field=field.profile_field,
            label=field.label,
            options=field.options,
            synonyms=self._extract_synonyms(field.diagnostics),
        )
        diagnostics = {
            "confidence": round(field.confidence, 2),
            "required": field.required,
            "source": resolution.source,
        }
        if field.diagnostics:
            diagnostics.update({k: v for k, v in field.diagnostics.items() if k != "confidence"})

        if not resolution.is_resolved or not self._has_value(resolution.value):
            reason = resolution.reason or "profile_missing"
            log_event(
                {
                    "event": "FIELD_SKIPPED",
                    "profileId": self._profile_id,
                    "profileField": field.profile_field,
                    "step": step.step_id,
                    "selector": field.selector,
                    "reason": reason,
                }
            )
            return FieldFillOutcome(
                profile_field=field.profile_field,
                step=step.step_id,
                selector=field.selector,
                widget_type=field.widget_type,
                status="skipped",
                reason=reason,
                diagnostics=diagnostics,
            )

        answer_value = self._stringify(resolution.value)
        target_value, option_meta = self._resolve_option(field, answer_value)
        if option_meta:
            diagnostics.setdefault("option", option_meta)

        log_event(
            {
                "event": "FIELD_FILL_STARTED",
                "profileId": self._profile_id,
                "profileField": field.profile_field,
                "step": step.step_id,
                "selector": field.selector,
                "widgetType": field.widget_type,
            }
        )

        action_result = self._attempt_fill(field, target_value)
        if action_result.status is BrowserActionStatus.ERROR:
            reason = action_result.details.get("error", "interaction_failed")
            log_event(
                {
                    "event": "FIELD_SKIPPED",
                    "profileId": self._profile_id,
                    "profileField": field.profile_field,
                    "step": step.step_id,
                    "selector": field.selector,
                    "reason": reason,
                }
            )
            diagnostics.update(action_result.details)
            return FieldFillOutcome(
                profile_field=field.profile_field,
                step=step.step_id,
                selector=field.selector,
                widget_type=field.widget_type,
                status="skipped",
                reason=reason,
                diagnostics=diagnostics,
            )

        preview = _preview_value(target_value)
        log_event(
            {
                "event": "FIELD_FILLED",
                "profileId": self._profile_id,
                "profileField": field.profile_field,
                "step": step.step_id,
                "selector": field.selector,
                "widgetType": field.widget_type,
                "valuePreview": preview,
            }
        )
        diagnostics.update(action_result.details.get("response", {}))
        return FieldFillOutcome(
            profile_field=field.profile_field,
            step=step.step_id,
            selector=field.selector,
            widget_type=field.widget_type,
            status="filled",
            value_preview=preview,
            diagnostics=diagnostics,
        )

    def _attempt_fill(
        self,
        field: FormFillPlanField,
        value: str,
    ) -> BrowserActionResult:
        attempts = 0
        last_result: BrowserActionResult | None = None
        while attempts <= self._max_retries:
            result = self._dispatch_action(field, value)
            if result.status is BrowserActionStatus.OK:
                return result
            last_result = result
            attempts += 1
            if attempts > self._max_retries:
                break
            log_event(
                {
                    "event": "FIELD_RETRY",
                    "profileId": self._profile_id,
                    "profileField": field.profile_field,
                    "step": field.step,
                    "selector": field.selector,
                    "attempt": attempts,
                }
            )
        return last_result or result

    def _dispatch_action(
        self,
        field: FormFillPlanField,
        value: str,
    ) -> BrowserActionResult:
        widget = field.widget_type.lower()
        if widget in {"text", "textarea"}:
            return self._controller.fill_text(field.selector, value, clear=True)
        if widget == "select":
            return self._controller.set_select_value(field.selector, value)
        if widget == "radio":
            return self._controller.set_radio_value(field.selector, value)
        if widget == "checkbox":
            desired = self._interpret_checkbox(value)
            if desired is None:
                return BrowserActionResult(
                    status=BrowserActionStatus.ERROR,
                    details={"error": "value_unsupported"},
                    telemetry={},
                )
            return self._controller.set_checkbox_state(field.selector, desired)
        return BrowserActionResult(
            status=BrowserActionStatus.ERROR,
            details={"error": "unsupported_widget"},
            telemetry={},
        )

    def _validate_fields(
        self, field_results: Sequence[tuple[FormFillPlanField, FieldFillOutcome]]
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for field, outcome in field_results:
            if not field.required:
                continue
            state_result = self._controller.get_field_state(field.selector, field.widget_type)
            if state_result.status is BrowserActionStatus.ERROR:
                issues.append(
                    {
                        "profileField": field.profile_field,
                        "step": field.step,
                        "reason": "validation_failed",
                        "details": state_result.details,
                    }
                )
                continue
            state = state_result.details.get("state", {})
            if isinstance(state, Mapping):
                empty = bool(state.get("empty"))
                checked = state.get("checked")
                if field.widget_type.lower() == "checkbox":
                    empty = not bool(checked)
                elif field.widget_type.lower() == "radio":
                    empty = not bool(checked)
                if empty:
                    issue = {
                        "profileField": field.profile_field,
                        "step": field.step,
                        "reason": "empty_required",
                        "state": dict(state),
                    }
                    issues.append(issue)
                    log_event(
                        {
                            "level": "warning",
                            "event": "FIELD_VALIDATION_FAILED",
                            "profileId": self._profile_id,
                            "profileField": field.profile_field,
                            "step": field.step,
                            "selector": field.selector,
                            "details": issue,
                        }
                    )
        return issues

    @staticmethod
    def _extract_synonyms(diagnostics: Mapping[str, Any]) -> Iterable[str]:
        synonyms = diagnostics.get("synonyms") if isinstance(diagnostics, Mapping) else None
        if isinstance(synonyms, Sequence):
            return [str(value) for value in synonyms if str(value).strip()]
        return []

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)

    @staticmethod
    def _interpret_checkbox(value: str) -> bool | None:
        normalized = value.strip().casefold()
        if normalized in {"yes", "true", "1", "checked", "y"}:
            return True
        if normalized in {"no", "false", "0", "unchecked", "n"}:
            return False
        return None

    def _resolve_option(
        self,
        field: FormFillPlanField,
        answer_value: str,
    ) -> tuple[str, Mapping[str, Any] | None]:
        options = field.options or []
        if not options:
            return answer_value, None
        normalized_answer = _normalize_token(answer_value)
        for option in options:
            label = option.get("label")
            value = option.get("value")
            if _normalize_token(value) == normalized_answer:
                return value or answer_value, option
            if _normalize_token(label) == normalized_answer:
                return option.get("value") or label or answer_value, option
        for option in options:
            label = option.get("label")
            if label and normalized_answer and normalized_answer in _normalize_token(label):
                return option.get("value") or label or answer_value, option
        return answer_value, None
