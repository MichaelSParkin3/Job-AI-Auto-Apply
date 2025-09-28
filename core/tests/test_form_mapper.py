from __future__ import annotations

from pathlib import Path

import pytest

from sites.simplyhired.form_mapper import (
    FormSelectorLibrary,
    FormStructureMapper,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTOR_PATH = PROJECT_ROOT / "sites" / "simplyhired" / "selectors" / "form-fields.json"
FIXTURES_DIR = (
    PROJECT_ROOT / "core" / "tests" / "fixtures" / "simplyhired" / "forms"
)


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def selector_library() -> FormSelectorLibrary:
    return FormSelectorLibrary.load(SELECTOR_PATH)


def test_mapper_maps_contact_fields(selector_library: FormSelectorLibrary) -> None:
    html = _load_fixture("contact-step.html")
    mapper = FormStructureMapper(html, selector_library)
    plan = mapper.generate_plan()
    contact_step = next(step for step in plan.steps if step.step_id == "contact")
    mapped = {entry.profile_field: entry for entry in contact_step.mapped}

    assert {"fullName", "email", "phone", "preferredName", "linkedinUrl"}.issubset(
        mapped.keys()
    )
    assert mapped["fullName"].label.lower().startswith("full legal")
    assert mapped["email"].required is True
    assert mapped["phone"].diagnostics["attributes"]["id"] == "contact-phone"
    assert mapped["linkedinUrl"].confidence >= 0.6


def test_mapper_extracts_grouped_options(selector_library: FormSelectorLibrary) -> None:
    html = _load_fixture("employer-questions.html")
    mapper = FormStructureMapper(html, selector_library)
    plan = mapper.generate_plan()
    employer_step = next(
        step for step in plan.steps if step.step_id == "employerQuestions"
    )
    mapped = {entry.profile_field: entry for entry in employer_step.mapped}

    authorization = mapped["workAuthorization"]
    assert authorization.widget_type == "radio"
    assert [option["value"] for option in authorization.options] == ["yes", "no"]

    relocation = mapped["relocation"]
    assert relocation.widget_type == "checkbox"
    assert relocation.options[0]["label"].startswith("Yes")

    experience = mapped["experienceLevel"]
    assert experience.widget_type == "select"
    labels = [option["label"] for option in experience.options]
    assert "Mid" in labels and "Senior" in labels


def test_mapper_records_unmapped_when_label_missing(
    selector_library: FormSelectorLibrary,
) -> None:
    html = _load_fixture("missing-label.html")
    mapper = FormStructureMapper(html, selector_library)
    plan = mapper.generate_plan()
    contact_step = next(step for step in plan.steps if step.step_id == "contact")
    mapped = {entry.profile_field: entry for entry in contact_step.mapped}
    unmapped = {entry.profile_field: entry for entry in contact_step.unmapped}

    assert mapped["email"].label == "Email"
    assert "customQuestion" in unmapped
    assert unmapped["customQuestion"].reason in {"label_missing", "low_confidence"}
    assert "selectors" in unmapped["customQuestion"].diagnostics

