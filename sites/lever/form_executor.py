"""Lever form planning and execution helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
from typing import Any, Dict, List, Sequence


def _normalize_label(text: str) -> str:
    """Return a casefolded label string with collapsed whitespace."""

    collapsed = re.sub(r"\s+", " ", text or "").strip()
    sanitized = re.sub(r"[^\w\s]", "", collapsed)
    return sanitized.casefold()


@dataclass(slots=True)
class LeverFieldSpec:
    """Selector configuration for a Lever field."""

    key: str
    labels: tuple[str, ...]
    selectors: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "LeverFieldSpec":
        key = str(data.get("key", "")).strip()
        if not key:
            raise ValueError("field spec must include a key")
        raw_labels = data.get("labels", [])
        labels: List[str] = []
        if isinstance(raw_labels, str):
            raw_labels = [raw_labels]
        for label in raw_labels:
            normalized = _normalize_label(str(label))
            if normalized:
                labels.append(normalized)
        if not labels:
            raise ValueError(f"field {key} must define at least one label")
        raw_selectors = data.get("selectors", [])
        if isinstance(raw_selectors, str):
            raw_selectors = [raw_selectors]
        selectors: List[str] = []
        for selector in raw_selectors:
            selector = str(selector).strip()
            if selector:
                selectors.append(selector)
        if not selectors:
            raise ValueError(f"field {key} must define selectors")
        return cls(key=key, labels=tuple(dict.fromkeys(labels)), selectors=tuple(dict.fromkeys(selectors)))


@dataclass(slots=True)
class LeverFieldPlan:
    """Resolved plan entry for a Lever field."""

    label: str
    selector: str
    value_key: str


@dataclass(slots=True)
class LeverFormPlan:
    """Executable plan for filling a Lever form."""

    fields: List[LeverFieldPlan]
    resume_selector: str = "input#resume-upload-input.application-file-input"

    def to_payload(self) -> Dict[str, Any]:
        return {
            "resumeSelector": self.resume_selector,
            "fields": [
                {
                    "label": field.label,
                    "selector": field.selector,
                    "valueKey": field.value_key,
                }
                for field in self.fields
            ],
        }


class LeverFormPlanner:
    """Build Lever form plans by matching visible labels to configured selectors."""

    def __init__(self, specs: Sequence[LeverFieldSpec]) -> None:
        self.specs = list(specs)
        self._label_to_spec: Dict[str, LeverFieldSpec] = {}
        for spec in self.specs:
            for label in spec.labels:
                self._label_to_spec[label] = spec

    @classmethod
    def load(cls, path: Path) -> "LeverFormPlanner":
        data = json.loads(path.read_text(encoding="utf-8"))
        fields_data = data.get("fields", [])
        specs = [LeverFieldSpec.from_mapping(item) for item in fields_data]
        return cls(specs)

    def plan_from_html(self, html: str) -> LeverFormPlan:
        fields: List[LeverFieldPlan] = []

        for label_text, end_index in _iter_labels(html):
            normalized = _normalize_label(label_text)
            spec = self._label_to_spec.get(normalized)
            if not spec:
                continue
            selector = self._resolve_selector(html, end_index, spec)
            if not selector:
                continue
            fields.append(LeverFieldPlan(label=label_text, selector=selector, value_key=spec.key))

        return LeverFormPlan(fields=fields)

    def _resolve_selector(self, html: str, start_index: int, spec: LeverFieldSpec) -> str | None:
        """Return the preferred selector for the given label/spec."""

        search_space = html[start_index:]
        for selector in spec.selectors:
            hint_groups = _selector_hints(selector)
            if all(
                any(option in search_space for option in group)
                for group in hint_groups
            ):
                return selector
        return None


class LeverFormExecutor:
    """Summarize Lever form fills prior to browser execution."""

    def __init__(self, *, source: str = "lever") -> None:
        self.source = source

    def execute(self, plan: LeverFormPlan, *, profile_answers: Dict[str, Any]) -> Dict[str, Any]:
        """Return a redacted fill summary without interacting with the browser."""

        filled: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for field in plan.fields:
            value = profile_answers.get(field.value_key)
            if value in (None, ""):
                skipped.append(
                    {
                        "label": field.label,
                        "selector": field.selector,
                        "valueKey": field.value_key,
                        "reason": "missing",
                    }
                )
                continue
            preview = self._preview_value(value)
            filled.append(
                {
                    "label": field.label,
                    "selector": field.selector,
                    "valueKey": field.value_key,
                    "valuePreview": preview,
                }
            )
        return {
            "source": self.source,
            "filled": filled,
            "skipped": skipped,
            "resumeSelector": plan.resume_selector,
        }

    @staticmethod
    def _preview_value(value: Any) -> Any:
        if isinstance(value, str) and len(value) > 16:
            return f"{value[:8]}…{value[-5:]}"
        return value


def detect_resume_success(dom_html: str) -> bool:
    """Return True when the Lever resume widget indicates a successful upload."""

    success_class = re.search(
        r"class=[\"']([^\"']*(resume-upload-success|application-upload-success)[^\"']*)[\"']",
        dom_html,
        re.IGNORECASE,
    )
    if success_class:
        return True
    resume_value = re.search(
        r"id=[\"']resume-upload-input[\"'][^>]*class=[\"'][^\"']*application-file-input[^\"']*[\"'][^>]*value=[\"']([^\"']+)[\"']",
        dom_html,
        re.IGNORECASE,
    )
    return bool(resume_value)


_LABEL_RE = re.compile(
    r"<div[^>]*class=[\"'][^\"']*application-label[^\"']*[\"'][^>]*>(?P<label>.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)


def _iter_labels(html: str) -> List[tuple[str, int]]:
    entries: List[tuple[str, int]] = []
    for match in _LABEL_RE.finditer(html):
        label = _strip_html(match.group("label"))
        entries.append((label, match.end()))
    return entries


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


_SELECTOR_ATTR_RE = re.compile(r"\[(?P<attr>[\w-]+)=['\"]?(?P<value>[^'\"\]]+)['\"]?\]")


def _selector_hints(selector: str) -> List[List[str]]:
    hints: List[List[str]] = []
    for attr, value in _SELECTOR_ATTR_RE.findall(selector):
        hints.append([f"{attr}='{value}'", f"{attr}=\"{value}\""])
    id_match = re.search(r"#([\w-]+)", selector)
    if id_match:
        value = id_match.group(1)
        hints.append([f"id='{value}'", f"id=\"{value}\""])
    class_matches = re.findall(r"\.([\w-]+)", selector)
    for class_name in class_matches:
        hints.append([f"class='{class_name}'", f"class=\"{class_name}\""])
    # Deduplicate option groups while preserving order
    unique: List[List[str]] = []
    seen: set[tuple[str, ...]] = set()
    for group in hints:
        key = tuple(group)
        if key not in seen:
            seen.add(key)
            unique.append(group)
    return unique

