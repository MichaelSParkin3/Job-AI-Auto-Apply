"""Utilities for redacting personally identifiable information from logs."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(
    r"\b(?:\+?\d{1,2}[\s.-]*)?(?:\(?\d{3}\)?[\s.-]*)?\d{3}[\s.-]*\d{4}\b"
)
RESUME_RE = re.compile(r"(?i)resume[^\s]*\.(pdf|docx?)")


def _redact_string(value: str) -> str:
    """Return the string with known PII patterns replaced by placeholders."""

    result = EMAIL_RE.sub("{{REDACTED:EMAIL}}", value)
    result = PHONE_RE.sub("{{REDACTED:PHONE}}", result)
    if RESUME_RE.search(result):
        result = RESUME_RE.sub("{{REDACTED:RESUME_PATH}}", result)
    return result


def redact_value(value: Any) -> Any:
    """Redact PII recursively from arbitrarily nested structures."""

    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    return value


SAFE_KEYS = {
    "id",
    "runId",
    "fingerprint",
    "runPath",
    "artifactsDir",
    "logsPath",
}


def redact_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-redacted copy of an event dictionary."""

    redacted: dict[str, Any] = {}
    for key, value in event.items():
        if key in SAFE_KEYS:
            redacted[key] = value
        else:
            redacted[key] = redact_value(value)
    return redacted


def _hash_text(value: str) -> str:
    """Return a deterministic SHA-256 hash with an explicit prefix."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def prepare_rationale_audit_fields(
    rationale: str | None,
    *,
    max_preview: int = 160,
) -> Dict[str, Any]:
    """Return sanitized metadata describing a decision rationale.

    The returned dictionary includes:
    - ``rationaleHash``: deterministic hash for audit correlation
    - ``rationalePreview``: redacted + truncated preview text (if available)
    - ``rationaleRedacted``: whether redaction modified the preview
    - ``rationaleTruncated``: whether preview was truncated for length
    - ``rationaleLength``: original rationale length in characters
    """

    if not rationale:
        return {
            "rationaleHash": None,
            "rationalePreview": None,
            "rationaleRedacted": False,
            "rationaleTruncated": False,
            "rationaleLength": 0,
        }

    preview_source = _redact_string(rationale)
    truncated = False
    if len(preview_source) > max_preview:
        preview_source = preview_source[: max_preview - 1].rstrip() + "\u2026"
        truncated = True
    return {
        "rationaleHash": _hash_text(rationale),
        "rationalePreview": preview_source or None,
        "rationaleRedacted": preview_source != rationale,
        "rationaleTruncated": truncated,
        "rationaleLength": len(rationale),
    }

