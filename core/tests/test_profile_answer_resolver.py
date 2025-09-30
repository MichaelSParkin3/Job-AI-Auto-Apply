import json
from pathlib import Path
import os
import sys

import pytest

pytest.importorskip("yaml")
pytest.importorskip("portalocker")

sys.path.insert(0, os.getcwd())

from apps.cli.profiles import (
    ProfileAnswerResolver,
    ProfileBinding,
    ProfileConfig,
)


def _build_profile() -> ProfileConfig:
    raw = {
        "id": "frontend-dev",
        "display_name": "Frontend Developer",
        "identity": {
            "full_name": "Alex Example",
            "email": "Alex@Example.COM ",
            "phone": "(555) 555-1212",
            "location": "Remote",
            "portfolio": ["https://linkedin.com/in/alex-example"],
        },
        "documents": {"resume_path": "data/resumes/frontend-dev/resume.pdf"},
        "qa_overrides": {
            "workAuthorization": "Yes",
            "relocation": "No",
            "experienceLevel": "Senior",
            "coverLetter": "Tailored cover letter",
        },
        "links": {"linkedin": "https://linkedin.com/in/alex"},
        "user_data_dir": ".local/browser/profiles/frontend-dev",
    }
    return ProfileConfig.model_validate(json.loads(json.dumps(raw)))


def _build_binding() -> ProfileBinding:
    return ProfileBinding(
        profile_id="frontend-dev",
        display_name="Frontend Developer",
        resume_path=Path("/tmp/resume.pdf"),
        user_data_dir=Path("/tmp/browser"),
        qa_overrides={"customQuestion": "N/A"},
        model_overrides={},
        browser_overrides={},
        plan_overrides={},
        session_backups_enabled=None,
        session_backups_retention=None,
        resume_exists=True,
        errors=[],
    )


def test_resolver_uses_identity_and_normalisation() -> None:
    profile = _build_profile()
    resolver = ProfileAnswerResolver(profile=profile, binding=_build_binding())

    full_name = resolver.resolve(profile_field="fullName")
    assert full_name.is_resolved
    assert full_name.value == "Alex Example"
    assert full_name.source == "identity.full_name"

    email = resolver.resolve(profile_field="email")
    assert email.value == "alex@example.com"

    phone = resolver.resolve(profile_field="phone")
    assert phone.value == "+1 555 555 1212"

    preferred = resolver.resolve(profile_field="preferredName")
    assert preferred.value == "Alex"

    linkedin = resolver.resolve(profile_field="linkedinUrl")
    assert linkedin.value == "https://linkedin.com/in/alex"


def test_resolver_falls_back_to_overrides_and_templates() -> None:
    profile = _build_profile()
    binding = _build_binding()
    resolver = ProfileAnswerResolver(profile=profile, binding=binding)

    work_auth = resolver.resolve(
        profile_field="workAuthorization",
        label="Are you legally authorized to work in the US?",
    )
    assert work_auth.is_resolved
    assert work_auth.value == "Yes"

    relocation = resolver.resolve(profile_field="relocation")
    assert relocation.value == "No"

    experience = resolver.resolve(profile_field="experienceLevel")
    assert experience.value == "Senior"

    custom = resolver.resolve(profile_field="customQuestion")
    assert custom.value == "N/A"

    cover_letter = resolver.resolve(profile_field="coverLetter")
    assert cover_letter.value == "Tailored cover letter"

    # Remove override to ensure template fallback is produced
    profile.qa_overrides.pop("coverLetter")
    resolver_template = ProfileAnswerResolver(profile=profile, binding=binding)
    template_answer = resolver_template.resolve(profile_field="coverLetter")
    assert template_answer.is_resolved
    assert "Alex" in template_answer.value


def test_resolver_marks_missing_when_no_data() -> None:
    profile = _build_profile()
    profile.identity.email = None  # type: ignore[assignment]
    resolver = ProfileAnswerResolver(profile=profile, binding=None)

    email = resolver.resolve(profile_field="email")
    assert not email.is_resolved
    assert email.reason == "profile_missing"
