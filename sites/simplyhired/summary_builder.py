"""Utilities for compiling a redacted submission summary for SimplyHired runs."""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from apps.cli.redaction import redact_value

try:  # pragma: no cover - optional import during tests
    from sites.simplyhired.form_filler import FormFillResult, StepFillResult
    from sites.simplyhired.resume_uploader import ResumeUploadResult
except Exception:  # pragma: no cover - circular import guard for type checking
    FormFillResult = StepFillResult = ResumeUploadResult = Any  # type: ignore


def _sha256_prefix(value: str, *, length: int = 8) -> str:
    """Return a short SHA-256 hash prefix for deterministic redaction previews."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:max(4, length)]


@dataclass(slots=True)
class SummaryAnswerSnippet:
    """Represents a redacted preview of a filled form answer."""

    profile_field: str
    step: str
    status: str
    value_preview: str | None = None
    length: int | None = None
    hash_prefix: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profileField": self.profile_field,
            "step": self.step,
            "status": self.status,
        }
        if self.value_preview:
            payload["valuePreview"] = self.value_preview
        if self.length is not None:
            payload["length"] = self.length
        if self.hash_prefix:
            payload["hash"] = self.hash_prefix
        return payload


@dataclass(slots=True)
class SummaryHeadline:
    """Headline metadata rendered in review summaries."""

    title: str | None
    company: str | None
    location: str | None
    posting_url: str | None
    source: str = "simplyhired"

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title or "",
            "company": self.company or "",
            "location": self.location or "",
            "postingUrl": self.posting_url or "",
            "source": self.source,
        }


@dataclass(slots=True)
class SummaryFormSection:
    """Aggregated counts for form filling results."""

    filled_fields: int
    skipped_fields: int
    issues: int
    answers: list[SummaryAnswerSnippet] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "filledFields": self.filled_fields,
            "skippedFields": self.skipped_fields,
            "issues": self.issues,
            "answers": [answer.to_payload() for answer in self.answers],
        }

    def telemetry_payload(self) -> dict[str, Any]:
        return {
            "filledFields": self.filled_fields,
            "skippedFields": self.skipped_fields,
            "issues": self.issues,
            "answerCount": len(self.answers),
        }


@dataclass(slots=True)
class SummaryResumeSection:
    """Redacted resume upload diagnostics."""

    status: str
    attempts: int
    simulated: bool
    selector: str
    step: str
    step_title: str | None
    file_name: str | None
    file_sha256: str | None
    file_size: int | None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "attempts": self.attempts,
            "simulated": self.simulated,
            "selector": self.selector,
            "step": self.step,
        }
        if self.step_title:
            payload["stepTitle"] = self.step_title
        file_payload: dict[str, Any] = {}
        if self.file_name:
            payload["file"] = file_payload
            file_payload["name"] = self.file_name
        if self.file_sha256:
            file_payload.setdefault("hash", self.file_sha256)
        if self.file_size is not None:
            file_payload.setdefault("sizeBytes", self.file_size)
        return payload

    def telemetry_payload(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "attempts": self.attempts,
            "simulated": self.simulated,
        }
        if self.file_sha256:
            payload["fileHash"] = self.file_sha256
        return payload


@dataclass(slots=True)
class SummaryPayload:
    """Structured summary persisted to run artifacts and surfaced in CLI."""

    run_id: str
    generated_at: datetime
    headline: SummaryHeadline
    form: SummaryFormSection
    resume: SummaryResumeSection | None
    dry_run: bool
    source: str = "simplyhired"

    def iso_timestamp(self) -> str:
        value = self.generated_at.astimezone(timezone.utc)
        return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def to_preview_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "runId": self.run_id,
            "generatedAt": self.iso_timestamp(),
            "dryRun": self.dry_run,
            "source": self.source,
            "headline": self.headline.to_payload(),
            "form": self.form.to_payload(),
        }
        if self.resume:
            payload["resume"] = self.resume.to_payload()
        return payload

    def telemetry_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "runId": self.run_id,
            "generatedAt": self.iso_timestamp(),
            "dryRun": self.dry_run,
        }
        payload.update(self.form.telemetry_payload())
        if self.resume:
            payload["resume"] = self.resume.telemetry_payload()
        return payload

    def render_html(self) -> str:
        """Render a lightweight HTML representation for synthetic screenshots."""

        headline = self.headline.to_payload()
        answers = self.form.answers
        rows = "".join(
            f"<tr><td>{html.escape(answer.profile_field)}</td>"
            f"<td>{html.escape(answer.status)}</td>"
            f"<td>{html.escape(answer.value_preview or '—')}</td>"
            f"<td>{answer.length or 0}</td>"
            f"<td>{html.escape(answer.hash_prefix or '')}</td></tr>"
            for answer in answers
        )
        resume = self.resume.to_payload() if self.resume else {}
        file_payload = resume.get("file") or {}
        return f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Submission Summary</title>
    <style>
      body {{ font-family: 'Segoe UI', sans-serif; background: #111827; color: #f9fafb; margin: 0; padding: 24px; }}
      h1 {{ font-size: 20px; margin-bottom: 8px; }}
      section {{ margin-bottom: 20px; }}
      .card {{ background: #1f2937; border-radius: 12px; padding: 16px; box-shadow: 0 4px 24px rgba(15,23,42,0.35); }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
      th, td {{ text-align: left; padding: 6px 8px; font-size: 12px; border-bottom: 1px solid rgba(148, 163, 184, 0.2); }}
      th {{ text-transform: uppercase; letter-spacing: 0.05em; color: #9ca3af; font-size: 11px; }}
      .meta {{ display: flex; gap: 16px; font-size: 13px; color: #d1d5db; }}
      .pill {{ padding: 4px 10px; border-radius: 999px; background: rgba(59,130,246,0.2); color: #93c5fd; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>{html.escape(headline.get('title') or 'Review submission')}</h1>
      <div class="meta">
        <span>{html.escape(headline.get('company') or 'Unknown company')}</span>
        <span>{html.escape(headline.get('location') or 'Location unknown')}</span>
        <span class="pill">{html.escape(self.source.title())}</span>
      </div>
    </div>
    <section class="card">
      <h1>Form Summary</h1>
      <div class="meta">
        <span>Filled: {self.form.filled_fields}</span>
        <span>Skipped: {self.form.skipped_fields}</span>
        <span>Issues: {self.form.issues}</span>
      </div>
      <table>
        <thead>
          <tr><th>Profile Field</th><th>Status</th><th>Preview</th><th>Length</th><th>Hash</th></tr>
        </thead>
        <tbody>{rows or '<tr><td colspan="5">No answers captured.</td></tr>'}</tbody>
      </table>
    </section>
    <section class="card">
      <h1>Resume Upload</h1>
      <div class="meta">
        <span>Status: {html.escape(resume.get('status', 'unknown'))}</span>
        <span>Attempts: {resume.get('attempts', 0)}</span>
        <span>Simulated: {str(resume.get('simulated', False)).lower()}</span>
      </div>
      <p>File: {html.escape(file_payload.get('name', 'n/a'))} (hash: {html.escape(file_payload.get('hash', 'n/a'))})</p>
    </section>
  </body>
</html>
"""


