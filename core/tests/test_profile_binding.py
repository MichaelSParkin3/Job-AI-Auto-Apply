from pathlib import Path

import json

from apps.cli.profiles import ProfileBinding, ProfileService


def _seed_profile(base: Path, profile_id: str = "qa-tester") -> Path:
    profile_dir = base / "data" / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    qa_overrides = {
        "phone": "+1-555-0000",
        "about": "This is a test biography",
    }
    qa_yaml = "\n".join(f"  {key}: {json.dumps(value)}" for key, value in qa_overrides.items())
    profile_yaml = f"""
identity:
  full_name: "Test User"
  email: "user@example.com"
  phone: null
  location: "Remote"
  portfolio: []
documents:
  resume_path: data/resumes/{profile_id}/resume.pdf
id: {json.dumps(profile_id)}
display_name: "QA Tester"
model_overrides:
  llm: "qa-model"
qa_overrides:
{qa_yaml}
links: {{}}
user_data_dir: .local/browser/profiles/{profile_id}
browser:
  model: "qa-model"
  locale: "en-US"
  timezone: "America/Chicago"
  viewport:
    width: 1280
    height: 720
  allowed_domains:
    - "*.simplyhired.com"
"""
    profile_path = profile_dir / f"{profile_id}.yaml"
    profile_path.write_text(profile_yaml.strip() + "\n", encoding="utf-8")
    resume_path = base / "data" / "resumes" / profile_id / "resume.pdf"
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_bytes(b"%PDF-1.4\n")
    return profile_path


def test_profile_binding_payloads(tmp_path: Path):
    service = ProfileService(base=tmp_path)
    _seed_profile(tmp_path)

    binding = service.bind_profile("qa-tester")
    cli_payload = binding.cli_payload()
    telemetry_payload = binding.telemetry_payload()

    assert cli_payload["valid"] is True
    assert cli_payload["qa_overrides"] == {
        "phone": "+1-555-0000",
        "about": "This is a test biography",
    }
    assert cli_payload["session_backups"]["enabled"] is None
    assert cli_payload["session_backups"]["retention"] is None
    assert telemetry_payload["qaOverrideKeys"] == ["about", "phone"]
    assert "qa_overrides" not in telemetry_payload
    assert telemetry_payload["resume"]["exists"] is True
    assert telemetry_payload["browser"]["allowed_domains"] == ["*.simplyhired.com"]
    assert telemetry_payload["sessionBackups"]["enabled"] is None


def test_profile_binding_demo_fallback(tmp_path: Path):
    binding = ProfileBinding.demo(tmp_path, profile_id="demo")
    assert binding.profile_id == "demo"
    assert binding.resume_exists is False
    assert binding.cli_payload()["valid"] is False
    assert binding.cli_payload()["session_backups"]["enabled"] is None
