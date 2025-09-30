"""Autofill planner orchestration for Lever form plans."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence

try:  # pragma: no cover - optional dependency when requests is installed
    import requests
except ModuleNotFoundError:  # pragma: no cover - keep lightweight default
    requests = None  # type: ignore[assignment]

from sites.lever.form_executor import LeverFieldPlan, LeverFormPlan


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AutofillIntent:
    """Normalized intent for executing a form fill instruction."""

    key: str
    label: str
    selector: str
    value_key: str
    field_type: str
    strategy: str
    confidence: float
    fallback_selector: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlannerTelemetry:
    """Telemetry emitted after preparing an autofill plan."""

    token_usage: Dict[str, int]
    latency_ms: int
    average_confidence: float
    min_confidence: float
    max_confidence: float


@dataclass(slots=True)
class PromptRecord:
    """Prompt/response bundle for audit persistence."""

    prompt: str
    response: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AutofillPlanResult:
    """Outcome of orchestrating an enriched autofill plan."""

    intents: List[AutofillIntent]
    llm_used: bool
    telemetry: PlannerTelemetry
    prompt_records: List[PromptRecord]


@dataclass(slots=True)
class AutofillPlannerConfig:
    """Configuration for orchestrating enriched autofill plans."""

    model: str
    enable_llm: bool
    max_dom_chars: int = 4000


class PlannerLLMClient(Protocol):
    """Protocol describing an LLM client that returns structured planner output."""

    def generate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a structured response for the provided payload."""