class SummaryCompiler:
    """Build a SummaryPayload from run artifacts with strict redaction."""

    def __init__(self, *, source: str = "simplyhired") -> None:
        self._source = source

    def compile(
        self,
        *,
        run_id: str,
        dry_run: bool,
        posting: Mapping[str, Any],
        form_result: FormFillResult | None,
        resume_result: ResumeUploadResult | None,
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

        form_section = self._build_form_section(form_result)
        resume_section = self._build_resume_section(resume_result)

        return SummaryPayload(
            run_id=run_id,
            generated_at=generated,
            headline=headline,
            form=form_section,
            resume=resume_section,
            dry_run=dry_run,
            source=self._source,
        )

    def _build_form_section(
        self, result: FormFillResult | None
    ) -> SummaryFormSection:
        if result is None:
            return SummaryFormSection(filled_fields=0, skipped_fields=0, issues=0)

        answers = self._extract_answers(result.steps)
        return SummaryFormSection(
            filled_fields=result.filled_count(),
            skipped_fields=result.skipped_count(),
            issues=result.issue_count(),
            answers=answers,
        )

    def _extract_answers(
        self, steps: Sequence[StepFillResult]
    ) -> list[SummaryAnswerSnippet]:
        answers: list[SummaryAnswerSnippet] = []
        for step in steps:
            answers.extend(self._answers_from_step(step))
        return answers

    def _answers_from_step(self, step: StepFillResult) -> Iterable[SummaryAnswerSnippet]:
        for outcome in step.filled:
            preview = outcome.value_preview or ""
            safe_preview = str(redact_value(preview)) if preview else ""
            snippet = SummaryAnswerSnippet(
                profile_field=outcome.profile_field,
                step=step.step_id,
                status=outcome.status,
                value_preview=safe_preview or None,
                length=len(preview) if preview else None,
                hash_prefix=_sha256_prefix(preview) if preview else None,
            )
            yield snippet

    def _build_resume_section(
        self, result: ResumeUploadResult | None
    ) -> SummaryResumeSection | None:
        if result is None:
            return None

        file_payload = result.file or {}
        file_name = file_payload.get("name")
        masked_name = None
        if isinstance(file_name, str) and file_name:
            ext = ""
            if "." in file_name:
                ext = file_name[file_name.rfind(".") :]
            masked_name = f"resume-{_sha256_prefix(file_name)}{ext}" if ext else f"resume-{_sha256_prefix(file_name)}"
        sha256 = file_payload.get("sha256") or file_payload.get("hash")
        size = file_payload.get("sizeBytes") or file_payload.get("size")
        return SummaryResumeSection(
            status=result.status,
            attempts=result.attempts,
            simulated=result.simulated,
            selector=result.selector,
            step=result.step_id,
            step_title=result.step_title,
            file_name=masked_name,
            file_sha256=sha256 if isinstance(sha256, str) else None,
            file_size=int(size) if isinstance(size, (int, float)) else None,
        )


__all__ = [
    "SummaryCompiler",
    "SummaryPayload",
    "SummaryHeadline",
    "SummaryFormSection",
    "SummaryResumeSection",
    "SummaryAnswerSnippet",
]

