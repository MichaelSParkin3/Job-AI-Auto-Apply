"""Prompt construction utilities for the answer orchestrator."""

from __future__ import annotations

import json
from typing import Any, Mapping

from apps.cli.redaction import redact_value

from .models import AnswerDraftRequest, AnswerPolicy, AnswerRequest


def _truncate_snippet(value: str | None, *, limit: int = 750) -> str | None:
    if not value:
        return None
    redacted = str(redact_value(value))
    if len(redacted) <= limit:
        return redacted
    return redacted[: limit - 1].rstrip() + "\u2026"


def build_answer_draft_request(
    request: AnswerRequest,
    *,
    policy: AnswerPolicy,
    extra_metadata: Mapping[str, Any] | None = None,
) -> AnswerDraftRequest:
    """Return a validated draft request for the LLM provider."""

    validation = request.validation if isinstance(request.validation, Mapping) else {}
    payload = AnswerDraftRequest(
        run_id=request.run_id,
        field_id=request.field_id,
        question=request.question,
        field_type=request.field_type,
        validation=dict(validation),
        resume_snippet=_truncate_snippet(request.resume_snippet),
        profile_snippet=_truncate_snippet(request.profile_snippet),
        locale=request.locale,
        timezone=request.timezone,
        policy=policy,
    )
    if extra_metadata:
        payload.validation = {**payload.validation, "extra": json.loads(json.dumps(extra_metadata, ensure_ascii=False))}
    return payload
