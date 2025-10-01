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

        def model_copy(self, update: dict[str, object] | None = None):
            payload = self.model_dump()
            if update:
                payload.update(update)
            return self.__class__(**payload)

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
)


class _StubDraftClient:
    def __init__(self, value: str = "AI value", confidence: float = 0.92) -> None:
        self.value = value
        self.confidence = confidence
        self.calls: list[AnswerDraftRequest] = []

    def draft(self, payload: AnswerDraftRequest) -> AnswerDraftResponse:
        self.calls.append(payload)
        return AnswerDraftResponse(
            value=self.value,
            confidence=self.confidence,
            rationale="Generated",  # noqa: S106 - test string
            citations=["resume"],
            tokens={"prompt": 120, "completion": 80},
        )


def _write_run_stub(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "run.json").write_text(json.dumps({"id": "run-1"}), encoding="utf-8")


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    root = tmp_path / "runs" / "run-1"
    _write_run_stub(root)
    return root


def test_answer_orchestrator_precedence(run_dir: Path) -> None:
    events: list[dict[str, object]] = []
    policy = AnswerPolicy(
        enabled=True,
        min_confidence=0.75,
        allow_save_to_profile=True,
        allow_llm_fallback=True,
        model="stub-model",
    )
    orchestrator = AnswerOrchestrator(
        run_id="run-1",
        run_dir=run_dir,
        policy=policy,
        cache=AnswerCache(),
        draft_client=None,
        telemetry_callback=events.append,
    )

    profile_request = AnswerRequest(
        run_id="run-1",
        field_id="fullName",
        question="Full name",
        field_type="text",
        validation={},
        profile_value="Ada Lovelace",
        resume_value=None,
    )
    profile_outcome = orchestrator.draft_answer(profile_request)
    assert profile_outcome.source is AnswerSource.PROFILE
    assert any(event["event"] == "AI_FIELD_DRAFT_SKIPPED" for event in events)
    profile_markdown = run_dir / "answers" / "fullName.md"
    assert profile_markdown.exists(), "Expected per-field markdown artifact"

    resume_request = AnswerRequest(
        run_id="run-1",
        field_id="portfolioUrl",
        question="Portfolio",
        field_type="url",
        validation={},
        resume_value="https://example.com",
    )
    resume_outcome = orchestrator.draft_answer(resume_request)
    assert resume_outcome.source is AnswerSource.RESUME_FACT

    cached_outcome = resume_outcome.model_copy(update={"field_id": "linkedinUrl"})
    orchestrator.cache.set("linkedinUrl", cached_outcome)
    cached_request = AnswerRequest(
        run_id="run-1",
        field_id="linkedinUrl",
        question="LinkedIn",
        field_type="url",
        validation={},
    )
    cached_result = orchestrator.draft_answer(cached_request)
    assert cached_result.source is AnswerSource.RESUME_FACT

    summary_path = run_dir / "answers" / "summary.md"
    assert summary_path.exists(), "Expected summary markdown artifact"
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["answerPolicy"]["model"] == policy.model
    assert any(entry["fieldId"] == "fullName" for entry in run_payload["answers"])
    markdown_paths = {entry["fieldId"]: entry["markdownPath"] for entry in run_payload["answers"]}
    assert markdown_paths["fullName"].endswith("answers/fullName.md")
    assert run_payload["artifacts"]["answers"]["fields"]["fullName"].endswith("answers/fullName.md")


def test_answer_orchestrator_llm_success(tmp_path: Path) -> None:
    root = tmp_path / "runs" / "run-2"
    _write_run_stub(root)
    events: list[dict[str, object]] = []
    policy = AnswerPolicy(
        enabled=True,
        min_confidence=0.5,
        allow_save_to_profile=True,
        allow_llm_fallback=True,
        model="stub-model",
    )
    stub_client = _StubDraftClient()
    orchestrator = AnswerOrchestrator(
        run_id="run-2",
        run_dir=root,
        policy=policy,
        cache=AnswerCache(),
        draft_client=stub_client,
        telemetry_callback=events.append,
    )

    request = AnswerRequest(
        run_id="run-2",
        field_id="summary",
        question="Tell us about yourself",
        field_type="textarea",
        validation={"max_length": 2000},
    )
    outcome = orchestrator.draft_answer(request)
    assert outcome.source is AnswerSource.LLM
    assert outcome.value == "AI value"
    assert any(event["event"] == "AI_FIELD_DRAFTED" for event in events)
    artifact_path = root / "answers" / "summary.json"
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert len(artifact["valueHash"]) == 64
