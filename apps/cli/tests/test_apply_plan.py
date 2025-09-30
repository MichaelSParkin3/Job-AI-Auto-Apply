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
            command=_identity_decorator, callback=_identity_decorator
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
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    sys.modules["yaml"] = types.SimpleNamespace(
        safe_load=lambda *_args, **_kwargs: {},
        safe_dump=lambda *_args, **_kwargs: "{}\n",
    )

try:
    import dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: False)

try:
    import portalocker  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
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

try:  # pragma: no cover - optional dependency guard
    import bs4  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
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

try:  # pragma: no cover - optional dependency guard
    import fastapi  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
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

    class FileResponse:  # pragma: no cover - placeholder for FastAPI response
        def __init__(self, path: Path | str, *args, **kwargs) -> None:
            self.path = Path(path)

    class StaticFiles:  # pragma: no cover - placeholder for FastAPI static handler
        def __init__(self, *args, **kwargs) -> None:
            pass

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.FastAPI = FastAPI
    fastapi_module.HTTPException = HTTPException
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.FileResponse = FileResponse
    fastapi_staticfiles = types.ModuleType("fastapi.staticfiles")
    fastapi_staticfiles.StaticFiles = StaticFiles
    fastapi_module.responses = fastapi_responses
    fastapi_module.staticfiles = fastapi_staticfiles
    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.responses"] = fastapi_responses
    sys.modules["fastapi.staticfiles"] = fastapi_staticfiles

try:  # pragma: no cover - optional dependency guard
    import pydantic  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    class _BaseModel:
        def __init__(self, **data) -> None:
            for key, value in data.items():
                setattr(self, key, value)

        def model_dump(self) -> dict[str, object]:
            return self.__dict__.copy()

    def _field(default=None, **_kwargs):
        return default

    pydantic_module = types.ModuleType("pydantic")
    pydantic_module.BaseModel = _BaseModel
    pydantic_module.Field = _field
    sys.modules["pydantic"] = pydantic_module

sys.path.insert(0, os.getcwd())

from apps.browser import BrowserActionResult, BrowserActionStatus
from apps.cli.main import PLAN_GOOGLE_DOMAINS, apply_plan
from sites.lever.lever_google_discovery import LeverSerpResult


def _write_profile(tmp_path: Path, profile_id: str = "qa-tester") -> Path:
    profile_dir = tmp_path / "data" / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    resume_path = tmp_path / "data" / "resumes" / profile_id / "resume.pdf"
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_bytes(b"%PDF-1.4\n")
    profile_yaml = f"""
identity:
  full_name: "Test User"
  email: "user@example.com"
  phone: null
  location: "Remote"
  portfolio: []
documents:
  resume_path: {resume_path.relative_to(tmp_path)}
id: "{profile_id}"
display_name: "QA Tester"
model_overrides: {{}}
qa_overrides: {{}}
links: {{}}
user_data_dir: .local/browser/profiles/{profile_id}
search:
  source: lever-google
  terms: ['front end']
  location: 'remote us'
  time_window: d
plan:
  browser_discovery: false
  programmable_search: false
  google_cse_key: null
  google_cse_cx: null
"""
    profile_path = profile_dir / f"{profile_id}.yaml"
    profile_path.write_text(profile_yaml.strip() + "\n", encoding="utf-8")
    return profile_path


class _StubPlanController:
    last_config = None
    html_content = "<html><body><a href='https://jobs.lever.co/acme/role/apply'>Apply</a></body></html>"

    def __init__(self, config) -> None:
        _StubPlanController.last_config = config
        self._html = _StubPlanController.html_content

    def open_url(self, url: str) -> BrowserActionResult:
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": {"url": url}},
            telemetry={"event": "stub.open"},
        )

    def wait_for_idle(self, timeout: float = 5.0) -> BrowserActionResult:
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": {"timeout": timeout}},
            telemetry={"event": "stub.idle"},
        )

    def get_page_html(self) -> BrowserActionResult:
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"html": self._html},
            telemetry={"event": "stub.html"},
        )

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        return None


class _FailingController:
    def __init__(self, *_args, **_kwargs) -> None:  # pragma: no cover - guard for precedence
        raise AssertionError("Browser controller should not be constructed for CSE mode")


def _read_plan_payload(capsys) -> dict[str, object]:
    captured = capsys.readouterr().out
    trimmed = captured.strip()
    start = trimmed.rfind("\n{")
    if start == -1:
        start = 0
    payload_str = trimmed[start:].strip()
    return json.loads(payload_str)


def test_apply_plan_with_browser_discovery(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _write_profile(tmp_path)

    monkeypatch.setattr("apps.cli.main.BrowserUseController", _StubPlanController)
    monkeypatch.setattr(
        "apps.cli.main.LeverGoogleDiscovery.extract_results",
        lambda html: [
            LeverSerpResult(title="Role", href="https://jobs.lever.co/acme/role/apply", mode="apply_direct"),
            LeverSerpResult(title="Role Duplicate", href="https://jobs.lever.co/acme/role/apply", mode="apply_direct"),
            LeverSerpResult(title="Job Page", href="https://jobs.lever.co/acme/job", mode="job_page"),
        ],
    )

    apply_plan(
        source=None,
        terms=None,
        location=None,
        time_window=None,
        pages=1,
        profile="qa-tester",
        browser_discovery=True,
        programmable_search=None,
        google_cse_key=None,
        google_cse_cx=None,
    )

    payload = _read_plan_payload(capsys)
    assert payload["plan"].get("discoveryMode") == "browser"
    assert [result["href"] for result in payload["results"]] == [
        "https://jobs.lever.co/acme/role/apply",
        "https://jobs.lever.co/acme/job",
    ]
    guardrails = payload["guardrails"]["allowed_domains"]
    for domain in PLAN_GOOGLE_DOMAINS:
        assert domain in guardrails
    run_dir = Path(payload["plan"]["runDir"])
    artifact_path = run_dir / "plan" / "serp-page-01.html"
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == _StubPlanController.html_content


def test_apply_plan_uses_programmable_search_when_credentials_present(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))
    _write_profile(tmp_path)

    monkeypatch.setattr("apps.cli.main.BrowserUseController", _FailingController)

    call_counter = {"count": 0}

    def fake_fetch(url: str):
        call_counter["count"] += 1
        return {
            "items": [
                {
                    "link": "https://jobs.lever.co/acme/engineering/apply",
                    "title": "Engineer",
                },
                {
                    "link": "https://jobs.lever.co/acme/support",
                    "title": "Support",
                },
            ]
        }

    monkeypatch.setattr("apps.cli.main._fetch_cse_json", fake_fetch)

    apply_plan(
        source=None,
        terms=None,
        location=None,
        time_window=None,
        pages=1,
        profile="qa-tester",
        browser_discovery=True,
        programmable_search=True,
        google_cse_key="demo-key",
        google_cse_cx="demo-cx",
    )

    payload = _read_plan_payload(capsys)
    assert payload["plan"].get("discoveryMode") == "programmable_search"
    assert payload["plan"].get("runDir") is None or payload["plan"].get("runDir") == ""
    assert [result["href"] for result in payload["results"]] == [
        "https://jobs.lever.co/acme/engineering/apply",
        "https://jobs.lever.co/acme/support",
    ]
    assert payload["plan"].get("summary", {}).get("apiCalls") == call_counter["count"]
    assert "allowed_domains" not in payload.get("guardrails", {}) or all(
        domain not in PLAN_GOOGLE_DOMAINS for domain in payload.get("guardrails", {}).get("allowed_domains", [])
    )
