from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from apps.browser import BrowserActionResult, BrowserActionStatus, BrowserUseController
from apps.cli.utils import log_event


@dataclass(slots=True)
class ResumeUploadResult:
    """Represents the outcome of attempting to upload a resume."""

    status: str
    attempts: int
    simulated: bool
    selector: str
    step_id: str
    step_title: str | None
    file: Dict[str, Any]
    confirmation: Dict[str, Any]
    artifact: str | None
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": self.status,
            "attempts": self.attempts,
            "simulated": self.simulated,
            "selector": self.selector,
            "step": self.step_id,
            "file": dict(self.file),
            "confirmation": dict(self.confirmation),
        }
        if self.step_title:
            payload["stepTitle"] = self.step_title
        if self.artifact:
            payload["artifact"] = self.artifact
        if self.diagnostics:
            payload["diagnostics"] = dict(self.diagnostics)
        return payload

    def telemetry_payload(self) -> Dict[str, Any]:
        confirmation = dict(self.confirmation)
        count = 0
        if "count" in confirmation and isinstance(confirmation["count"], int):
            count = confirmation["count"]
        elif "files" in confirmation and isinstance(confirmation["files"], Sequence):
            count = len(confirmation["files"])
        payload: Dict[str, Any] = {
            "status": self.status,
            "attempts": self.attempts,
            "simulated": self.simulated,
            "confirmationCount": count,
        }
        if self.artifact:
            payload["artifact"] = self.artifact
        return payload


class ResumeUploader:
    """Deterministically attach a resume file with guardrail-aware retries."""

    def __init__(
        self,
        controller: BrowserUseController,
        *,
        resume_path: Path,
        dry_run: bool,
        run_dir: Path,
        step_lookup: Mapping[str, str],
        max_attempts: int = 2,
        rng: random.Random | None = None,
    ) -> None:
        self._controller = controller
        self._resume_path = resume_path
        self._dry_run = dry_run
        self._artifacts_dir = run_dir / "resume"
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._step_lookup = dict(step_lookup)
        self._max_attempts = max(1, max_attempts)
        self._rng = rng or random.Random()
        wait_range = controller.config.wait_jitter_ms
        self._wait_range = (int(wait_range[0]), int(wait_range[1])) if wait_range else (0, 0)

    def upload(self, *, selector: str, step_id: str) -> ResumeUploadResult:
        step_title = self._step_lookup.get(step_id)
        attempts = 0
        last_error: Dict[str, Any] | None = None
        confirmation_payload: Dict[str, Any] | None = None
        for attempt in range(1, self._max_attempts + 1):
            attempts = attempt
            upload_result = self._controller.upload_file(
                selector,
                self._resume_path,
                dry_run=self._dry_run,
            )
            if upload_result.status is BrowserActionStatus.ERROR:
                last_error = dict(upload_result.details)
            else:
                if self._dry_run:
                    confirmation_payload = {
                        "simulated": True,
                        "count": 1,
                    }
                else:
                    confirmation_payload = self._confirm(selector)
                if self._dry_run or self._is_confirmed(confirmation_payload):
                    file_payload = self._extract_file_payload(upload_result)
                    log_event(
                        {
                            "event": "RESUME_UPLOAD_CONFIRMED",
                            "profileId": self._controller.config.profile_id,
                            "selector": selector,
                            "step": step_id,
                            "stepTitle": step_title,
                            "simulated": self._dry_run,
                            "confirmation": confirmation_payload,
                        }
                    )
                    return ResumeUploadResult(
                        status="simulated" if self._dry_run else "uploaded",
                        attempts=attempt,
                        simulated=self._dry_run,
                        selector=selector,
                        step_id=step_id,
                        step_title=step_title,
                        file=file_payload,
                        confirmation=confirmation_payload or {},
                        artifact=None,
                        diagnostics={},
                    )
                last_error = {
                    "error": "confirmation_failed",
                    "confirmation": confirmation_payload or {},
                }
            if attempt < self._max_attempts and not self._dry_run:
                wait_seconds = self._compute_backoff_seconds()
                log_event(
                    {
                        "event": "RESUME_UPLOAD_RETRY",
                        "profileId": self._controller.config.profile_id,
                        "selector": selector,
                        "step": step_id,
                        "attempt": attempt,
                        "remaining": self._max_attempts - attempt,
                        "waitSeconds": wait_seconds,
                    }
                )
                if wait_seconds > 0:
                    time.sleep(wait_seconds)

        artifact = self._capture_artifact(step_id, attempts)
        log_event(
            {
                "level": "error",
                "event": "RESUME_UPLOAD_FAILED",
                "profileId": self._controller.config.profile_id,
                "selector": selector,
                "step": step_id,
                "stepTitle": step_title,
                "simulated": self._dry_run,
                "attempts": attempts,
                "artifact": artifact,
                "reason": (last_error or {}).get("error", "upload_failed"),
            }
        )
        return ResumeUploadResult(
            status="failed",
            attempts=attempts,
            simulated=self._dry_run,
            selector=selector,
            step_id=step_id,
            step_title=step_title,
            file=self._describe_resume(),
            confirmation=confirmation_payload or {},
            artifact=artifact,
            diagnostics=last_error or {},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _confirm(self, selector: str) -> Dict[str, Any]:
        state_result: BrowserActionResult = self._controller.get_field_state(selector, "file")
        if state_result.status is BrowserActionStatus.OK:
            return dict(state_result.details.get("state", {}))
        return {
            "ok": False,
            "reason": state_result.details.get("error", "unknown"),
        }

    def _is_confirmed(self, confirmation: Mapping[str, Any] | None) -> bool:
        if not confirmation:
            return False
        if confirmation.get("count"):
            return int(confirmation.get("count", 0)) > 0
        files = confirmation.get("files")
        if isinstance(files, Sequence):
            return len(files) > 0
        return False

    def _extract_file_payload(self, result: BrowserActionResult) -> Dict[str, Any]:
        payload = result.details.get("response", {}) if isinstance(result.details, Mapping) else {}
        if isinstance(payload, Mapping) and "file" in payload:
            return dict(payload.get("file", {}))
        return self._describe_resume()

    def _describe_resume(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "name": self._resume_path.name,
            "exists": self._resume_path.exists(),
        }
        try:
            info["sizeBytes"] = self._resume_path.stat().st_size
        except OSError:
            info["sizeBytes"] = None
        sha_path = self._resume_path
        if info["exists"]:
            import hashlib

            digest = hashlib.sha256()
            try:
                with sha_path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(8192), b""):
                        digest.update(chunk)
            except OSError:
                info["sha256"] = None
            else:
                info["sha256"] = digest.hexdigest()
        else:
            info["sha256"] = None
        return info

    def _compute_backoff_seconds(self) -> float:
        low, high = self._wait_range
        if high <= 0:
            return 0.0
        return self._rng.uniform(low, high) / 1000.0

    def _capture_artifact(self, step_id: str, attempt: int) -> str | None:
        html_result = self._controller.get_page_html()
        if html_result.status is not BrowserActionStatus.OK:
            return None
        html = html_result.details.get("html", "")
        if not isinstance(html, str):
            return None
        artifact_path = self._artifacts_dir / f"resume-upload-{step_id}-{attempt}.html"
        artifact_path.write_text(html, encoding="utf-8")
        return str(artifact_path)
