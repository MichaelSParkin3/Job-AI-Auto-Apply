"""Execute Lever autofill plans using Browser-Use primitives."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from apps.browser import BrowserActionResult, BrowserActionStatus, BrowserUseController
from apps.cli.redaction import redact_value


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return bool(value)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Sequence, set)) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) > 0
    return True


def _value_length(value: Any) -> int:
    if isinstance(value, (list, tuple, set)):
        return sum(_value_length(item) for item in value)
    return len(str(value))


def _value_hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _preview_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        preview = "checked" if value else "unchecked"
    elif isinstance(value, (list, tuple, set)):
        preview = ", ".join(str(item) for item in value)
    else:
        preview = str(value)
    preview = preview.strip()
    if not preview:
        return None
    truncated = preview[:12]
    if len(preview) > 12:
        truncated += "…"
    masked = "".join("•" if ch.isalnum() else ch for ch in truncated)
    return str(redact_value(masked))


@dataclass(slots=True)
class LeverAutofillField:
    """Normalized field definition derived from planner intents."""

    key: str
    value_key: str
    label: str
    selector: str
    field_type: str
    strategy: str
    fallback_selector: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LeverAutofillPlan:
    """Executable Lever autofill plan."""

    candidate_id: str
    fields: Sequence[LeverAutofillField]
    resume_selector: str | None = None
    llm_used: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FieldArtifact:
    """Artifact bundle captured for a single field execution."""

    key: str
    screenshot_path: Path | None
    before_html: Path | None
    after_html: Path | None

    def to_payload(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.screenshot_path is not None:
            payload["screenshot"] = str(self.screenshot_path)
        if self.before_html is not None:
            payload["beforeHtml"] = str(self.before_html)
        if self.after_html is not None:
            payload["afterHtml"] = str(self.after_html)
        return payload


@dataclass(slots=True)
class FieldExecution:
    """Outcome of executing a single field intent."""

    key: str
    selector: str
    status: str
    reason: str | None
    value_preview: str | None
    value_length: int | None
    value_hash: str | None
    artifacts: FieldArtifact | None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "selector": self.selector,
            "status": self.status,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.value_preview is not None:
            payload["valuePreview"] = self.value_preview
        if self.value_length is not None:
            payload["valueLength"] = self.value_length
        if self.value_hash is not None:
            payload["valueHash"] = self.value_hash
        if self.artifacts is not None:
            artifacts_payload = self.artifacts.to_payload()
            if artifacts_payload:
                payload["artifacts"] = artifacts_payload
        return payload


@dataclass(slots=True)
class AutofillExecutionResult:
    """Aggregate execution summary for an autofill plan."""

    candidate_id: str
    fields: Sequence[FieldExecution]

    def filled(self) -> int:
        return sum(1 for field in self.fields if field.status == "filled")

    def skipped(self) -> int:
        return sum(1 for field in self.fields if field.status != "filled")

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "filled": self.filled(),
            "skipped": self.skipped(),
            "fields": [field.to_payload() for field in self.fields],
        }


class AutofillExecutor:
    """Replay Lever autofill intents against Browser-Use primitives."""

    def __init__(
        self,
        *,
        controller: BrowserUseController,
        run_dir: Path,
        telemetry_callback,
        dry_run: bool,
    ) -> None:
        self._controller = controller
        self._telemetry = telemetry_callback
        self._dry_run = dry_run
        self._root = Path(run_dir) / "autofill"
        self._root.mkdir(parents=True, exist_ok=True)
        self._screenshots_dir = self._root / "screenshots"
        self._screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._html_dir = self._root / "html"
        self._html_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        plan: LeverAutofillPlan,
        *,
        answers: Mapping[str, Any],
        validate_prefilled: bool = False,
    ) -> AutofillExecutionResult:
        answers_map: MutableMapping[str, Any] = dict(answers)
        skip_lengths: dict[str, int] = {}
        if validate_prefilled:
            answers_map, skip_lengths = self._apply_prefilled_validations(plan, answers_map)

        fields: list[FieldExecution] = []
        for intent in plan.fields:
            if intent.value_key in skip_lengths:
                fields.append(
                    self._skip_field(
                        plan,
                        intent,
                        reason="prefilled",
                        value_length=skip_lengths[intent.value_key],
                    )
                )
                continue

            value = answers_map.get(intent.value_key)
            if not _has_value(value):
                fields.append(
                    self._skip_field(plan, intent, reason="missing_answer")
                )
                continue
            if self._dry_run:
                fields.append(
                    self._skip_field(
                        plan,
                        intent,
                        reason="dry_run",
                        value=value,
                    )
                )
                continue
            execution = self._execute_field(plan, intent, value)
            fields.append(execution)
        return AutofillExecutionResult(candidate_id=plan.candidate_id, fields=fields)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _skip_field(
        self,
        plan: LeverAutofillPlan,
        field: LeverAutofillField,
        *,
        reason: str,
        selector: str | None = None,
        value: Any | None = None,
        value_length: int | None = None,
        value_preview: str | None = None,
        value_hash: str | None = None,
    ) -> FieldExecution:
        selector = selector or field.selector
        payload: dict[str, Any] = {
            "event": "AUTOFILL_FIELD_SKIPPED",
            "candidateId": plan.candidate_id,
            "fieldKey": field.key,
            "selector": selector,
            "reason": reason,
            "strategy": field.strategy,
        }
        preview: str | None = None
        length: int | None = None
        hashed: str | None = None
        if value is not None:
            preview = _preview_value(value)
            length = _value_length(value)
            hashed = _value_hash(value)
        else:
            preview = value_preview
            length = value_length
            hashed = value_hash
        if length is not None:
            payload["valueLength"] = length
        if hashed is not None:
            payload["valueHash"] = hashed
        if preview is not None:
            payload["valuePreview"] = preview
        self._telemetry(payload)
        return FieldExecution(
            key=field.key,
            selector=selector,
            status="skipped",
            reason=reason,
            value_preview=preview,
            value_length=length,
            value_hash=hashed,
            artifacts=None,
        )

    def _execute_field(
        self,
        plan: LeverAutofillPlan,
        field: LeverAutofillField,
        value: Any,
    ) -> FieldExecution:
        selectors: Iterable[str] = self._selector_chain(field)
        last_error: str | None = None
        last_selector: str | None = None
        for selector in selectors:
            last_selector = selector
            artifacts, error = self._execute_with_selector(plan, field, selector, value)
            if artifacts is not None:
                preview = _preview_value(value)
                length = _value_length(value)
                hashed = _value_hash(value)
                telemetry = {
                    "event": "AUTOFILL_FIELD_FILLED",
                    "candidateId": plan.candidate_id,
                    "fieldKey": field.key,
                    "selector": selector,
                    "strategy": field.strategy,
                    "valueLength": length,
                    "valueHash": hashed,
                }
                if preview is not None:
                    telemetry["valuePreview"] = preview
                self._telemetry(telemetry)
                return FieldExecution(
                    key=field.key,
                    selector=selector,
                    status="filled",
                    reason=None,
                    value_preview=preview,
                    value_length=length,
                    value_hash=hashed,
                    artifacts=artifacts,
                )
            if error:
                last_error = error
            elif last_error is None:
                last_error = "selector_failed"
        return self._skip_field(
            plan,
            field,
            reason=last_error or "selector_failed",
            selector=last_selector,
            value=value,
        )

    def _selector_chain(self, field: LeverAutofillField) -> Iterable[str]:
        selectors = [field.selector]
        fallback = field.fallback_selector
        if fallback:
            fallbacks: list[str] = []
            if isinstance(fallback, str):
                fallbacks = [fallback]
            elif isinstance(fallback, Sequence):
                fallbacks = [str(item) for item in fallback]
            selectors.extend(item for item in fallbacks if item and item not in selectors)
        return selectors

    def _execute_with_selector(
        self,
        plan: LeverAutofillPlan,
        field: LeverAutofillField,
        selector: str,
        value: Any,
    ) -> tuple[FieldArtifact | None, str | None]:
        before_html = self._capture_html(plan, field, selector, suffix="before")
        action = self._dispatch_action(plan, field, selector, value)
        if action.status is not BrowserActionStatus.OK:
            error_detail = str(action.details.get("error") or action.status.value)
            return None, error_detail
        self._controller.wait_for_idle()
        after_html = self._capture_html(plan, field, selector, suffix="after")
        screenshot = self._capture_screenshot(plan, field, selector)
        if screenshot is None:
            return None, "screenshot_failed"
        artifact = FieldArtifact(
            key=field.key,
            screenshot_path=screenshot,
            before_html=before_html,
            after_html=after_html,
        )
        return artifact, None

    def _apply_prefilled_validations(
        self,
        plan: LeverAutofillPlan,
        answers: MutableMapping[str, Any],
    ) -> tuple[MutableMapping[str, Any], dict[str, int]]:
        skip_lengths: dict[str, int] = {}
        outcomes: list[dict[str, Any]] = []
        for field in plan.fields:
            if not self._should_validate_field(field):
                continue
            widget_type = self._field_widget_type(field)
            state_result = self._controller.get_field_state(field.selector, widget_type)
            dom_value = ""
            dom_length = 0
            if state_result.status is BrowserActionStatus.OK:
                state_payload = state_result.details.get("state")
                if isinstance(state_payload, Mapping):
                    dom_value = self._extract_state_value(state_payload, widget_type)
                    dom_length = len(dom_value)
            if dom_value and self._is_value_valid(field, dom_value):
                skip_lengths[field.value_key] = dom_length
                outcomes.append(
                    {
                        "key": field.value_key,
                        "status": "ok",
                        "source": "dom",
                        "valueLength": dom_length,
                    }
                )
                continue
            profile_value = answers.get(field.value_key)
            if _has_value(profile_value) and self._is_value_valid(field, profile_value):
                answers[field.value_key] = profile_value
                outcomes.append(
                    {
                        "key": field.value_key,
                        "status": "updated",
                        "source": "profile",
                        "valueLength": _value_length(profile_value),
                    }
                )
                continue
            outcomes.append(
                {
                    "key": field.value_key,
                    "status": "failed",
                    "source": "resume",
                    "valueLength": dom_length,
                }
            )
            self._telemetry(
                {
                    "event": "RESUME_FIELD_VALIDATION_FAILED",
                    "candidateId": plan.candidate_id,
                    "fieldKey": field.value_key,
                    "valueLength": dom_length,
                }
            )
        if outcomes:
            self._telemetry(
                {
                    "event": "RESUME_FIELDS_VALIDATED",
                    "candidateId": plan.candidate_id,
                    "fields": outcomes,
                }
            )
        return answers, skip_lengths

    @staticmethod
    def _field_widget_type(field: LeverAutofillField) -> str:
        field_type = (field.field_type or "text").strip().lower()
        if field_type in {"select", "dropdown"}:
            return "select"
        if field_type in {"radio", "option"}:
            return "radio"
        if field_type in {"checkbox"}:
            return "checkbox"
        return "text"

    def _extract_state_value(
        self, state: Mapping[str, Any], widget_type: str
    ) -> str:
        if widget_type in {"text", "textarea"}:
            value = state.get("value")
            return str(value or "").strip()
        if widget_type == "select":
            value = state.get("value") or state.get("label")
            return str(value or "").strip()
        if widget_type == "radio":
            value = state.get("value") or state.get("label")
            return str(value or "").strip()
        if widget_type == "checkbox":
            return "true" if state.get("checked") else ""
        return str(state.get("value") or "").strip()

    def _should_validate_field(self, field: LeverAutofillField) -> bool:
        key = field.value_key.lower()
        if key in {
            "fullname",
            "full_name",
            "firstname",
            "first_name",
            "lastname",
            "last_name",
            "email",
            "phone",
            "phone_number",
        }:
            return True
        if any(token in key for token in ("linkedin", "github", "portfolio", "url", "website", "link")):
            return True
        return False

    def _is_value_valid(self, field: LeverAutofillField, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        key = field.value_key.lower()
        field_type = (field.field_type or "text").strip().lower()
        if key in {"fullname", "full_name"}:
            return len(text) >= 3 and " " in text
        if key in {"firstname", "first_name", "lastname", "last_name"}:
            return len(text) >= 2
        if "email" in key or field_type == "email":
            return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text))
        if "phone" in key or field_type in {"tel", "phone"}:
            digits = re.sub(r"\D", "", text)
            return len(digits) >= 10
        if any(token in key for token in ("linkedin", "github", "portfolio", "url", "website", "link")):
            return self._looks_like_url(text)
        return True

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        lowered = value.lower()
        if lowered.startswith(("http://", "https://", "www.")):
            return True
        if "." in lowered and " " not in lowered:
            return True
        return False

    def _dispatch_action(
        self,
        plan: LeverAutofillPlan,
        field: LeverAutofillField,
        selector: str,
        value: Any,
    ) -> BrowserActionResult:
        field_type = field.field_type.lower().strip()
        if field_type in {"select", "dropdown"}:
            return self._controller.set_select_value(selector, str(value))
        if field_type in {"radio", "option"}:
            return self._controller.set_radio_value(selector, str(value))
        if field_type in {"checkbox"}:
            return self._controller.set_checkbox_state(selector, _normalize_bool(value))
        if field_type in {"file", "upload", "resume"}:
            file_path = Path(str(value))
            result = self._controller.upload_file(
                selector=selector,
                file_path=file_path,
                dry_run=self._dry_run,
            )
            if result.status is BrowserActionStatus.OK:
                payload: MutableMapping[str, Any] = {
                    "event": "AUTOFILL_UPLOAD_SUCCESS",
                    "candidateId": plan.candidate_id,
                    "selector": selector,
                }
                self._telemetry(payload)
            else:
                self._telemetry(
                    {
                        "event": "AUTOFILL_UPLOAD_FAILURE",
                        "candidateId": plan.candidate_id,
                        "selector": selector,
                        "error": result.details.get("error"),
                    }
                )
            return result
        # Default to focus + fill text for text-like fields.
        self._controller.focus(selector)
        return self._controller.fill_text(selector, str(value))

    def _artifact_stem(
        self, plan: LeverAutofillPlan, field: LeverAutofillField, selector: str
    ) -> str:
        digest = hashlib.sha256()
        digest.update(plan.candidate_id.encode("utf-8"))
        digest.update(b"|")
        digest.update(field.key.encode("utf-8"))
        digest.update(b"|")
        digest.update(selector.encode("utf-8"))
        return digest.hexdigest()

    def _capture_html(
        self,
        plan: LeverAutofillPlan,
        field: LeverAutofillField,
        selector: str,
        *,
        suffix: str,
    ) -> Path | None:
        result = self._controller.get_page_html()
        if result.status is not BrowserActionStatus.OK:
            return None
        html = result.details.get("html")
        if not html:
            return None
        path = self._html_dir / f"{self._artifact_stem(plan, field, selector)}.{suffix}.html"
        path.write_text(str(html), encoding="utf-8")
        return path

    def _capture_screenshot(
        self,
        plan: LeverAutofillPlan,
        field: LeverAutofillField,
        selector: str,
    ) -> Path | None:
        filename = f"{self._artifact_stem(plan, field, selector)}.png"
        path = self._screenshots_dir / filename
        result = self._controller.capture_element_screenshot(selector, path)
        if result.status is not BrowserActionStatus.OK:
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            return None
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size <= 0:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        return path


__all__ = [
    "AutofillExecutor",
    "AutofillExecutionResult",
    "LeverAutofillField",
    "LeverAutofillPlan",
]

