import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

sys.path.insert(0, os.getcwd())

from apps.browser import BrowserActionResult, BrowserActionStatus, ReviewArtifactCapture
from apps.cli.main import apply_run, _lever_guardrail_domains
from apps.cli.run_store import RunRecord, RunStore
from apps.preview.main import create_app


APPLY_HTML = """
<html><body>
<form id="application-form">
  <div class="application-question">
    <div class="application-label">Full name</div>
    <div class="application-field"><input data-qa="name-input" /></div>
  </div>
  <div class="application-question">
    <div class="application-label">Email</div>
    <div class="application-field"><input data-qa="email-input" /></div>
  </div>
  <div class="application-question">
    <div class="application-label">Phone number</div>
    <div class="application-field"><input data-qa="phone-input" /></div>
  </div>
  <input id="resume-upload-input" class="application-file-input" />
</form>
</body></html>
"""


class StubBrowserController:
    """Deterministic stub that mimics BrowserUseController behaviour for tests."""

    last_config = None

    def __init__(self, config) -> None:
        StubBrowserController.last_config = config
        self.config = config
        self._current_url: str | None = None

    def open_url(self, url: str) -> BrowserActionResult:
        self._current_url = url
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": {"url": url}},
            telemetry={"event": "stub.open"},
        )

    def wait_for_idle(self, timeout: float = 5.0) -> BrowserActionResult:
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": {"timeout": timeout}},
            telemetry={"event": "stub.idle"},
        )

    def get_page_html(self) -> BrowserActionResult:
        html = APPLY_HTML if self._current_url and "lever.co" in self._current_url else ""
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"html": html},
            telemetry={"event": "stub.html"},
        )

    def get_current_url(self) -> BrowserActionResult:
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"url": self._current_url},
            telemetry={"event": "stub.url"},
        )

    def safe_click(self, selector: str, timeout: float | None = None) -> BrowserActionResult:
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"selector": selector, "timeout": timeout},
            telemetry={"event": "stub.click"},
        )

    def upload_file(self, selector, file_path, *, dry_run=False, timeout=None, think_time=True):
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": {"simulated": dry_run, "file": {"name": file_path.name}}},
            telemetry={"event": "stub.upload"},
        )

    def get_field_state(self, selector, widget_type):
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"state": {"count": 1}},
            telemetry={"event": "stub.field_state"},
        )

    def capture_review_artifacts(self, *, output_path: Path, summary_html: str | None = None) -> ReviewArtifactCapture:
        output_path.write_bytes(b"stub")
        return ReviewArtifactCapture(
            screenshot_path=output_path,
            method="stub",
            metadata={"ok": True},
        )


@pytest.fixture()
def lever_cli_run(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    profile_dir = tmp_path / "data" / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    resume_path = tmp_path / "data" / "resumes" / "qa-tester" / "resume.pdf"
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_bytes(b"%PDF-1.4\n")
    profile_yaml = """
identity:
  full_name: "Test User"
  email: "user@example.com"
  phone: null
  location: "Remote"
  portfolio: []
documents:
  resume_path: data/resumes/qa-tester/resume.pdf
id: "qa-tester"
display_name: "QA Tester"
model_overrides:
  llm: "qa-model"
qa_overrides:
  phone: "+1-555-0000"
links: {}
user_data_dir: .local/browser/profiles/qa-tester
browser:
  model: "qa-model"
  locale: "en-US"
  timezone: "America/Chicago"
  viewport:
    width: 1280
    height: 720
"""
    (profile_dir / "qa-tester.yaml").write_text(profile_yaml.strip() + "\n", encoding="utf-8")

    plan_payload = {
        "plan": {"baseUrl": "https://www.google.com/search?q=lever", "pages": 1, "urls": []},
        "results": [
            {
                "title": "Front End Engineer",
                "href": "https://jobs.lever.co/acme/front-end/apply",
                "mode": "apply_direct",
            }
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")

    selectors_src = Path(__file__).resolve().parents[3] / "sites" / "lever" / "selectors" / "form-fields.json"
    selectors_dest = tmp_path / "sites" / "lever" / "selectors"
    selectors_dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(selectors_src, selectors_dest / "form-fields.json")

    monkeypatch.setattr("apps.cli.main.BrowserUseController", StubBrowserController)

    run_id = apply_run(
        source="lever-google",
        plan=plan_path,
        terms=None,
        location=None,
        time_window=None,
        pages=1,
        limit=None,
        profile="qa-tester",
        dry_run=True,
        mode="review",
        model=None,
    )
    return {
        "base": tmp_path,
        "run_id": run_id,
        "plan": plan_payload,
    }


def test_apply_run_populates_queue_and_artifacts(lever_cli_run):
    base = lever_cli_run["base"]
    run_id = lever_cli_run["run_id"]
    assert run_id
    run_dir = base / "runs" / run_id
    assert run_dir.exists()

    queue_snapshot = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
    assert queue_snapshot["pending"], "pending candidates should be recorded"
    first_candidate = queue_snapshot["pending"][0]
    assert first_candidate["state"] == "awaiting_decision"

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    candidate_payload = run_payload["lever"]["candidates"][first_candidate["id"]]
    assert candidate_payload["state"] == "awaiting_decision"
    assert candidate_payload["resumeUpload"]["status"] == "simulated"
    screenshot_path = candidate_payload["artifacts"]["previewScreenshot"]
    assert Path(screenshot_path).exists()

    guardrails = StubBrowserController.last_config.guardrail_domains
    assert tuple(guardrails) == tuple(_lever_guardrail_domains())


def test_preview_queue_endpoint_serves_snapshot(monkeypatch, lever_cli_run):
    base = lever_cli_run["base"]
    run_id = lever_cli_run["run_id"]
    run_dir = base / "runs" / run_id
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    started_at = datetime.fromisoformat(payload["startedAt"].replace("Z", "+00:00"))
    run_record = RunRecord(
        id=run_id,
        started_at=started_at,
        run_dir=run_dir,
        run_json_path=run_dir / "run.json",
        logs_path=run_dir / "actions.log",
        profile_id=payload.get("profileId"),
        screenshot_path=None,
    )
    run_store = RunStore(base=base)

    app = create_app(demo=False, run_store=run_store, run_record=run_record)
    client = TestClient(app)
    response = client.get(f"/api/queue/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["pending"], "queue endpoint should return pending entries"