class OpenRouterPlannerClient:
    """Simple OpenRouter client for planner prompts."""

    def __init__(self, *, api_key: str, model: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("api_key is required for OpenRouterPlannerClient")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:  # pragma: no cover - network path
        if requests is None:
            raise RuntimeError("requests library is required for OpenRouterPlannerClient")
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("payload must include chat messages")
        request_payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
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
        payload = response.json()
        return payload


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class AutofillPlannerOrchestrator:
    """Compose deterministic selectors with optional LLM guidance."""

    def __init__(
        self,
        *,
        config: AutofillPlannerConfig,
        llm_client: PlannerLLMClient | None,
    ) -> None:
        self.config = config
        self._llm_client = llm_client

    def build_plan(
        self,
        *,
        candidate_id: str,
        dom_html: str,
        plan: LeverFormPlan,
        answer_metadata: Mapping[str, Mapping[str, Any]],
    ) -> AutofillPlanResult:
        """Return enriched intents for the provided Lever plan."""

        fallback_intents = [
            self._fallback_intent(field, answer_metadata.get(field.value_key))
            for field in plan.fields
        ]
        prompt_records: List[PromptRecord] = []
        llm_used = False
        token_usage: Dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}
        latency_ms = 0
        intents = fallback_intents

        if self.config.enable_llm and self._llm_client and plan.fields:
            request_payload = self._build_payload(candidate_id, dom_html, plan, answer_metadata)
            prompt_records.append(
                PromptRecord(
                    prompt=json.dumps(request_payload["messages"], indent=2, ensure_ascii=False),
                    response="",
                    metadata={"model": self.config.model, "candidateId": candidate_id},
                )
            )
            start = time.perf_counter()
            try:
                response_payload = self._llm_client.generate(request_payload)
            except Exception as exc:  # pragma: no cover - defensive guard
                prompt_records[-1].metadata.setdefault("error", str(exc))
                response_payload = {}
            latency_ms = int((time.perf_counter() - start) * 1000)
            parsed = self._parse_response(response_payload)
            if parsed["intents"]:
                llm_used = True
                intents = self._merge_intents(
                    fallback_intents,
                    parsed["intents"],
                    answer_metadata,
                )
                token_usage = parsed["token_usage"]
                prompt_records[-1].response = json.dumps(
                    parsed["raw_intents"], indent=2, ensure_ascii=False
                )
            else:
                prompt_records[-1].response = json.dumps(
                    {"fallback": True, "reason": parsed["error"]},
                    indent=2,
                    ensure_ascii=False,
                )

        telemetry = self._telemetry_from_intents(intents, token_usage, latency_ms)
        if prompt_records and not prompt_records[-1].response:
            prompt_records[-1].response = json.dumps(
                {"fallback": True, "reason": "no_response"}, indent=2, ensure_ascii=False
            )
        return AutofillPlanResult(
            intents=intents,
            llm_used=llm_used,
            telemetry=telemetry,
            prompt_records=prompt_records,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fallback_intent(
        self,
        field: LeverFieldPlan,
        answer_info: Mapping[str, Any] | None,
    ) -> AutofillIntent:
        strategy = "deterministic_selector"
        confidence = 0.55
        metadata: Dict[str, Any] = {}
        if answer_info:
            status = str(answer_info.get("status"))
            source = str(answer_info.get("source")) if answer_info.get("source") else None
            if status == "resolved":
                metadata["answerSource"] = source or "profile"
                if source == "qa_override":
                    strategy = "profile_override"
                    confidence = 1.0
                else:
                    strategy = "profile_answer"
                    confidence = 0.9
        return AutofillIntent(
            key=_normalized_key(field.label, field.value_key),
            label=field.label,
            selector=field.selector,
            value_key=field.value_key,
            field_type=_infer_field_type(field.value_key, field.label),
            strategy=strategy,
            confidence=confidence,
            fallback_selector=field.selector,
            metadata=metadata,
        )

    def _build_payload(
        self,
        candidate_id: str,
        dom_html: str,
        plan: LeverFormPlan,
        answer_metadata: Mapping[str, Mapping[str, Any]],
    ) -> Dict[str, Any]:
        truncated_dom = (dom_html or "")[: self.config.max_dom_chars]
        fields_payload = [
            {
                "key": field.value_key,
                "label": field.label,
                "selector": field.selector,
                "answer": answer_metadata.get(field.value_key, {}),
            }
            for field in plan.fields
        ]
        system_prompt = (
            "You are an assistant that converts Lever job application DOM snapshots into "
            "structured autofill intents. Return strict JSON with a top-level 'intents' array."
        )
        user_payload = {
            "candidateId": candidate_id,
            "fields": fields_payload,
            "domExcerpt": truncated_dom,
        }
        return {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
        }

    def _parse_response(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        intents_payload: Sequence[Mapping[str, Any]] = []
        error = None
        if isinstance(payload, Mapping):
            try:
                choices = payload.get("choices") or []
                if choices:
                    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
                    if message and isinstance(message.get("content"), str):
                        content = message["content"].strip()
                        parsed = json.loads(content) if content else {}
                        raw_intents = parsed.get("intents")
                        if isinstance(raw_intents, list):
                            intents_payload = [
                                item for item in raw_intents if isinstance(item, Mapping)
                            ]
                        else:
                            error = "intents_missing"
                    else:
                        error = "message_missing"
                else:
                    error = "choices_missing"
            except json.JSONDecodeError as exc:
                error = f"invalid_json:{exc}"  # pragma: no cover - defensive parsing
        usage_payload = payload.get("usage") if isinstance(payload, Mapping) else {}
        token_usage = {
            "prompt": int(usage_payload.get("prompt_tokens", 0))
            if isinstance(usage_payload, Mapping)
            else 0,
            "completion": int(usage_payload.get("completion_tokens", 0))
            if isinstance(usage_payload, Mapping)
            else 0,
        }
        token_usage["total"] = token_usage["prompt"] + token_usage["completion"]
        return {
            "intents": intents_payload,
            "token_usage": token_usage,
            "raw_intents": intents_payload,
            "error": error,
        }

    def _merge_intents(
        self,
        fallback: Sequence[AutofillIntent],
        llm_intents: Sequence[Mapping[str, Any]],
        answer_metadata: Mapping[str, Mapping[str, Any]],
    ) -> List[AutofillIntent]:
        merged: List[AutofillIntent] = []
        llm_index: Dict[str, Mapping[str, Any]] = {}
        for entry in llm_intents:
            key = entry.get("key") or entry.get("value_key") or entry.get("field")
            if isinstance(key, str):
                llm_index[key] = entry
        for fallback_intent in fallback:
            source_key = fallback_intent.value_key
            llm_entry = llm_index.get(source_key) or llm_index.get(fallback_intent.key)
            if llm_entry:
                strategy = str(llm_entry.get("strategy") or fallback_intent.strategy)
                confidence = _clamp_float(llm_entry.get("confidence"), fallback_intent.confidence)
                field_type = str(llm_entry.get("field_type") or fallback_intent.field_type)
                fallback_selector = str(
                    llm_entry.get("fallback_selector") or fallback_intent.fallback_selector
                )
                metadata = dict(fallback_intent.metadata)
                metadata.update(
                    {
                        key: value
                        for key, value in llm_entry.items()
                        if key not in {"key", "strategy", "confidence", "field_type", "fallback_selector"}
                    }
                )
                merged_intent = AutofillIntent(
                    key=fallback_intent.key,
                    label=fallback_intent.label,
                    selector=fallback_intent.selector,
                    value_key=fallback_intent.value_key,
                    field_type=field_type,
                    strategy=strategy,
                    confidence=confidence,
                    fallback_selector=fallback_selector,
                    metadata=metadata,
                )
            else:
                merged_intent = fallback_intent
            answer_info = answer_metadata.get(fallback_intent.value_key)
            if answer_info and answer_info.get("status") == "resolved":
                source = answer_info.get("source")
                if source == "qa_override":
                    merged_intent.strategy = "profile_override"
                    merged_intent.confidence = 1.0
                else:
                    merged_intent.strategy = "profile_answer"
                    merged_intent.confidence = max(merged_intent.confidence, 0.9)
                merged_intent.metadata.setdefault("answerSource", source)
            merged.append(merged_intent)
        return merged

    def _telemetry_from_intents(
        self,
        intents: Sequence[AutofillIntent],
        token_usage: Mapping[str, int],
        latency_ms: int,
    ) -> PlannerTelemetry:
        confidences = [intent.confidence for intent in intents]
        if confidences:
            average = sum(confidences) / len(confidences)
            min_conf = min(confidences)
            max_conf = max(confidences)
        else:
            average = 0.0
            min_conf = 0.0
            max_conf = 0.0
        return PlannerTelemetry(
            token_usage={
                "prompt": int(token_usage.get("prompt", 0)),
                "completion": int(token_usage.get("completion", 0)),
                "total": int(token_usage.get("total", 0)),
            },
            latency_ms=int(latency_ms),
            average_confidence=round(average, 4),
            min_confidence=round(min_conf, 4),
            max_confidence=round(max_conf, 4),
        )


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _normalized_key(label: str, fallback: str) -> str:
    base = label.strip().lower().replace(" ", "_") if label else ""
    return base or fallback


def _infer_field_type(value_key: str, label: str) -> str:
    candidates = [value_key or "", label or ""]
    combined = " ".join(candidates).lower()
    if "email" in combined:
        return "email"
    if "phone" in combined:
        return "phone"
    if any(token in combined for token in ("resume", "upload")):
        return "file"
    if any(token in combined for token in ("cover", "summary")):
        return "textarea"
    return "text"


def _clamp_float(value: Any, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(numeric) or math.isinf(numeric):
        return default
    return max(0.0, min(1.0, numeric))

