import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.getcwd())

from sites.simplyhired.summary_builder import SummaryCompiler
from sites.simplyhired.form_filler import (
    FieldFillOutcome,
    FormFillResult,
    StepFillResult,
)


def _build_form_result() -> FormFillResult:
    step = StepFillResult(step_id="step-1", title="Basic Info")
    step.filled.append(
        FieldFillOutcome(
            profile_field="identity.full_name",
            step="step-1",
            selector="input.name",
            widget_type="text",
            status="filled",
            value_preview="Alex Example",
        )
    )
    step.filled.append(
        FieldFillOutcome(
            profile_field="identity.email",
            step="step-1",
            selector="input.email",
            widget_type="text",
            status="filled",
            value_preview="alex@example.com",
        )
    )
    return FormFillResult(artifact=None, profile_id="frontend-dev", steps=[step])


def test_summary_compiler_masks_answers():
    compiler = SummaryCompiler()
    result = compiler.compile(
        run_id="run-123",
        dry_run=True,
        posting={"title": "Frontend Engineer", "postingUrl": "https://jobs/1"},
        form_result=_build_form_result(),
        resume_result=None,
        generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    payload = result.to_preview_payload()
    assert payload["headline"]["title"] == "Frontend Engineer"
    assert payload["form"]["filledFields"] == 2
    answers = payload["form"]["answers"]
    assert len(answers) == 2
    assert answers[0]["valuePreview"] == "Alex Example"
    assert answers[1]["hash"], "Expected hashed preview for deterministic audit"

    html = result.render_html()
    assert "Frontend Engineer" in html
    assert "Alex Example" in html

