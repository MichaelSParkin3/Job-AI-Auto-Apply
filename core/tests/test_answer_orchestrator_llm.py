import json
import os
import sys
import types
from pathlib import Path

import pytest

if "pydantic" not in sys.modules:  # pragma: no cover - optional dependency stub
    class _BaseModel:
        def __init__(self, **data) -> None:
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self) -> dict[str, object]:
            return dict(self.__dict__)

    def _identity(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    class _ValidationError(Exception):
        pass

    def _field(default=None, *_args, **_kwargs):
        return default

    sys.modules["pydantic"] = types.SimpleNamespace(
        BaseModel=_BaseModel,
        Field=_field,
        ValidationError=_ValidationError,
        field_validator=_identity,
    )

sys.path.insert(0, os.getcwd())

from core.answers import (
    AnswerCache,
    AnswerDraftRequest,
    AnswerDraftResponse,
    AnswerOrchestrator,
    AnswerPolicy,
    AnswerRequest,
    AnswerSource,
    FallbackReason,
)


class _LowConfidenceClient:
    def draft(self, payload: AnswerDraftRequest) -> AnswerDraftResponse:
        return AnswerDraftResponse(
            value="too risky",
            confidence=0.2,
            rationale="Uncertain",
        )


class _TimeoutClient:
    def draft(self, payload: AnswerDraftRequest) -> AnswerDraftResponse:
        raise TimeoutError("network timeout")


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    root = tmp_path / "runs" / "run-3"
    root.mkdir(parents=True, exist_ok=True)
    (root / "run.json").write_text(json.dumps({"id": "run-3"}), encoding="utf-8")
    return root


def test_low_confidence_falls_back(run_dir: Path) -> None:
    events: list[dict[str, object]] = []
    policy = AnswerPolicy(
        enabled=True,
        min_confidence=0.6,
        allow_save_to_profile=True,
        allow_llm_fallback=True,
        model="stub-model",
    )
    orchestrator = AnswerOrchestrator(
        run_id="run-3",
        run_dir=run_dir,
        policy=policy,
        cache=AnswerCache(),
        draft_client=_LowConfidenceClient(),
        telemetry_callback=events.append,
    )
    request = AnswerRequest(
        run_id="run-3",
        field_id="coverLetter",
        question="Cover letter",
        field_type="textarea",
    )
    outcome = orchestrator.draft_answer(request)
    assert outcome.value is None
    assert outcome.source is AnswerSource.MANUAL
    assert outcome.fallback_reason is FallbackReason.LOW_CONFIDENCE
    assert any(event["event"] == "AI_FIELD_DRAFT_FAILED" for event in events)
    markdown_path = run_dir / "answers" / "coverLetter.md"
    assert markdown_path.exists()


def test_timeout_emits_failure(run_dir: Path) -> None:
    events: list[dict[str, object]] = []
    policy = AnswerPolicy(
        enabled=True,
        min_confidence=0.75,
        allow_save_to_profile=True,
        allow_llm_fallback=True,
        model="stub-model",
    )
    orchestrator = AnswerOrchestrator(
        run_id="run-3",
        run_dir=run_dir,
        policy=policy,
        cache=AnswerCache(),
        draft_client=_TimeoutClient(),
        telemetry_callback=events.append,
    )
    request = AnswerRequest(
        run_id="run-3",
        field_id="availability",
        question="Availability",
        field_type="text",
    )
    outcome = orchestrator.draft_answer(request)
    assert outcome.value is None
    assert outcome.fallback_reason in {
        FallbackReason.TIMEOUT,
        FallbackReason.PROVIDER_ERROR,
    }
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    entry = next(item for item in run_payload["answers"] if item["fieldId"] == "availability")
    assert entry["fallbackReason"] in {"timeout", "provider_error"}
    assert entry["markdownPath"].endswith("answers/availability.md")
