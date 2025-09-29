from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from apps.browser import BrowserUseController
from apps.cli.redaction import redact_value
from sites.simplyhired.summary_builder import (
    SummaryAnswerSnippet,
    SummaryFormSection,
    SummaryHeadline,
    SummaryPayload,
    SummaryResumeSection,
)


def _sha256_prefix(value: str, *, length: int = 8) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[: max(4, length)]


@dataclass(slots=True)
class LeverPreviewResult:
    """Preview payload and telemetry emitted for review artifacts."""

    summary: dict[str, Any]
    screenshot: dict[str, Any]
    telemetry: dict[str, Any]


class LeverSummaryBuilder:
    """Compile Lever form summaries and capture review artifacts."""

    def __init__(self, *, source: str = "lever-google") -> None:
        self._source = source

    def build(
        self,
        *,
        run_id: str,
        dry_run: bool,
        posting: Mapping[str, Any],
        form_summary: Mapping[str, Any],
        resume_success: bool | None,
        generated_at: datetime | None = None,
    ) -> SummaryPayload:
        generated = generated_at or datetime.now(timezone.utc)
        headline = SummaryHeadline(
            title=str(posting.get("title")) if posting.get("title") else None,
            company=str(posting.get("company")) if posting.get("company") else None,
            location=str(posting.get("location")) if posting.get("location") else None,
            posting_url=str(posting.get("postingUrl")) if posting.get("postingUrl") else None,
            source=self._source,
        )

        filled_answers = list(self._build_answer_snippets(form_summary.get("filled") or [], status="filled"))
        skipped_answers = list(
            self._build_answer_snippets(form_summary.get("skipped") or [], status="skipped")
        )
        answers = filled_answers + skipped_answers
        form_section = SummaryFormSection(
            filled_fields=len(filled_answers),
            skipped_fields=len(skipped_answers),
            issues=0,
            answers=answers,
        )

        resume_section = self._build_resume_section(
            form_summary.get("resumeSelector"), resume_success, dry_run
        )

        return SummaryPayload(
            run_id=run_id,
            generated_at=generated,
            headline=headline,
            form=form_section,
            resume=resume_section,
            dry_run=dry_run,
            source=self._source,
        )

    def capture_preview(
        self,
        controller: BrowserUseController,
        summary: SummaryPayload,
        *,
        output_path: Path,
    ) -> LeverPreviewResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        capture = controller.capture_review_artifacts(
            output_path=output_path,
            summary_html=summary.render_html(),
        )
        capture_payload = capture.to_payload()
        summary_payload = summary.to_preview_payload()
        summary_telemetry = summary.telemetry_payload()
        screenshot_telemetry = capture.telemetry_payload()
        screenshot_telemetry["path"] = capture_payload.get("path")
        summary_telemetry["screenshot"] = screenshot_telemetry
        return LeverPreviewResult(
            summary=summary_payload,
            screenshot=capture_payload,
            telemetry=summary_telemetry,
        )

    def _build_answer_snippets(
        self, entries: list[Mapping[str, Any]], *, status: str
    ) -> list[SummaryAnswerSnippet]:
        snippets: list[SummaryAnswerSnippet] = []
        for entry in entries:
            profile_field = str(entry.get("valueKey") or entry.get("label") or "")
            preview = str(entry.get("valuePreview") or "")
            safe_preview = str(redact_value(preview)) if preview else ""
            snippet = SummaryAnswerSnippet(
                profile_field=profile_field,
                step="lever.form",
                status=status,
                value_preview=safe_preview or None,
                length=len(preview) if preview else None,
                hash_prefix=_sha256_prefix(preview) if preview else None,
            )
            snippets.append(snippet)
        return snippets

    def _build_resume_section(
        self,
        selector: Any,
        resume_success: bool | None,
        dry_run: bool,
    ) -> SummaryResumeSection | None:
        if resume_success is None:
            return None
        selector_str = str(selector) if selector else "input#resume-upload-input.application-file-input"
        status = "uploaded" if resume_success else "missing"
        attempts = 1 if resume_success else 0
        return SummaryResumeSection(
            status=status,
            attempts=attempts,
            simulated=dry_run,
            selector=selector_str,
            step="lever.resume",
            step_title="Resume upload",
            file_name=None,
            file_sha256=None,
            file_size=None,
        )


__all__ = ["LeverSummaryBuilder", "LeverPreviewResult"]

