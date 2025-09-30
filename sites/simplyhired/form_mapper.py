from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

try:  # pragma: no cover - exercised when bs4 is unavailable
    from bs4 import BeautifulSoup, Tag
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    class Tag:  # type: ignore[override]
        pass

    class BeautifulSoup:  # type: ignore[override]
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def select(self, *_args, **_kwargs) -> list[Tag]:
            return []

        def find_all(self, *_args, **_kwargs) -> list[Tag]:
            return []


_MIN_CONFIDENCE = 0.55


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.strip().casefold()
    text = re.sub(r"[\s]+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_mapping(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge_mapping(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


@dataclass(slots=True)
class FormFieldSelectorConfig:
    """Represents selector metadata for a specific profile field."""

    profile_field: str
    label: str
    synonyms: tuple[str, ...]
    selectors: tuple[str, ...]
    widget_type: str
    required: bool
    value_attribute: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "FormFieldSelectorConfig":
        profile_field = str(data.get("profileField", "")).strip()
        if not profile_field:
            raise ValueError("profileField is required")
        selectors_raw = data.get("selectors")
        if isinstance(selectors_raw, str):
            selectors = [selectors_raw]
        elif isinstance(selectors_raw, Sequence):
            selectors = [str(item) for item in selectors_raw if str(item).strip()]
        else:
            selectors = []
        selectors = [item.strip() for item in selectors if item and item.strip()]
        if not selectors:
            raise ValueError(f"selectors must be provided for {profile_field}")
        synonyms_raw = data.get("synonyms", [])
        if isinstance(synonyms_raw, str):
            synonyms = [synonyms_raw]
        elif isinstance(synonyms_raw, Sequence):
            synonyms = [str(item) for item in synonyms_raw if str(item).strip()]
        else:
            synonyms = []
        value_attribute = data.get("valueAttribute")
        return cls(
            profile_field=profile_field,
            label=str(data.get("label", "")).strip() or profile_field,
            synonyms=tuple(dict.fromkeys(_normalize_text(item) for item in synonyms if item)),
            selectors=tuple(dict.fromkeys(selectors)),
            widget_type=str(data.get("widgetType", "text")).strip() or "text",
            required=bool(data.get("required", False)),
            value_attribute=str(value_attribute).strip() if value_attribute else None,
        )


@dataclass(slots=True)
class FormStepConfig:
    """Container for fields grouped by logical Quick Apply step."""

    step_id: str
    title: str
    fields: tuple[FormFieldSelectorConfig, ...]

    @classmethod
    def from_mapping(cls, step_id: str, data: Mapping[str, Any]) -> "FormStepConfig":
        title = str(data.get("title", step_id)).strip()
        raw_fields = data.get("fields")
        if not isinstance(raw_fields, Sequence):
            raise ValueError(f"Step {step_id} must define a fields array")
        fields = [FormFieldSelectorConfig.from_mapping(item) for item in raw_fields]
        return cls(step_id=step_id, title=title, fields=tuple(fields))


@dataclass(slots=True)
class FormSelectorLibrary:
    """Immutable configuration tree of all supported Quick Apply fields."""

    steps: tuple[FormStepConfig, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "FormSelectorLibrary":
        steps_data = data.get("steps")
        if not isinstance(steps_data, Mapping):
            raise ValueError("Selector config must include a steps mapping")
        steps: list[FormStepConfig] = []
        for step_id, step_data in steps_data.items():
            if isinstance(step_data, Mapping):
                steps.append(FormStepConfig.from_mapping(step_id, step_data))
        if not steps:
            raise ValueError("Selector config did not contain any steps")
        return cls(steps=tuple(steps))

    @classmethod
    def load(
        cls,
        base: Path,
        *,
        overrides: Sequence[Path] | None = None,
    ) -> "FormSelectorLibrary":
        data = _load_json(base)
        for override in overrides or ():
            if override.exists():
                data = _merge_mapping(data, _load_json(override))
        return cls.from_mapping(data)

    def iter_fields(self) -> Iterable[tuple[FormStepConfig, FormFieldSelectorConfig]]:
        for step in self.steps:
            for field in step.fields:
                yield step, field


@dataclass(slots=True)
class FormFillPlanField:
    profile_field: str
    step: str
    selector: str
    widget_type: str
    required: bool
    label: str | None
    confidence: float
    options: list[dict[str, str]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profileField": self.profile_field,
            "step": self.step,
            "selector": self.selector,
            "widgetType": self.widget_type,
            "required": self.required,
            "confidence": round(self.confidence, 2),
        }
        if self.label:
            payload["label"] = self.label
        if self.options:
            payload["options"] = [dict(option) for option in self.options]
        if self.diagnostics:
            payload["diagnostics"] = dict(self.diagnostics)
        return payload


@dataclass(slots=True)
class FormFillPlanUnmapped:
    profile_field: str
    step: str
    reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "profileField": self.profile_field,
            "step": self.step,
            "reason": self.reason,
        }
        if self.diagnostics:
            payload["diagnostics"] = dict(self.diagnostics)
        return payload


@dataclass(slots=True)
class FormFillPlanStep:
    step_id: str
    title: str
    mapped: list[FormFillPlanField] = field(default_factory=list)
    unmapped: list[FormFillPlanUnmapped] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.step_id,
            "title": self.title,
            "mapped": [entry.to_payload() for entry in self.mapped],
            "unmapped": [entry.to_payload() for entry in self.unmapped],
        }


