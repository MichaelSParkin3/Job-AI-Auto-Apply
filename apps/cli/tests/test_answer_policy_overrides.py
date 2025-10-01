from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

if "yaml" not in sys.modules:  # pragma: no cover - testing fallback when PyYAML absent
    class _YamlError(Exception):
        pass

    def _safe_load(*_args, **_kwargs):
        return {}

    def _safe_dump(_data, *_args, **_kwargs):
        return "{}\n"

    sys.modules["yaml"] = types.SimpleNamespace(
        safe_load=_safe_load,
        safe_dump=_safe_dump,
        YAMLError=_YamlError,
    )

if "dotenv" not in sys.modules:  # pragma: no cover - optional dependency stub
    sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: False)

from apps.cli.config_loader import Settings
from core.answers import (
    AnswerCache,
    AnswerOrchestrator,
    AnswerRequest,
    AnswerSource,
    FallbackReason,
)


def _init_base(tmp_path: Path) -> Path:
    base = tmp_path / "project"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    return base


def _write_run_stub(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps({"id": run_dir.name}), encoding="utf-8")


def test_cli_overrides_disable_llm_and_persist_policy(tmp_path: Path) -> None:
    base = _init_base(tmp_path)
    overrides = {
        "automation.answerPolicies.allowLLMFallback": False,
        "automation.answerPolicies.minConfidence": 0.9,
        "automation.answerPolicies.model": "openrouter/custom",
    }
    settings = Settings.load(base=base, overrides=overrides)
    policy = settings.base_answer_policy()

    assert policy.allow_llm_fallback is False
    assert policy.min_confidence == pytest.approx(0.9)
    assert policy.model == "openrouter/custom"

    run_dir = base / "runs" / "run-cli"
    _write_run_stub(run_dir)
    orchestrator = AnswerOrchestrator(
        run_id="run-cli",
        run_dir=run_dir,
        policy=policy,
        cache=AnswerCache(),
        draft_client=None,
        telemetry_callback=lambda *_args, **_kwargs: None,
    )

    outcome = orchestrator.draft_answer(
        AnswerRequest(
            run_id="run-cli",
            field_id="summary",
            question="Summary",
            field_type="textarea",
        )
    )

    assert outcome.source is AnswerSource.MANUAL
    assert outcome.fallback_reason is FallbackReason.POLICY_DISABLED

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["answerPolicy"]["allow_llm_fallback"] is False
    assert run_payload["answerPolicy"]["min_confidence"] == pytest.approx(0.9)
    assert run_payload["answerPolicy"]["model"] == "openrouter/custom"
    assert run_payload["answers"], "Expected run.json to record answer outcomes"
    record = run_payload["answers"][0]
    assert record["source"] == "manual"
    assert record.get("cachedFrom") is None
