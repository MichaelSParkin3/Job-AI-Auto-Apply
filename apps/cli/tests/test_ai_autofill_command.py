import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.getcwd())

try:  # pragma: no cover - optional dependency guard
    import typer  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _TyperExit(Exception):
        def __init__(self, code: int | None = None) -> None:
            super().__init__(code)
            self.code = code

    def _identity_decorator(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator

    def _option_stub(*_args, **_kwargs):
        return _kwargs.get("default")

    def _echo_stub(message: str, **_kwargs) -> None:
        print(message)

    typer = types.SimpleNamespace(  # type: ignore[assignment]
        Typer=lambda *args, **kwargs: types.SimpleNamespace(
            command=_identity_decorator,
            callback=_identity_decorator,
        ),
        Option=_option_stub,
        Argument=_option_stub,
        Exit=_TyperExit,
        secho=_echo_stub,
        echo=_echo_stub,
        colors=types.SimpleNamespace(RED="red", GREEN="green", YELLOW="yellow"),
    )
    sys.modules["typer"] = typer  # type: ignore[assignment]

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    sys.modules["yaml"] = types.SimpleNamespace(
        safe_load=lambda *_args, **_kwargs: {},
        safe_dump=lambda *_args, **_kwargs: "{}\n",
    )

try:
    import dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: False)

try:
    import portalocker  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _PortalockerLock:
        def __init__(self, path, mode, *, flags=None):
            self._path = path
            self._mode = mode
            self._handle = None

        def __enter__(self):
            self._handle = open(self._path, self._mode)
            return self._handle

        def __exit__(self, exc_type, exc, tb) -> None:
            if self._handle:
                self._handle.close()

    sys.modules["portalocker"] = types.SimpleNamespace(
        LockFlags=types.SimpleNamespace(EXCLUSIVE=1),
        Lock=lambda path, mode, **kwargs: _PortalockerLock(path, mode, **kwargs),
    )

try:  # pragma: no cover
    import bs4  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _Tag:
        pass

    class _BeautifulSoup:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def select(self, *_args, **_kwargs):
            return []

        def find_all(self, *_args, **_kwargs):
            return []

    bs4_module = types.ModuleType("bs4")
    bs4_module.BeautifulSoup = _BeautifulSoup
    bs4_module.Tag = _Tag
    sys.modules["bs4"] = bs4_module

try:  # pragma: no cover
    import fastapi  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _FastAPIState(types.SimpleNamespace):
        pass

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: object | None = None) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:  # type: ignore[override]
        def __init__(self, *args, **kwargs) -> None:
            self.state = _FastAPIState()
            self._routes: dict[tuple[str, str], callable] = {}

        def mount(self, *_args, **_kwargs) -> None:
            return None

        def get(self, path: str, **_kwargs):
            def decorator(func):
                self._routes[("GET", path)] = func
                return func

            return decorator

        def post(self, path: str, **_kwargs):
            def decorator(func):
                self._routes[("POST", path)] = func
                return func

            return decorator

    class FileResponse:  # pragma: no cover
        def __init__(self, path: Path | str, *args, **kwargs) -> None:
            self.path = Path(path)

    class StaticFiles:  # pragma: no cover
        def __init__(self, *args, **kwargs) -> None:
            pass

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.FastAPI = FastAPI
    fastapi_module.HTTPException = HTTPException
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.FileResponse = FileResponse
    fastapi_responses.JSONResponse = lambda *args, **kwargs: None
    fastapi_staticfiles = types.ModuleType("fastapi.staticfiles")
    fastapi_staticfiles.StaticFiles = StaticFiles
    fastapi_module.responses = fastapi_responses
    fastapi_module.staticfiles = fastapi_staticfiles
    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.responses"] = fastapi_responses
    sys.modules["fastapi.staticfiles"] = fastapi_staticfiles