@dataclass(slots=True)
class FormFillPlan:
    steps: list[FormFillPlanStep]

    def mapped_count(self) -> int:
        return sum(len(step.mapped) for step in self.steps)

    def unmapped_count(self) -> int:
        return sum(len(step.unmapped) for step in self.steps)

    def to_payload(self) -> dict[str, Any]:
        return {
            "steps": [step.to_payload() for step in self.steps],
            "summary": {
                "steps": len(self.steps),
                "mappedFields": self.mapped_count(),
                "unmappedFields": self.unmapped_count(),
            },
        }


class FormStructureMapper:
    """Analyse Quick Apply DOM snapshots and produce a deterministic mapping plan."""

    def __init__(self, html: str, config: FormSelectorLibrary) -> None:
        self._soup = BeautifulSoup(html or "", "html.parser")
        self._config = config

    def generate_plan(self) -> FormFillPlan:
        steps: list[FormFillPlanStep] = []
        for step_config in self._config.steps:
            step_plan = FormFillPlanStep(step_id=step_config.step_id, title=step_config.title)
            for field_config in step_config.fields:
                result = self._map_field(step_config, field_config)
                if isinstance(result, FormFillPlanField):
                    step_plan.mapped.append(result)
                else:
                    step_plan.unmapped.append(result)
            steps.append(step_plan)
        return FormFillPlan(steps=steps)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _map_field(
        self, step: FormStepConfig, field: FormFieldSelectorConfig
    ) -> FormFillPlanField | FormFillPlanUnmapped:
        best_candidate: tuple[Tag, str, float, str | None, dict[str, Any]] | None = None
        for selector in field.selectors:
            for element in self._soup.select(selector):
                label_texts = self._collect_label_texts(element)
                placeholder = self._extract_placeholder(element)
                score, matched_label = self._score_candidate(
                    label_texts, field, placeholder
                )
                diagnostics = {
                    "domPath": self._dom_path(element),
                    "labelTexts": label_texts,
                    "placeholder": placeholder,
                    "attributes": self._safe_attributes(element),
                }
                if best_candidate is None or score > best_candidate[2]:
                    best_candidate = (element, selector, score, matched_label, diagnostics)
        if best_candidate is None:
            return FormFillPlanUnmapped(
                profile_field=field.profile_field,
                step=step.step_id,
                reason="selector_missing",
                diagnostics={
                    "selectors": list(field.selectors),
                    "synonyms": list(field.synonyms),
                },
            )

        element, selector, score, matched_label, diagnostics = best_candidate
        if score < _MIN_CONFIDENCE:
            reason = "label_missing"
            if diagnostics.get("labelTexts") or diagnostics.get("placeholder"):
                reason = "low_confidence"
            diagnostics.update({
                "confidence": round(score, 2),
                "selectors": list(field.selectors),
                "synonyms": list(field.synonyms),
            })
            return FormFillPlanUnmapped(
                profile_field=field.profile_field,
                step=step.step_id,
                reason=reason,
                diagnostics=diagnostics,
            )

        options = self._extract_options(element, field.widget_type)
        required = field.required or element.has_attr("required")
        payload_diagnostics = diagnostics | {
            "confidence": round(score, 2),
            "valueAttribute": field.value_attribute or "value",
        }
        return FormFillPlanField(
            profile_field=field.profile_field,
            step=step.step_id,
            selector=selector,
            widget_type=field.widget_type,
            required=required,
            label=matched_label,
            confidence=score,
            options=options,
            diagnostics=payload_diagnostics,
        )

    def _collect_label_texts(self, element: Tag) -> list[str]:
        texts: list[str] = []
        element_id = element.get("id")
        if element_id:
            label = self._soup.find("label", attrs={"for": element_id})
            if label:
                value = label.get_text(" ", strip=True)
                if value:
                    texts.append(value)
        parent_label = element.find_parent("label")
        if parent_label:
            value = parent_label.get_text(" ", strip=True)
            if value:
                texts.append(value)
        aria_label = element.get("aria-label")
        if aria_label:
            texts.append(aria_label.strip())
        aria_labelledby = element.get("aria-labelledby")
        if aria_labelledby:
            for ref in aria_labelledby.split():
                target = self._soup.find(id=ref)
                if target:
                    value = target.get_text(" ", strip=True)
                    if value:
                        texts.append(value)
        return list(dict.fromkeys([text for text in texts if text]))

    def _extract_placeholder(self, element: Tag) -> str | None:
        for attribute in ("placeholder", "aria-placeholder", "data-placeholder"):
            value = element.get(attribute)
            if value:
                return str(value)
        return None

    def _score_candidate(
        self,
        label_texts: Sequence[str],
        field: FormFieldSelectorConfig,
        placeholder: str | None,
    ) -> tuple[float, str | None]:
        synonyms = set(field.synonyms)
        canonical = _normalize_text(field.label)
        if canonical:
            synonyms.add(canonical)
        best_score = 0.0
        best_label: str | None = None
        for label in label_texts:
            normalized = _normalize_text(label)
            if not normalized:
                continue
            if normalized in synonyms:
                return 1.0, label
            if any(normalized in synonym for synonym in synonyms if synonym):
                if best_score < 0.85:
                    best_score = 0.85
                    best_label = label
            elif any(synonym in normalized for synonym in synonyms if synonym):
                if best_score < 0.75:
                    best_score = 0.75
                    best_label = label
            elif best_score < 0.6 and synonyms:
                best_score = 0.6
                best_label = label
        if placeholder:
            normalized_placeholder = _normalize_text(placeholder)
            if normalized_placeholder in synonyms:
                return 0.7, placeholder
            if any(normalized_placeholder in synonym for synonym in synonyms if synonym):
                best_score = max(best_score, 0.65)
                best_label = placeholder
            elif any(synonym in normalized_placeholder for synonym in synonyms if synonym):
                best_score = max(best_score, 0.6 if synonyms else 0.0)
                best_label = best_label or placeholder
        if not synonyms and label_texts:
            # Without synonyms fall back to the first label but with reduced confidence.
            best_score = max(best_score, 0.5)
            best_label = best_label or label_texts[0]
        return best_score, best_label

    def _extract_options(self, element: Tag, widget_type: str) -> list[dict[str, str]]:
        widget = widget_type.lower()
        if widget == "select":
            options = []
            for option in element.find_all("option"):
                label = option.get_text(" ", strip=True)
                options.append({
                    "value": option.get("value", ""),
                    "label": label,
                })
            return options
        if widget in {"radio", "checkbox"}:
            name = element.get("name")
            if not name:
                return []
            options: list[dict[str, str]] = []
            for input_el in self._soup.find_all("input", attrs={"name": name}):
                label_texts = self._collect_label_texts(input_el)
                label = label_texts[0] if label_texts else None
                options.append(
                    {
                        "value": input_el.get("value", ""),
                        "label": label or "",
                    }
                )
            return options
        return []

    def _dom_path(self, element: Tag) -> str:
        parts: list[str] = []
        node: Tag | None = element
        while node and isinstance(node, Tag):
            segment = node.name
            element_id = node.get("id")
            if element_id:
                segment += f"#{element_id}"
            else:
                classes = node.get("class")
                if classes:
                    segment += "." + ".".join(classes)
            index = 1
            sibling = node
            while sibling.previous_sibling:
                sibling = sibling.previous_sibling
                if isinstance(sibling, Tag) and sibling.name == node.name:
                    index += 1
            if index > 1:
                segment += f":nth-of-type({index})"
            parts.append(segment)
            node = node.parent if isinstance(node.parent, Tag) else None
        return " > ".join(reversed(parts))

    def _safe_attributes(self, element: Tag) -> dict[str, Any]:
        safe_keys = {"id", "name", "type", "data-testid", "aria-labelledby"}
        payload: dict[str, Any] = {}
        for key in safe_keys:
            if element.has_attr(key):
                payload[key] = element.get(key)
        return payload

