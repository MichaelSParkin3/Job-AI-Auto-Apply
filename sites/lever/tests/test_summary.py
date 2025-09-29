import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from apps.browser import ReviewArtifactCapture
from sites.lever.summary import LeverPreviewResult, LeverSummaryBuilder


class CaptureStubController:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def capture_review_artifacts(
        self,
        *,
        output_path: Path,
        summary_html: str | None = None,
    ) -> ReviewArtifactCapture:
        self.calls.append(summary_html or "")
        output_path.write_bytes(b"stub")
        return ReviewArtifactCapture(
            screenshot_path=output_path,
            method="stub",
            metadata={"ok": True},
        )


def test_summary_builder_compiles_preview_payload() -> None:
    builder = LeverSummaryBuilder()
    form_summary = {
        "filled": [
            {
                "label": "Full name",
                "selector": "input[name='name']",
                "valueKey": "fullName",
                "valuePreview": "Ada Lovelace",
            }
        ],
        "skipped": [
            {
                "label": "Phone",
                "selector": "input[name='phone']",
                "valueKey": "phone",
                "reason": "missing",
            }
        ],
        "resumeSelector": "input#resume-upload-input.application-file-input",
    }
    posting = {
        "title": "Front End Engineer",
        "company": "Acme",
        "location": "Remote",
        "postingUrl": "https://jobs.lever.co/acme/front-end/apply",
    }

    payload = builder.build(
        run_id="run-1",
        dry_run=True,
        posting=posting,
        form_summary=form_summary,
        resume_success=True,
    )

    preview = payload.to_preview_payload()
    assert preview["form"]["filledFields"] == 1
    assert preview["form"]["skippedFields"] == 1
    assert preview["headline"]["source"] == "lever-google"
    assert preview["resume"]["status"] == "uploaded"
    assert payload.form.answers[0].profile_field == "fullName"
    assert payload.form.answers[1].status == "skipped"


def test_summary_builder_capture_preview(tmp_path: Path) -> None:
    builder = LeverSummaryBuilder()
    summary = builder.build(
        run_id="run-2",
        dry_run=True,
        posting={"title": None, "company": None, "location": None, "postingUrl": None},
        form_summary={"filled": [], "skipped": [], "resumeSelector": None},
        resume_success=False,
    )
    controller = CaptureStubController()
    output_path = tmp_path / "pre-submit.png"

    result = builder.capture_preview(controller, summary, output_path=output_path)

    assert isinstance(result, LeverPreviewResult)
    assert controller.calls[0] == summary.render_html()
    assert result.screenshot["path"] == str(output_path)
    assert result.telemetry["screenshot"]["path"] == str(output_path)
