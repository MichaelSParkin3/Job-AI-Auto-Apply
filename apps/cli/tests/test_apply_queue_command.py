import json
import os
import sys
import types
from pathlib import Path

import pytest

try:
    import typer  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    class _TyperExit(Exception):
        def __init__(self, code: int | None = None) -> None:
            super().__init__(code)
            self.code = code

    def _noop(*_args, **_kwargs):  # type: ignore[return-value]
        def _wrapper(func):
            return func

        return _wrapper

    def _option_stub(*_args, **_kwargs):
        return _kwargs.get("default")

    def _secho(message: str, **_kwargs) -> None:
        print(message)

    typer = types.SimpleNamespace(  # type: ignore[assignment]
        Typer=lambda *args, **kwargs: types.SimpleNamespace(
            command=_noop, callback=_noop
        ),
        Option=_option_stub,
        Argument=_option_stub,
        Exit=_TyperExit,
        secho=_secho,
        echo=_secho,
        colors=types.SimpleNamespace(RED="red", GREEN="green", YELLOW="yellow"),
    )
    sys.modules["typer"] = typer  # type: ignore[assignment]

default_yaml = types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {})
sys.modules.setdefault("yaml", default_yaml)  # type: ignore[assignment]
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_a, **_k: None))

try:  # pragma: no cover - optional dependency guard
    import pydantic  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    class _BaseModel:
        def __init__(self, **data) -> None:
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self) -> dict[str, object]:
            return dict(self.__dict__)

    def _field(default=None, **_kwargs):
        return default

    class _ValidationError(Exception):
        def __init__(self, errors=None) -> None:
            super().__init__("validation error")
            self._errors = errors or []

        def errors(self):  # pragma: no cover - compatibility helper
            return list(self._errors)

    def _decorator_factory(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator

    pydantic_module = types.ModuleType("pydantic")
    pydantic_module.BaseModel = _BaseModel
    pydantic_module.Field = _field
    pydantic_module.ValidationError = _ValidationError
    pydantic_module.ConfigDict = dict
    pydantic_module.field_validator = _decorator_factory
    pydantic_module.model_validator = _decorator_factory
    pydantic_module.root_validator = _decorator_factory
    pydantic_module.validator = _decorator_factory
    sys.modules["pydantic"] = pydantic_module

sys.path.insert(0, os.getcwd())

from apps.cli.main import apply_queue  # noqa: E402
from apps.cli.queue_manager import ApplicationCandidate, ReviewQueueManager  # noqa: E402
from apps.cli.run_store import RunStore  # noqa: E402


def _seed_run(tmp_path: Path) -> tuple[RunStore, "RunRecord", ReviewQueueManager]:
    store = RunStore(base=tmp_path)
    record = store.start_demo_run(profile_id="qa-tester")
    manager = ReviewQueueManager(run_store=store, run_record=record)
    return store, record, manager


def test_apply_queue_escalate_overrides_to_human(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("JAA_QUEUE_WATCHDOG_TIMEOUT", "0")

    store, record, manager = _seed_run(tmp_path)

    candidate = ApplicationCandidate(
        id="cand-override",
        posting={"postingUrl": "https://example.com", "title": "Engineer"},
        form_plan_path=None,
        discovered_at="2025-01-01T00:00:00Z",
        state="awaiting_decision",
        assigned_mode="ai",
    )
    manager.enqueue(candidate)
    manager.assign_mode(candidate.id, "ai", trigger="bootstrap")

    apply_queue(run=record.id, candidate=candidate.id, action="escalate")

    queue_payload = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert queue_payload["pending"] == []
    assert queue_payload["escalated"][0]["assignedMode"] == "human"
    assert queue_payload["escalated"][0]["id"] == candidate.id

    run_payload = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    overrides = run_payload.get("overrides") or []
    assert overrides, "queue override entries should be recorded"
    override_entry = overrides[-1]
    assert override_entry["candidateId"] == candidate.id
    assert override_entry["mode"] == "human"

    captured = capsys.readouterr()
    assert "escalated to human lane" in captured.out


def test_apply_queue_assigns_back_to_ai(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("JAA_QUEUE_WATCHDOG_TIMEOUT", "0")

    store, record, manager = _seed_run(tmp_path)

    candidate = ApplicationCandidate(
        id="cand-ai",
        posting={"postingUrl": "https://example.com", "title": "Engineer"},
        form_plan_path=None,
        discovered_at="2025-01-01T00:00:00Z",
        state="awaiting_decision",
    )
    manager.enqueue(candidate)
    manager.assign_mode(candidate.id, "human", trigger="bootstrap", reason="initial")

    apply_queue(run=record.id, candidate=candidate.id, action="assign-ai")

    queue_payload = json.loads(record.queue_path.read_text(encoding="utf-8"))
    assert queue_payload["escalated"] == []
    assert queue_payload["pending"][0]["assignedMode"] == "ai"
    assert queue_payload["pending"][0]["id"] == candidate.id

    run_payload = json.loads(record.run_json_path.read_text(encoding="utf-8"))
    overrides = run_payload.get("overrides") or []
    assert overrides, "override entries should be appended on assign-ai"
    override_entry = overrides[-1]
    assert override_entry["candidateId"] == candidate.id
    assert override_entry["mode"] == "ai"

    captured = capsys.readouterr()
    assert "reassigned to AI lane" in captured.out
