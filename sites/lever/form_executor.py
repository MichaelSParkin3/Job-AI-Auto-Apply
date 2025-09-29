from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class LeverFieldPlan:
    label: str
    selector: str
    value_key: str


@dataclass(slots=True)
class LeverFormPlan:
    fields: List[LeverFieldPlan]
    resume_selector: str = "input#resume-upload-input.application-file-input"


class LeverFormExecutor:
    """Thin executor to be wired to BrowserUseController.

    This scaffold mirrors the SimplyHired executor shape but avoids runtime
    coupling until Story 4.0 implementation. It provides method signatures
    and telemetry dicts so tests/mocks can target them.
    """

    def __init__(self, *, source: str = "lever") -> None:
        self.source = source

    def execute(self, plan: LeverFormPlan, *, profile_answers: Dict[str, Any]) -> Dict[str, Any]:
        """Return a redacted fill summary without interacting with the browser yet."""

        filled: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for field in plan.fields:
            key = field.value_key
            value = profile_answers.get(key)
            if value in (None, ""):
                skipped.append({"label": field.label, "selector": field.selector, "reason": "missing"})
            else:
                preview = str(value)[:8] + "…" if isinstance(value, str) and len(value) > 8 else value
                filled.append({"label": field.label, "selector": field.selector, "valuePreview": preview})
        return {
            "source": self.source,
            "filled": filled,
            "skipped": skipped,
        }

