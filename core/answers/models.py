"""Typed models describing answer drafting requests and outcomes."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Literal, Mapping, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator


class AnswerSource(str, Enum):
    """Origin of an answer returned by the orchestrator."""

    PROFILE = "profile"
    RESUME_FACT = "resume_fact"
    CACHED = "cached"
    LLM = "llm"
    MANUAL = "manual"


class FallbackReason(str, Enum):
    """Enumerate the structured fallback reasons surfaced to telemetry."""

    VALIDATION_FAILED = "validation_failed"
    LOW_CONFIDENCE = "low_confidence"
    POLICY_DISABLED = "policy_disabled"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    MISSING_CONTEXT = "missing_context"


class AnswerPolicy(BaseModel):
    """Governance policy applied when drafting answers."""

    enabled: bool = Field(True, description="Master flag for orchestrator participation")
    min_confidence: float = Field(
        0.75,
        ge=0.0,
        le=1.0,
        description="Minimum confidence required to accept an LLM draft",
    )
    allow_save_to_profile: bool = Field(
        True, description="Whether approved answers can be promoted to profile"
    )
    allow_llm_fallback: bool = Field(
        True, description="Permit contacting an LLM provider when deterministic data missing"
    )
    model: str = Field(
        "openrouter/mistral-small",
        description="Model identifier used for LLM fallbacks",
    )

    @field_validator("model")
    @classmethod
    def _trim_model(cls, value: str) -> str:
        return value.strip()


class AnswerDraftRequest(BaseModel):
    """Payload sent to the LLM provider when drafting an answer."""

    run_id: str
    field_id: str
    question: str
    field_type: Literal["text", "textarea", "select", "multi_select", "url", "email", "phone"]
    validation: Dict[str, Any] = Field(default_factory=dict)
    resume_snippet: str | None = Field(default=None, max_length=750)
    profile_snippet: str | None = Field(default=None, max_length=750)
    locale: str = "en-US"
    timezone: str = "UTC"
    policy: AnswerPolicy


class AnswerDraftResponse(BaseModel):
    """Structured response returned by the LLM provider."""

    value: str
    confidence: float = Field(gt=0.0, lt=1.0)
    rationale: str = Field(default="", max_length=512)
    citations: list[str] | None = None
    tokens: Mapping[str, int] | None = None


class AnswerRequest(BaseModel):
    """Input describing the orchestrator request for a single field."""

    run_id: str
    field_id: str
    question: str
    field_type: Literal["text", "textarea", "select", "multi_select", "url", "email", "phone"]
    validation: Dict[str, Any] = Field(default_factory=dict)
    profile_value: Any | None = None
    resume_value: Any | None = None
    resume_snippet: str | None = None
    profile_snippet: str | None = None
    locale: str = "en-US"
    timezone: str = "UTC"

    @field_validator("field_id", "question")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class AnswerOutcome(BaseModel):
    """Structured payload describing the orchestrator outcome for a field."""

    field_id: str
    value: Any | None
    source: AnswerSource
    cached_from: AnswerSource | None = None
    confidence: float | None = None
    rationale_digest: str | None = None
    policy: AnswerPolicy
    fallback_reason: Optional[FallbackReason] = None
    model: str | None = None
    latency_ms: int | None = None
    tokens: Mapping[str, int] | None = None


class AnswerValidationError(ValidationError):
    """Specialised validation error raised when responses violate field rules."""

    pass
