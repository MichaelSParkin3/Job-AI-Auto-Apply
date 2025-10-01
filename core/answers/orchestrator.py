"""Answer orchestration service enforcing precedence and governance."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, MutableMapping, Protocol

try:  # pragma: no cover - optional dependency for network calls
    import requests
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

from apps.cli.redaction import prepare_rationale_audit_fields, redact_value
from apps.cli.utils import log_event

from .models import (
    AnswerDraftRequest,
    AnswerDraftResponse,
    AnswerOutcome,
    AnswerPolicy,
    AnswerRequest,
    AnswerSource,
    AnswerValidationError,
    FallbackReason,
)
from .prompt import build_answer_draft_request


class AnswerDraftClient(Protocol):
    """Protocol describing an answer drafting client."""

    def draft(self, payload: AnswerDraftRequest) -> AnswerDraftResponse:
        """Return an LLM drafted answer for the provided payload."""


@dataclass
class AnswerCache:
    """In-memory cache storing orchestrator outcomes within a run."""

    store: MutableMapping[str, AnswerOutcome]

    def __init__(self) -> None:
        self.store = {}

    @staticmethod
    def _clone(outcome: AnswerOutcome) -> AnswerOutcome:
        try:
            return outcome.model_copy(deep=True)
        except TypeError:  # pragma: no cover - fallback for test shims without deep kwarg
            return outcome.model_copy()

    def get(self, field_id: str) -> AnswerOutcome | None:
        outcome = self.store.get(field_id)
        if outcome is None:
            return None
        return self._clone(outcome)

    def set(self, field_id: str, outcome: AnswerOutcome) -> None:
        self.store[field_id] = self._clone(outcome)

    def record_feedback(self, field_id: str, *, accepted: bool, value: Any | None = None) -> None:
        """Stub hook for future reviewer feedback integration."""

        outcome = self.store.get(field_id)
        if outcome is None:
            return
        if accepted and value is not None:
            outcome.value = value


class OpenRouterDraftClient:
    """Simple OpenRouter-backed draft client following project conventions."""

    def __init__(self, *, api_key: str, model: str, timeout: float = 8.0) -> None:
        if not api_key:
            raise ValueError("api_key is required for OpenRouterDraftClient")
        if requests is None:  # pragma: no cover - requires optional dependency
            raise RuntimeError("requests package is required for OpenRouterDraftClient")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def draft(self, payload: AnswerDraftRequest) -> AnswerDraftResponse:  # pragma: no cover - network path
        request_payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "input": json.dumps(payload.model_dump(), ensure_ascii=False),
        }
        response = requests.post(  # type: ignore[operator]
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(request_payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        if not message:
            raise RuntimeError("Unexpected OpenRouter payload: missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Unexpected OpenRouter payload: content must be string")
        payload = json.loads(content)
        return AnswerDraftResponse.model_validate(payload)


class AnswerOrchestrator:
    """Coordinate deterministic answers with LLM fallbacks and telemetry."""

    def __init__(
        self,
        *,
        run_id: str,
        run_dir: Path,
        policy: AnswerPolicy,
        cache: AnswerCache | None = None,
        draft_client: AnswerDraftClient | None = None,
        telemetry_callback: Callable[[Mapping[str, Any]], None] = log_event,
    ) -> None:
        self.run_id = run_id
        self.run_dir = Path(run_dir)
        self.policy = policy
        self.cache = cache or AnswerCache()
        self.draft_client = draft_client
        self._telemetry = telemetry_callback
        self._answers_dir = self.run_dir / "answers"
        self._answers_dir.mkdir(parents=True, exist_ok=True)
        self._summary_entries: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def draft_answer(self, request: AnswerRequest) -> AnswerOutcome:
        """Resolve an answer using precedence rules and optional LLM fallback."""

        if request.profile_value not in (None, ""):
            outcome = self._outcome_from_value(
                request=request,
                value=request.profile_value,
                source=AnswerSource.PROFILE,
                confidence=1.0,
            )
            self._emit_skipped(request, reason="profile_answer")
            self._persist_outcome(outcome)
            return outcome

        if request.resume_value not in (None, ""):
            outcome = self._outcome_from_value(
                request=request,
                value=request.resume_value,
                source=AnswerSource.RESUME_FACT,
                confidence=0.9,
            )
            self.cache.set(request.field_id, outcome)
            self._emit_skipped(request, reason="resume_fact")
            self._persist_outcome(outcome)
            return outcome

        cached = self.cache.get(request.field_id)
        if cached is not None:
            original_source = cached.cached_from or cached.source
            reused = cached.model_copy(
                update={
                    "source": AnswerSource.CACHED,
                    "cached_from": original_source,
                }
            )
            self._emit_skipped(request, reason="cached")
            self._persist_outcome(reused)
            return reused

        if not self.policy.enabled:
            outcome = self._fallback_outcome(request, FallbackReason.POLICY_DISABLED)
            self._emit_failure(request, reason="policy_disabled")
            self._persist_outcome(outcome)
            return outcome

        if not self.policy.allow_llm_fallback or self.draft_client is None:
            outcome = self._fallback_outcome(request, FallbackReason.POLICY_DISABLED)
            self._emit_failure(request, reason="policy_disabled")
            self._persist_outcome(outcome)
            return outcome

        draft_request = build_answer_draft_request(request, policy=self.policy)
        start = time.perf_counter()
        try:
            response = self.draft_client.draft(draft_request)
        except TimeoutError:
            outcome = self._fallback_outcome(request, FallbackReason.TIMEOUT)
            self._emit_failure(request, reason="timeout")
            self._persist_outcome(outcome)
            return outcome
        except Exception as exc:  # pragma: no cover - defensive guard
            outcome = self._fallback_outcome(request, FallbackReason.PROVIDER_ERROR)
            self._emit_failure(request, reason=str(exc) or "provider_error")
            self._persist_outcome(outcome)
            return outcome
        latency_ms = int((time.perf_counter() - start) * 1000)

        try:
            self._validate_response(request, response)
        except AnswerValidationError as exc:
            outcome = self._fallback_outcome(
                request,
                FallbackReason.VALIDATION_FAILED,
                rationale=str(exc),
            )
            self._emit_failure(request, reason="validation_failed")
            self._persist_outcome(outcome)
            return outcome

        if response.confidence < self.policy.min_confidence:
            outcome = self._fallback_outcome(request, FallbackReason.LOW_CONFIDENCE)
            self._emit_failure(request, reason="low_confidence")
            self._persist_outcome(outcome)
            return outcome

        outcome = self._outcome_from_value(
            request=request,
            value=response.value,
            source=AnswerSource.LLM,
            confidence=response.confidence,
            rationale=response.rationale,
            latency_ms=latency_ms,
            tokens=response.tokens,
        )
        self.cache.set(request.field_id, outcome)
        self._emit_success(request, outcome)
        self._persist_outcome(outcome)
        return outcome

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _outcome_from_value(
        self,
        *,
        request: AnswerRequest,
        value: Any,
        source: AnswerSource,
        cached_from: AnswerSource | None = None,
        confidence: float | None = None,
        rationale: str | None = None,
        latency_ms: int | None = None,
        tokens: Mapping[str, int] | None = None,
    ) -> AnswerOutcome:
        digest = None
        if rationale:
            audit = prepare_rationale_audit_fields(rationale, max_preview=160)
            digest = audit.get("rationaleHash")
        return AnswerOutcome(
            field_id=request.field_id,
            value=value,
            source=source,
            cached_from=cached_from,
            confidence=confidence,
            rationale_digest=digest,
            policy=self.policy,
            model=self.policy.model,
            latency_ms=latency_ms,
            tokens=tokens,
        )

    def _fallback_outcome(
        self,
        request: AnswerRequest,
        reason: FallbackReason,
        rationale: str | None = None,
    ) -> AnswerOutcome:
        outcome = AnswerOutcome(
            field_id=request.field_id,
            value=None,
            source=AnswerSource.MANUAL,
            confidence=None,
            rationale_digest=None,
            policy=self.policy,
            fallback_reason=reason,
            model=self.policy.model,
        )
        if rationale:
            audit = prepare_rationale_audit_fields(rationale, max_preview=120)
            outcome.rationale_digest = audit.get("rationaleHash")
        return outcome

    def _value_hash(self, value: Any) -> str:
        serialized = json.dumps(redact_value(value), ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _persist_outcome(self, outcome: AnswerOutcome) -> None:
        drafted_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        artifact = {
            "fieldId": outcome.field_id,
            "source": outcome.source.value,
            "cachedFrom": outcome.cached_from.value if outcome.cached_from else None,
            "valueHash": self._value_hash(outcome.value) if outcome.value is not None else None,
            "valueLength": len(str(outcome.value)) if outcome.value is not None else 0,
            "confidence": outcome.confidence,
            "rationaleDigest": outcome.rationale_digest,
            "policy": outcome.policy.model_dump(),
            "model": outcome.model,
            "fallbackReason": outcome.fallback_reason.value if outcome.fallback_reason else None,
            "latencyMs": outcome.latency_ms,
            "draftedAt": drafted_at,
        }
        artifact_path = self._answers_dir / f"{outcome.field_id}.json"
        artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        markdown_path = self._write_field_markdown(outcome, artifact)
        self._summary_entries = [entry for entry in self._summary_entries if entry.get("fieldId") != outcome.field_id]
        summary_entry = {
            "fieldId": outcome.field_id,
            "source": outcome.source.value,
            "cachedFrom": artifact["cachedFrom"],
            "valueHash": artifact["valueHash"],
            "confidence": outcome.confidence,
            "fallback": artifact["fallbackReason"],
        }
        self._summary_entries.append(summary_entry)
        self._write_summary()
        self._update_run_json(outcome, artifact_path, markdown_path, drafted_at)

    def _write_field_markdown(self, outcome: AnswerOutcome, artifact: Mapping[str, Any]) -> Path:
        """Persist reviewer friendly markdown without exposing raw values."""

        lines = [f"# Drafted Answer: `{outcome.field_id}`", ""]
        lines.append("| Attribute | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| Source | `{artifact['source']}` |")
        confidence = artifact.get("confidence")
        if confidence is None:
            lines.append("| Confidence | _n/a_ |")
        else:
            lines.append(f"| Confidence | `{confidence:.2f}` |")
        value_hash = artifact.get("valueHash")
        if value_hash:
            lines.append(f"| Value Hash | `{value_hash}` |")
        else:
            lines.append("| Value Hash | _none_ |")
        lines.append(f"| Value Length | `{artifact.get('valueLength', 0)}` |")
        if artifact.get("rationaleDigest"):
            lines.append(f"| Rationale Digest | `{artifact['rationaleDigest']}` |")
        if artifact.get("fallbackReason"):
            lines.append(f"| Fallback Reason | `{artifact['fallbackReason']}` |")
        if artifact.get("cachedFrom"):
            lines.append(f"| Cached From | `{artifact['cachedFrom']}` |")
        if outcome.latency_ms is not None:
            lines.append(f"| Latency (ms) | `{outcome.latency_ms}` |")
        if outcome.tokens:
            token_pairs = ", ".join(f"{name}={count}" for name, count in sorted(outcome.tokens.items()))
            lines.append(f"| Tokens | `{token_pairs}` |")
        lines.append(f"| Drafted At | `{artifact['draftedAt']}` |")
        policy_snapshot = json.dumps(outcome.policy.model_dump(), indent=2, ensure_ascii=False)
        lines.extend(["", "## Policy Snapshot", "", "```json", policy_snapshot, "```"])
        markdown_path = self._answers_dir / f"{outcome.field_id}.md"
        markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return markdown_path

    def _write_summary(self) -> None:
        lines = ["# Drafted Answers", ""]
        for entry in sorted(self._summary_entries, key=lambda item: item["fieldId"]):
            description = f"- **{entry['fieldId']}** → {entry['source']}"
            if entry.get("confidence") is not None:
                description += f" (confidence={entry['confidence']:.2f})"
            if entry.get("cachedFrom"):
                description += f" ← {entry['cachedFrom']}"
            if entry.get("fallback"):
                description += f" — fallback: {entry['fallback']}"
            if entry.get("valueHash"):
                description += f" — hash={entry['valueHash'][:12]}"
            lines.append(description)
        summary_path = self._answers_dir / "summary.md"
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _update_run_json(
        self,
        outcome: AnswerOutcome,
        artifact_path: Path,
        markdown_path: Path,
        drafted_at: str,
    ) -> None:
        run_json_path = self.run_dir / "run.json"
        if not run_json_path.exists():
            return
        payload = json.loads(run_json_path.read_text(encoding="utf-8"))
        answers = payload.setdefault("answers", [])
        new_record = {
            "fieldId": outcome.field_id,
            "valueHash": self._value_hash(outcome.value) if outcome.value is not None else None,
            "source": outcome.source.value,
            "cachedFrom": outcome.cached_from.value if outcome.cached_from else None,
            "confidence": outcome.confidence,
            "rationaleDigest": outcome.rationale_digest,
            "model": outcome.model,
            "latencyMs": outcome.latency_ms,
            "fallbackReason": outcome.fallback_reason.value if outcome.fallback_reason else None,
            "artifactPath": artifact_path.relative_to(self.run_dir).as_posix(),
            "markdownPath": markdown_path.relative_to(self.run_dir).as_posix(),
            "draftedAt": drafted_at,
        }
        answers = [record for record in answers if record.get("fieldId") != outcome.field_id]
        answers.append(new_record)
        payload["answers"] = answers
        payload["answerPolicy"] = outcome.policy.model_dump()
        artifacts = payload.setdefault("artifacts", {})
        answers_artifacts = artifacts.setdefault("answers", {})
        answers_artifacts["summary"] = (self._answers_dir / "summary.md").relative_to(self.run_dir).as_posix()
        fields_artifacts = answers_artifacts.setdefault("fields", {})
        fields_artifacts[outcome.field_id] = markdown_path.relative_to(self.run_dir).as_posix()
        run_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _emit_skipped(self, request: AnswerRequest, *, reason: str) -> None:
        self._telemetry(
            {
                "event": "AI_FIELD_DRAFT_SKIPPED",
                "runId": self.run_id,
                "fieldId": request.field_id,
                "reason": reason,
                "policy": self.policy.model_dump(),
            }
        )

    def _emit_success(self, request: AnswerRequest, outcome: AnswerOutcome) -> None:
        payload = {
            "event": "AI_FIELD_DRAFTED",
            "runId": self.run_id,
            "fieldId": request.field_id,
            "source": outcome.source.value,
            "model": outcome.model,
            "latencyMs": outcome.latency_ms,
            "confidence": outcome.confidence,
            "policy": self.policy.model_dump(),
        }
        if outcome.tokens:
            payload["tokens"] = dict(outcome.tokens)
        self._telemetry(payload)

    def _emit_failure(self, request: AnswerRequest, *, reason: str) -> None:
        self._telemetry(
            {
                "event": "AI_FIELD_DRAFT_FAILED",
                "runId": self.run_id,
                "fieldId": request.field_id,
                "reason": reason,
                "policy": self.policy.model_dump(),
            }
        )

    def _validate_response(self, request: AnswerRequest, response: AnswerDraftResponse) -> None:
        rules = request.validation or {}
        value = response.value
        if rules.get("max_length") is not None:
            max_length = int(rules["max_length"])
            if len(value) > max_length:
                raise AnswerValidationError(
                    [
                        {
                            "loc": ("value",),
                            "msg": f"value exceeds max_length {max_length}",
                            "type": "value_error.length",
                        }
                    ],
                    AnswerDraftResponse,
                )
        if rules.get("regex"):
            import re

            pattern = str(rules["regex"])
            if not re.fullmatch(pattern, value):
                raise AnswerValidationError(
                    [
                        {
                            "loc": ("value",),
                            "msg": "value does not match regex",
                            "type": "value_error.regex",
                        }
                    ],
                    AnswerDraftResponse,
                )
        allowed = rules.get("allowed_values")
        if isinstance(allowed, (list, tuple, set)) and allowed:
            allowed_normalized = {str(item).strip().casefold() for item in allowed}
            if value.strip().casefold() not in allowed_normalized:
                raise AnswerValidationError(
                    [
                        {
                            "loc": ("value",),
                            "msg": "value not in allowed_values",
                            "type": "value_error.enum",
                        }
                    ],
                    AnswerDraftResponse,
                )