try:  # pragma: no cover
    import pydantic  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _BaseModel:
        def __init__(self, **data) -> None:
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self) -> dict[str, object]:
            return self.__dict__.copy()

        @classmethod
        def model_validate(cls, data):
            if isinstance(data, dict):
                return cls(**data)
            raise TypeError("Unsupported data type")

    def _field(default=None, **_kwargs):
        return default

    class ValidationError(Exception):
        pass

    def _validator(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    pydantic_module = types.ModuleType("pydantic")
    pydantic_module.BaseModel = _BaseModel
    pydantic_module.Field = _field
    pydantic_module.ValidationError = ValidationError
    pydantic_module.ConfigDict = dict
    pydantic_module.field_validator = _validator
    pydantic_module.model_validator = _validator
    pydantic_module.root_validator = _validator
    pydantic_module.validator = _validator
    sys.modules["pydantic"] = pydantic_module

from apps.browser import BrowserActionResult, BrowserActionStatus  # noqa: E402
from apps.cli.main import apply_run  # noqa: E402


class StubAutofillExecutor:
    last_instance: object | None = None

    def __init__(self, *, controller, run_dir, telemetry_callback, dry_run):
        self.controller = controller
        self.run_dir = run_dir
        self.telemetry_callback = telemetry_callback
        self.dry_run = dry_run
        self.last_plan = None
        self.last_answers = None
        StubAutofillExecutor.last_instance = self

    def execute(self, plan, *, answers, validate_prefilled=False):
        self.last_plan = plan
        self.last_answers = answers

        class _Result:
            def __init__(self, candidate_id: str) -> None:
                self._candidate_id = candidate_id

            def to_payload(self) -> dict[str, object]:
                return {
                    "candidateId": self._candidate_id,
                    "filled": 1,
                    "skipped": 0,
                    "fields": [],
                }

            def filled(self) -> int:
                return 1

            def skipped(self) -> int:
                return 0

        return _Result(plan.candidate_id)


class StubNavigator:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def open_result(self, result, *, idle_timeout: float = 6.0):  # noqa: D401
        from sites.lever.navigation import LeverNavigationOutcome

        return LeverNavigationOutcome(
            result=result,
            status="ok",
            landing_url=result.href,
            html="<html><body><form id='application-form'></form></body></html>",
        )


class StubPlanner:
    def plan_from_html(self, _html: str):
        from sites.lever.form_executor import LeverFieldPlan, LeverFormPlan

        return LeverFormPlan(
            fields=[
                LeverFieldPlan(
                    label="Full name",
                    selector="input#name",
                    value_key="fullName",
                )
            ]
        )


class StubPlannerLoader:
    def __call__(self, *_args, **_kwargs):
        return StubPlanner()


class StubPlannerOrchestrator:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def build_plan(self, *, candidate_id: str, dom_html: str, plan, answer_metadata):
        from core.autofill.planner import AutofillIntent, AutofillPlanResult, PlannerTelemetry

        intents = [
            AutofillIntent(
                key="fullName",
                label="Full name",
                selector="input#name",
                value_key="fullName",
                field_type="text",
                strategy="profile_answer",
                confidence=1.0,
                fallback_selector="",
                metadata={},
            )
        ]
        telemetry = PlannerTelemetry(
            token_usage={"prompt": 0, "completion": 0, "total": 0},
            latency_ms=10,
            average_confidence=1.0,
            min_confidence=1.0,
            max_confidence=1.0,
        )
        return AutofillPlanResult(
            intents=intents,
            llm_used=False,
            telemetry=telemetry,
            prompt_records=[],
        )


class StubFormExecutor:
    def execute(self, _plan, *, profile_answers):
        return {"filled": [], "skipped": [], "resumeSelector": "#resume"}


class StubResumeUploader:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def upload(self, *args, **kwargs):
        class _Result:
            status = "simulated"

            def to_payload(self) -> dict[str, object]:
                return {"status": "simulated"}

            def telemetry_payload(self) -> dict[str, object]:
                return {"status": "simulated"}

        return _Result()


class StubSummaryPayload:
    def to_preview_payload(self) -> dict[str, object]:
        return {"headline": {}, "form": {}, "resume": None}

    def telemetry_payload(self) -> dict[str, object]:
        return {"summary": True}

    def render_html(self) -> str:
        return "<html></html>"


class StubSummaryBuilder:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def build(self, **_kwargs):
        return StubSummaryPayload()

    def capture_preview(self, controller, summary, *, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"preview")

        return types.SimpleNamespace(
            summary=summary.to_preview_payload(),
            screenshot={"path": str(output_path)},
            telemetry=summary.telemetry_payload(),
        )


class StubBrowserUseController:
    def __init__(self, config) -> None:
        self.config = config
        self.session_id = "stub-session"
        self._html_counter = 0

    def wait_for_idle(self, timeout: float = 5.0) -> BrowserActionResult:
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": {"timeout": timeout}},
            telemetry={"event": "stub.idle"},
        )

    def get_page_html(self) -> BrowserActionResult:
        self._html_counter += 1
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"html": f"<html data-counter=\"{self._html_counter}\"></html>"},
            telemetry={"event": "stub.html"},
        )

    def query_selector(self, selector: str) -> BrowserActionResult:
        exists = selector in {
            "div.resume-upload-success",
            "input#resume-upload-input.application-file-input[value]",
        }
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"exists": exists, "response": {"exists": exists, "count": 1 if exists else 0}},
            telemetry={"event": "stub.selector"},
        )


