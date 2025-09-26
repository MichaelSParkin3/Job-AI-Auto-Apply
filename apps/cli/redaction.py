"""Utilities for redacting personally identifiable information from logs."""

from __future__ import annotations

import re
from typing import Any


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

