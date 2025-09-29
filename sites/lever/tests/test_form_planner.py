"""Tests for Lever form planning and execution helpers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.getcwd())

from sites.lever.form_executor import (  # noqa: E402
    LeverFormExecutor,
    LeverFormPlanner,
    detect_resume_success,
)


@pytest.fixture()
def selector_config(tmp_path: Path) -> Path:
    data = {
        "fields": [
            {
                "key": "fullName",
                "labels": ["Full name"],
                "selectors": ["input[data-qa='name-input']", "input[name='name']"],
            },
            {
                "key": "email",
                "labels": ["Email"],
                "selectors": ["input[data-qa='email-input']"],
            },
            {
                "key": "phone",
                "labels": ["Phone number"],
                "selectors": ["input[data-qa='phone-input']"],
            },
        ]
    }
    path = tmp_path / "selectors.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


FORM_HTML = """
<form id="application-form">
  <div class="application-question">
    <div class="application-label">Full name</div>
    <div class="application-field">
      <input data-qa="name-input" name="name" />
    </div>
  </div>
  <div class="application-question">
    <div class="application-label">Email</div>
    <div class="application-field">
      <input data-qa="email-input" name="email" type="email" />
    </div>
  </div>
  <div class="application-question">
    <div class="application-label">Phone number</div>
    <div class="application-field">
      <input data-qa="phone-input" name="phone" />
    </div>
  </div>
</form>
"""


def test_planner_matches_labels_and_prefers_data_qa(selector_config: Path):
    """Planner should match labels and return selectors in priority order."""

    planner = LeverFormPlanner.load(selector_config)
    plan = planner.plan_from_html(FORM_HTML)
    keys = [field.value_key for field in plan.fields]
    assert keys == ["fullName", "email", "phone"]
    selectors = [field.selector for field in plan.fields]
    assert selectors == [
        "input[data-qa='name-input']",
        "input[data-qa='email-input']",
        "input[data-qa='phone-input']",
    ]


def test_executor_returns_redacted_preview(selector_config: Path):
    """Executor should summarize filled vs missing answers."""

    planner = LeverFormPlanner.load(selector_config)
    plan = planner.plan_from_html(FORM_HTML)
    executor = LeverFormExecutor()
    answers = {
        "fullName": "Ada Augusta Lovelace",
        "email": "ada@example.com",
        # phone intentionally missing
    }
    summary = executor.execute(plan, profile_answers=answers)
    assert summary["source"] == "lever"
    assert summary["filled"] == [
            {
                "label": "Full name",
                "selector": "input[data-qa='name-input']",
                "valueKey": "fullName",
                "valuePreview": "Ada Augu…elace",
            },
        {
            "label": "Email",
            "selector": "input[data-qa='email-input']",
            "valueKey": "email",
            "valuePreview": "ada@example.com",
        },
    ]
    assert summary["skipped"] == [
        {
            "label": "Phone number",
            "selector": "input[data-qa='phone-input']",
            "valueKey": "phone",
            "reason": "missing",
        }
    ]
    assert summary["resumeSelector"] == "input#resume-upload-input.application-file-input"


def test_detect_resume_success_variants():
    """Resume success detection should handle widget class and input value."""

    success_html = """
    <div class="resume-upload-success">Uploaded!</div>
    <input id="resume-upload-input" class="application-file-input" value="resume.pdf" />
    """
    fallback_html = """
    <input id="resume-upload-input" class="application-file-input" value="resume.pdf" />
    """
    empty_html = """<div>No upload yet</div>"""

    assert detect_resume_success(success_html) is True
    assert detect_resume_success(fallback_html) is True
    assert detect_resume_success(empty_html) is False