@pytest.fixture()
def stubbed_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    monkeypatch.setattr("apps.cli.main.BrowserUseController", StubBrowserUseController)
    monkeypatch.setattr("apps.cli.main.LeverNavigator", StubNavigator)
    monkeypatch.setattr("apps.cli.main.LeverFormPlanner.load", StubPlannerLoader())
    monkeypatch.setattr("apps.cli.main.AutofillPlannerOrchestrator", StubPlannerOrchestrator)
    monkeypatch.setattr("apps.cli.main.LeverFormExecutor", lambda: StubFormExecutor())
    monkeypatch.setattr("apps.cli.main.ResumeUploader", lambda *a, **k: StubResumeUploader())
    monkeypatch.setattr("apps.cli.main.LeverSummaryBuilder", lambda *a, **k: StubSummaryBuilder())
    from sites.lever.lever_google_discovery import LeverSerpResult

    monkeypatch.setattr(
        "apps.cli.main._plan_candidates",
        lambda payload, fetch_html=None: [
            LeverSerpResult(
                title="QA Engineer",
                href="https://jobs.lever.co/acme/qa/apply",
                mode="apply_direct",
            )
        ],
    )

    class _Binding:
        def __init__(self) -> None:
            self.user_data_dir = tmp_path / ".local/browser/profiles/qa-tester"
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            self.browser_overrides = {}
            self.model_overrides = {}
            self.plan_overrides = {}
            self.qa_overrides = {}
            self.resume_path = tmp_path / "data/resumes/qa-tester/resume.pdf"
            self.resume_path.parent.mkdir(parents=True, exist_ok=True)
            self.resume_path.write_bytes(b"%PDF-1.4\n")
            self.session_backups_enabled = None
            self.session_backups_retention = None
            self.profile_id = "qa-tester"
            self.display_name = "QA Tester"

        def cli_payload(self) -> dict[str, object]:
            return {"id": "qa-tester"}

        def telemetry_payload(self) -> dict[str, object]:
            return {"id": "qa-tester"}

    class _ProfileConfig:
        def __init__(self) -> None:
            self.search = types.SimpleNamespace(source="lever-google", terms=["qa"], location="remote", time_window="d")
            self.qa_overrides = {}
            self.links = {}
            self.identity = types.SimpleNamespace(full_name="Test User", email="user@example.com")

        def resolved_plan_overrides(self) -> dict[str, object]:
            return {}

    class StubProfileService:
        def __init__(self, base: Path | None = None) -> None:
            self.base = base or tmp_path

        def build_binding(self, profile_id: str):
            return _Binding()

        def bind_profile(self, profile_id: str, require_resume: bool = True):
            return _Binding()

        def load_profile(self, profile_id: str):
            return _ProfileConfig()

        def profile_path(self, profile_id: str) -> Path:
            return tmp_path / "data" / "profiles" / f"{profile_id}.yaml"

        def validate_profile(self, profile_id: str):
            class _Result:
                def __init__(self) -> None:
                    self.profile = _ProfileConfig()
                    self.errors: list[dict[str, object]] = []

            return _Result()

    monkeypatch.setattr("apps.cli.main.ProfileService", StubProfileService)
    monkeypatch.setattr("apps.cli.main.AutofillExecutor", StubAutofillExecutor)
    lever_site_dir = tmp_path / "sites" / "lever"
    selectors_dir = lever_site_dir / "selectors"
    selectors_dir.mkdir(parents=True, exist_ok=True)
    (selectors_dir / "form-fields.json").write_text(json.dumps({"fields": []}), encoding="utf-8")
    (lever_site_dir / "config.yaml").write_text(
        """
resume:
  success_selectors:
    - "div.resume-upload-success"
    - "input#resume-upload-input.application-file-input[value]"
  working_selectors:
    - "div.resume-upload-spinner"
  failure_selectors:
    - "div.resume-upload-error"
  max_wait_seconds: 2
  poll_interval_ms: 100
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_apply_run_ai_autofill_records_execution(stubbed_environment: Path, capsys):
    tmp_path = stubbed_environment

    result = apply_run(
        source="lever-google",
        plan=None,
        terms="qa",
        location="remote",
        time_window="d",
        pages=1,
        limit=1,
        profile="qa-tester",
        dry_run=False,
        mode="ai_autofill",
        model="gpt-stub",
        plan_model="gpt-plan",
        plan_llm=None,
    )

    assert result is not None
    captured = capsys.readouterr()
    assert "candidatesProcessed" in captured.out

    runs_dir = Path(os.environ["JAA_BASE_DIR"]) / "runs"
    run_dirs = list(runs_dir.iterdir())
    assert run_dirs, "Expected run directory to be created"
    run_json = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_json.get("browserSession", {}).get("sessionId") == "stub-session"
    candidates = run_json.get("lever", {}).get("candidates", {})
    assert candidates, "Expected candidate entry"
    candidate_payload = next(iter(candidates.values()))
    execution = candidate_payload.get("autofill", {}).get("execution", {})
    assert execution.get("filled") == 1
    assert Path(execution.get("path", "")).exists()
    assert StubAutofillExecutor.last_instance is not None
    assert StubAutofillExecutor.last_instance.last_plan is not None
    resume_analysis = candidate_payload.get("resumeAnalysis")
    assert resume_analysis is not None
    assert resume_analysis.get("status") in {"ok", "timeout", "failed"}
