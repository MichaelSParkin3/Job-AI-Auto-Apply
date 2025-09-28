import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("portalocker")

sys.path.insert(0, os.getcwd())

from apps.browser.controller import BrowserActionResult, BrowserActionStatus
from sites.simplyhired.resume_uploader import ResumeUploader


class StubController:
    def __init__(
        self,
        *,
        upload_results: list[BrowserActionResult],
        confirmation_results: list[BrowserActionResult] | None = None,
        html_result: BrowserActionResult | None = None,
    ) -> None:
        self.config = SimpleNamespace(profile_id="qa-profile", wait_jitter_ms=(0, 0))
        self._upload_results = upload_results
        self._confirmation_results = confirmation_results or [
            BrowserActionResult(
                BrowserActionStatus.OK,
                {"state": {"count": 1, "files": [{"name": "resume.pdf", "size": 1024}]}},
                {},
            )
        ]
        self._html_result = html_result or BrowserActionResult(
            BrowserActionStatus.OK,
            {"html": "<html></html>"},
            {},
        )
        self.upload_invocations = 0
        self.confirm_invocations = 0

    def upload_file(self, selector: str, file_path: Path, *, dry_run: bool = False):
        index = min(self.upload_invocations, len(self._upload_results) - 1)
        self.upload_invocations += 1
        return self._upload_results[index]

    def get_field_state(self, selector: str, widget_type: str) -> BrowserActionResult:
        index = min(self.confirm_invocations, len(self._confirmation_results) - 1)
        self.confirm_invocations += 1
        return self._confirmation_results[index]

    def get_page_html(self) -> BrowserActionResult:
        return self._html_result


def _ok_upload(file_name: str = "resume.pdf") -> BrowserActionResult:
    return BrowserActionResult(
        BrowserActionStatus.OK,
        {"response": {"file": {"name": file_name, "sizeBytes": 2048, "sha256": "deadbeef"}}},
        {},
    )


def _error_upload(message: str) -> BrowserActionResult:
    return BrowserActionResult(
        BrowserActionStatus.ERROR,
        {"error": message},
        {},
    )


def test_resume_uploader_success(tmp_path: Path) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    controller = StubController(upload_results=[_ok_upload()])
    uploader = ResumeUploader(
        controller,
        resume_path=resume,
        dry_run=False,
        run_dir=tmp_path,
        step_lookup={"contact": "Contact"},
    )

    result = uploader.upload(selector="input.resume", step_id="contact")
    assert result.status == "uploaded"
    assert result.attempts == 1
    assert result.file["name"] == "resume.pdf"
    assert result.confirmation.get("count") == 1
    assert result.artifact is None


def test_resume_uploader_failure_records_artifact(tmp_path: Path) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    controller = StubController(
        upload_results=[_error_upload("chooser_failed"), _error_upload("chooser_failed")],
        confirmation_results=[
            BrowserActionResult(
                BrowserActionStatus.OK,
                {"state": {"count": 0, "files": []}},
                {},
            )
        ],
        html_result=BrowserActionResult(
            BrowserActionStatus.OK,
            {"html": "<html><body>error</body></html>"},
            {},
        ),
    )
    uploader = ResumeUploader(
        controller,
        resume_path=resume,
        dry_run=False,
        run_dir=tmp_path,
        step_lookup={"contact": "Contact"},
        max_attempts=2,
    )

    result = uploader.upload(selector="input.resume", step_id="contact")
    assert result.status == "failed"
    assert result.attempts == 2
    assert result.artifact is not None
    assert Path(result.artifact).exists()
    assert controller.upload_invocations == 2


def test_resume_uploader_dry_run(tmp_path: Path) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    controller = StubController(upload_results=[_ok_upload()])
    uploader = ResumeUploader(
        controller,
        resume_path=resume,
        dry_run=True,
        run_dir=tmp_path,
        step_lookup={"contact": "Contact"},
    )

    result = uploader.upload(selector="input.resume", step_id="contact")
    assert result.status == "simulated"
    assert result.simulated is True
    assert result.attempts == 1
    assert result.confirmation.get("simulated") is True
