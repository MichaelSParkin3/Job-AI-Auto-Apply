"""Typer CLI entry points for Job AI Auto Apply operations."""

from __future__ import annotations

import os
import sys
import hashlib
import json
import time
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")

try:  # pragma: no cover - exercised in environments without typer installed
    import typer
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
            command=_identity_decorator,
            callback=_identity_decorator,
            add_typer=lambda sub_app, *a, **kw: sub_app,
        ),
        Option=_option_stub,
        Argument=_option_stub,
        Exit=_TyperExit,
        secho=_echo_stub,
        echo=_echo_stub,
        colors=types.SimpleNamespace(RED="red", GREEN="green", YELLOW="yellow"),
    )


from apps.browser import (
    BrowserActionStatus,
    BrowserLaunchConfig,
    BrowserLaunchError,
    BrowserUseController,
    BrowserUseError,
    SessionBackupManager,
)
from apps.preview.runner import run_preview_service
from sites.lever.form_executor import LeverFormExecutor, LeverFormPlanner
from sites.lever.lever_google_discovery import LeverGoogleDiscovery, LeverSerpResult
from sites.lever.navigation import LeverNavigator
from sites.lever.summary import LeverSummaryBuilder
from sites.simplyhired.form_mapper import FormFillPlan, FormSelectorLibrary, FormStructureMapper
from sites.simplyhired.form_filler import FormFillExecutor
from sites.simplyhired.quick_apply_discovery import QuickApplyDiscovery
from sites.simplyhired.resume_uploader import ResumeUploader
from sites.simplyhired.summary_builder import SummaryCompiler
from sites.simplyhired.search_readiness import SearchReadinessDetector
from .config_loader import (
    Settings,
    ensure_runtime_dirs,
    get_base_dir,
    write_default_config,
)
from .history_store import HistoryWriter
from .profiles import ProfileAnswerResolver, ProfileBinding, ProfileService
from .queue_manager import ApplicationCandidate, ReviewQueueManager
from .run_store import RunStore
from .runtime_state import RunContext, get_run_context, set_run_context
from .utils import ApiError, log_event


def _create_typer_app(*args: Any, **kwargs: Any):
    """Return a Typer application with compatibility helpers for stubbed environments."""

    typer_app = typer.Typer(*args, **kwargs)
    if not hasattr(typer_app, "add_typer"):

        def _add_typer(_sub_app, *_, **__):
            return _sub_app

        setattr(typer_app, "add_typer", _add_typer)
    return typer_app


app = _create_typer_app(help="Job AI Auto Apply CLI")


def _configure_console_utf8() -> None:
    """Best-effort: make Windows console UTF-8 safe for emoji logs from dependencies."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@app.callback()
def init(_: bool = typer.Option(False, "--version", help="Show version")):
    """Initialize the application state before running any command.

    Ensures that all required runtime directories exist.
    """
    _configure_console_utf8()
    # Create runtime dirs early (AC #4)
    ensure_runtime_dirs()


config_app = _create_typer_app(help="Configuration commands")
apply_app = _create_typer_app(help="Application/automation commands (skeleton)")
preview_app = _create_typer_app(help="Preview server commands")
profiles_app = _create_typer_app(help="Profile management commands")
history_app = _create_typer_app(help="Run history utilities (skeleton)")


@config_app.command("init")
def config_init():
    """Create config/config.yaml with documented defaults if missing (idempotent)."""
    path = write_default_config()
    typer.echo(f"Config initialized at {path}")


@config_app.command("show")
def config_show():
    """Show effective settings (precedence: CLI > profile > global)."""
    s = Settings.load()
    typer.echo(s.to_json())


@apply_app.command("demo")
def apply_demo(
    limit: int = typer.Option(1, help="Maximum number of demo items to stage."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Force dry-run guardrails."),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Skip launching Chrome app-mode; server still runs.",
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        min=1024,
        max=65535,
        help="Override preview server port (defaults to config value).",
    ),
):
    """Run a complete dry-run demo of the application preview flow."""

    overrides: dict[str, object] = {"dry_run": dry_run}
    if port is not None:
        overrides["preview_port"] = port
    settings = Settings.load(overrides=overrides)
    base = get_base_dir()
    service = ProfileService(base=base)
    binding_payload = None
    if settings.active_profile:
        binding = service.build_binding(settings.active_profile)
        if binding:
            binding_payload = binding.cli_payload()
    store = RunStore(base=base)
    record = store.start_demo_run(
        profile_id=settings.active_profile,
        profile_binding=binding_payload,
    )
    store.bootstrap_demo_preview(record, limit=limit, profile_id=settings.active_profile)
    log_event(
        {
            "event": "run.demo_initialized",
            "message": "Demo run directory prepared with redacted logging.",
            "limit": limit,
            "dryRun": True,
        }
    )
    log_event(
        {
            "event": "guardrail.demo.no_network",
            "message": "Demo mode disables Browser-Use navigation and SimplyHired traffic.",
            "domains": ["*.simplyhired.com"],
            "mode": "demo",
        }
    )
    context = get_run_context()
    writer = HistoryWriter()
    if context:
        writer.append_demo_entry(
            context,
            summary="Demo run initialized; preview interactions remain local-only.",
            decision="initialized",
        )
    typer.echo(
        json.dumps(
            {
                "run_id": record.id,
                "run_dir": str(record.run_dir),
                "actions_log": str(record.logs_path),
                "limit": limit,
                "dry_run": True,
                "preview_port": settings.preview_port,
            },
            ensure_ascii=False,
        )
    )
    run_preview_service(
        settings,
        demo=True,
        open_browser=not no_browser,
        run_record=record,
        run_store=store,
        history_writer=writer,
        run_context=context,
    )


def _lever_guardrail_domains() -> list[str]:
    return [
        "jobs.lever.co",
        "*.jobs.lever.co",
        "api.lever.co",
        "newassets.hcaptcha.com",
    ]


PLAN_GOOGLE_DOMAINS = ["www.google.com", "*.google.com", "consent.google.com"]


def _iso_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_serp_html(url: str) -> str | None:
    """Fetch Google SERP HTML using a basic HTTP client."""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        )
    }
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except URLError as error:
        log_event(
            {
                "level": "warning",
                "event": "lever.plan.fetch_failed",
                "message": "Failed to fetch Lever SERP HTML.",
                "url": url,
                "error": getattr(error, "reason", str(error)),
            }
        )
        return None


def _lever_candidate_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return digest[:12]


def _plan_candidates(
    payload: Mapping[str, Any],
    *,
    fetch_html: Callable[[str], str | None] = _fetch_serp_html,
) -> list[LeverSerpResult]:
    """Return Lever SERP results from cached plan data or live fetches."""

    results: list[LeverSerpResult] = []
    seen: set[str] = set()
    explicit_results: Iterable[Mapping[str, Any]] | None = None
    if isinstance(payload.get("results"), list):
        explicit_results = payload.get("results")  # type: ignore[assignment]
    elif isinstance(payload.get("plan"), Mapping):
        plan_map = payload.get("plan")  # type: ignore[assignment]
        if isinstance(plan_map, Mapping) and isinstance(plan_map.get("results"), list):
            explicit_results = plan_map.get("results")  # type: ignore[assignment]
    if explicit_results:
        for item in explicit_results:
            href = str(item.get("href") or "").strip()
            if not href or href in seen:
                continue
            title = str(item.get("title") or href)
            mode = str(item.get("mode") or ("apply_direct" if item.get("isApply") else "job_page"))
            seen.add(href)
            results.append(LeverSerpResult(title=title, href=href, mode=mode))
        if results:
            return results

    plan_map = payload.get("plan") if isinstance(payload.get("plan"), Mapping) else {}
    urls: Iterable[str] = plan_map.get("urls") if isinstance(plan_map, Mapping) else []
    for url in urls or []:
        html = fetch_html(str(url))
        if not html:
            continue
        for result in LeverGoogleDiscovery.extract_results(html):
            if result.href in seen:
                continue
            seen.add(result.href)
            results.append(result)
    return results


def _normalize_lever_href(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if not parsed.scheme:
        parsed = parsed._replace(scheme="https")
    host = parsed.netloc.lower()
    if not host:
        return None
    if not host.endswith("jobs.lever.co"):
        return None
    cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    normalized_path = parsed.path.rstrip("/")
    is_apply = normalized_path.endswith("/apply") or "/apply/" in normalized_path
    mode = "apply_direct" if is_apply else "job_page"
    return cleaned, mode


def _fetch_cse_json(url: str) -> Mapping[str, Any] | None:
    try:
        request = Request(url)
        with urlopen(request, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset, errors="replace")
            return json.loads(payload)
    except URLError as error:
        log_event(
            {
                "level": "warning",
                "event": "lever.plan.cse_failed",
                "message": "Programmable Search request failed.",
                "url": url,
                "error": getattr(error, "reason", str(error)),
            }
        )
        return None


def _discover_candidates_with_cse(
    *,
    plan_payload: Mapping[str, Any],
    api_key: str,
    cx: str,
    time_window: str,
    pages: int,
    fetch_json: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> tuple[list[LeverSerpResult], dict[str, Any]]:
    fetcher = fetch_json or _fetch_cse_json
    plan_map = plan_payload.get("plan") if isinstance(plan_payload.get("plan"), Mapping) else {}
    base_url = ""
    if isinstance(plan_map, Mapping):
        base_value = plan_map.get("baseUrl")
        if isinstance(base_value, str):
            base_url = base_value
    if not base_url:
        search_map = plan_payload.get("search") if isinstance(plan_payload.get("search"), Mapping) else {}
        terms = search_map.get("terms") if isinstance(search_map, Mapping) else []
        location = search_map.get("location") if isinstance(search_map, Mapping) else None
        terms_list = [str(term) for term in terms] if isinstance(terms, (list, tuple)) else []
        discovery_plan = LeverGoogleDiscovery.plan(terms_list, location, time_window=time_window, pages=1)
        base_url = discovery_plan.base_url
    parsed = urlparse(base_url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    q_param = query_params.get("q", "")
    tbs = query_params.get("tbs", "")
    time_map = {
        "qdr:h": "d1",
        "qdr:d": "d1",
        "qdr:w": "w1",
        "qdr:m": "m1",
        "qdr:y": "y1",
    }
    window_map = {"h": "d1", "d": "d1", "w": "w1", "m": "m1", "y": "y1"}
    date_restrict = time_map.get(tbs) or window_map.get(time_window)
    results: list[LeverSerpResult] = []
    seen: set[str] = set()
    api_calls = 0
    max_pages = max(1, pages)
    for index in range(max_pages):
        params = {
            "key": api_key,
            "cx": cx,
            "q": q_param,
            "num": 10,
            "start": index * 10 + 1,
        }
        if date_restrict:
            params["dateRestrict"] = date_restrict
        request_url = f"https://www.googleapis.com/customsearch/v1?{urlencode(params)}"
        log_event(
            {
                "event": "lever.plan.cse_request",
                "page": index + 1,
                "url": request_url,
            }
        )
        payload = fetcher(request_url)
        if not payload:
            continue
        api_calls += 1
        items = payload.get("items") if isinstance(payload, Mapping) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            link = str(item.get("link") or "").strip()
            if not link:
                continue
            normalized = _normalize_lever_href(link)
            if not normalized:
                continue
            href, mode = normalized
            if href in seen:
                continue
            seen.add(href)
            title = str(item.get("title") or href)
            results.append(LeverSerpResult(title=title, href=href, mode=mode))
        if len(items) < 10:
            break
    log_event(
        {
            "event": "lever.plan.cse_completed",
            "results": len(results),
            "apiCalls": api_calls,
        }
    )
    return results, {"mode": "programmable_search", "apiCalls": api_calls}


def _discover_candidates_with_browser(
    *,
    plan_payload: Mapping[str, Any],
    settings: Settings,
    profile_id: str,
    binding: ProfileBinding | None,
    base: Path,
) -> tuple[list[LeverSerpResult], dict[str, Any]]:
    binding = binding or ProfileBinding.demo(base, profile_id=profile_id)
    binding.user_data_dir.mkdir(parents=True, exist_ok=True)
    guardrail_domains: list[str]
    overrides_domains = binding.browser_overrides.get("allowed_domains") if binding.browser_overrides else None
    if isinstance(overrides_domains, (list, tuple)) and overrides_domains:
        guardrail_domains = [str(domain).strip() for domain in overrides_domains if str(domain).strip()]
    else:
        guardrail_domains = [str(domain).strip() for domain in settings.browser_allowed_domains]
    for domain in _lever_guardrail_domains():
        if domain not in guardrail_domains:
            guardrail_domains.append(domain)
    for domain in PLAN_GOOGLE_DOMAINS:
        if domain not in guardrail_domains:
            guardrail_domains.append(domain)
    wait_range = tuple(int(value) for value in settings.browser_pacing_wait_jitter_ms)
    think_range = tuple(float(value) for value in settings.browser_pacing_think_time_range_s)
    browser_model_override = (
        binding.browser_overrides.get("model") if binding.browser_overrides else None
    )
    profile_model = binding.model_overrides.get("llm") if binding.model_overrides else None
    effective_model = (
        browser_model_override
        or profile_model
        or settings.OPENROUTER_MODEL
        or settings.browser_model
    )
    if not effective_model:
        raise ApiError(
            code="plan.browser.model_missing",
            message="No Browser-Use model configured for plan discovery.",
            details={"profileId": profile_id},
        )
    search_map = plan_payload.get("search") if isinstance(plan_payload.get("search"), Mapping) else {}
    source = "lever-google"
    if isinstance(search_map, Mapping) and isinstance(search_map.get("source"), str):
        source = str(search_map.get("source"))
    launch_config = BrowserLaunchConfig(
        profile_id=profile_id,
        user_data_dir=binding.user_data_dir,
        model=effective_model,
        viewport_width=settings.browser_viewport_width,
        viewport_height=settings.browser_viewport_height,
        locale=settings.browser_locale,
        timezone=settings.browser_timezone,
        chrome_path=settings.chrome_path,
        guardrail_domains=tuple(guardrail_domains),
        wait_jitter_ms=wait_range,
        think_time_range_s=think_range,
        profile_metadata={"mode": "plan", "source": source},
        profile_binding=binding.telemetry_payload(),
    )
    run_store = RunStore(base=base)
    run_record = run_store.start_lever_plan_discovery(
        profile_id=profile_id,
        source=source,
        plan_payload=plan_payload,
        guardrails=guardrail_domains,
        discovery_mode="browser",
        profile_binding=binding.cli_payload(),
    )
    plan_dir = run_record.run_dir / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_map = plan_payload.get("plan") if isinstance(plan_payload.get("plan"), Mapping) else {}
    urls: list[str] = []
    if isinstance(plan_map, Mapping):
        raw_urls = plan_map.get("urls")
        if isinstance(raw_urls, (list, tuple)):
            urls = [str(item) for item in raw_urls if str(item).strip()]
    log_event(
        {
            "event": "lever.plan.browser.start",
            "runId": run_record.id,
            "urls": len(urls),
            "guardrails": guardrail_domains,
        }
    )
    controller = BrowserUseController(launch_config)
    artifacts: list[dict[str, Any]] = []
    results: list[LeverSerpResult] = []
    seen: set[str] = set()
    try:
        for index, url in enumerate(urls, start=1):
            artifact_path = plan_dir / f"serp-page-{index:02}.html"
            log_event(
                {
                    "event": "lever.plan.browser.navigate",
                    "page": index,
                    "url": url,
                    "runId": run_record.id,
                }
            )
            navigation = controller.open_url(url)
            if navigation.status != BrowserActionStatus.OK:
                log_event(
                    {
                        "level": "warning",
                        "event": "lever.plan.browser.navigation_failed",
                        "page": index,
                        "url": url,
                        "details": navigation.details,
                        "runId": run_record.id,
                    }
                )
                continue
            controller.wait_for_idle(timeout=12.0)
            page_html = controller.get_page_html()
            html = ""
            if isinstance(page_html.details, Mapping):
                html = str(page_html.details.get("html") or "")
            if not html.strip():
                log_event(
                    {
                        "level": "warning",
                        "event": "lever.plan.browser.empty_html",
                        "page": index,
                        "url": url,
                        "runId": run_record.id,
                    }
                )
                continue
            artifact_path.write_text(html, encoding="utf-8")
            artifacts.append({"path": str(artifact_path), "url": url})
            for result in LeverGoogleDiscovery.extract_results(html):
                if result.href in seen:
                    continue
                seen.add(result.href)
                results.append(result)
    finally:
        try:
            controller.close()
        except Exception:
            pass
        run_store.record_plan_discovery(
            run_record,
            {
                "guardrails": guardrail_domains,
                "artifacts": artifacts,
                "results": [
                    {"title": r.title, "href": r.href, "mode": r.mode} for r in results
                ],
                "mode": "browser",
                "summary": {"pages": len(artifacts), "results": len(results)},
            },
        )
        log_event(
            {
                "event": "lever.plan.browser.completed",
                "runId": run_record.id,
                "pages": len(artifacts),
                "results": len(results),
            }
        )
        set_run_context(None)
    return results, {
        "guardrails": guardrail_domains,
        "artifacts": artifacts,
        "run_id": run_record.id,
        "run_dir": str(run_record.run_dir),
        "mode": "browser",
        "summary": {"pages": len(artifacts), "results": len(results)},
    }
def _load_profile_search_defaults(
    service: ProfileService, profile_id: str
) -> tuple[Any, Any, list[str], str | None, str]:
    binding = service.build_binding(profile_id)
    result = service.validate_profile(profile_id)
    prof = result.profile
    terms_list: list[str] = []
    loc: str | None = None
    qdr = "d"
    if prof and prof.search:
        terms_list = list(prof.search.terms or [])
        loc = prof.search.location
        qdr = prof.search.time_window or "d"
    return binding, prof, terms_list, loc, qdr


def _build_lever_plan_payload(
    *,
    profile_id: str,
    binding: Any,
    terms: list[str],
    location: str,
    time_window: str,
    pages: int,
) -> dict[str, Any]:
    plan = LeverGoogleDiscovery.plan(terms, location, time_window=time_window, pages=pages)
    if binding:
        profile_payload = binding.cli_payload()
    else:
        profile_payload = {"id": profile_id, "valid": False}
    return {
        "profile": profile_payload,
        "search": {
            "source": "lever-google",
            "terms": terms,
            "location": location,
            "time_window": time_window,
            "pages": pages,
        },
        "guardrails": {"allowed_domains": _lever_guardrail_domains()},
        "plan": plan.to_payload(),
        "notes": [
            "Review-only: do not submit during Epic 4.",
            "Use Browser-Use pacing and single-tab policy.",
            "Prefer /apply URLs; otherwise click in-page Apply to reach the form.",
        ],
    }


@apply_app.command("plan")
def apply_plan(
    source: Optional[str] = typer.Option(
        None,
        "--source",
        "-s",
        help="Discovery provider id (lever-google). Defaults to profile.search.source or lever-google.",
    ),
    terms: Optional[str] = typer.Option(
        None, "--terms", help="Quoted terms (space-separated). Defaults to profile.search.terms."
    ),
    location: Optional[str] = typer.Option(
        None, "--location", help="Location string (e.g., 'remote us'). Defaults to profile.search.location."
    ),
    time_window: Optional[str] = typer.Option(
        None, "--time-window", help="Google qdr window: h|d|w|m|y. Defaults to profile.search.time_window (d)."
    ),
    pages: int = typer.Option(1, "--pages", min=1, help="Number of SERP pages (10 results each)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Profile identifier to bind."),
    browser_discovery: Optional[bool] = typer.Option(
        None,
        "--browser-discovery/--no-browser-discovery",
        help="Use Browser-Use to capture SERP HTML and dedupe Lever results.",
    ),
    programmable_search: Optional[bool] = typer.Option(
        None,
        "--programmable-search/--no-programmable-search",
        help="Use Google Programmable Search when credentials are configured.",
    ),
    google_cse_key: Optional[str] = typer.Option(
        None,
        "--google-cse-key",
        help="Override Google Custom Search API key for this invocation.",
    ),
    google_cse_cx: Optional[str] = typer.Option(
        None,
        "--google-cse-cx",
        help="Override Google Programmable Search engine identifier.",
    ),
):
    """Plan discovery URLs for supported sources (lever-google review flow)."""

    overrides: dict[str, Any] = {}
    if profile:
        overrides["active_profile"] = profile
    if browser_discovery is not None:
        overrides["plan.browser_discovery"] = browser_discovery
    if programmable_search is not None:
        overrides["plan.programmable_search"] = programmable_search
    if google_cse_key:
        overrides["plan.google_cse_key"] = google_cse_key
    if google_cse_cx:
        overrides["plan.google_cse_cx"] = google_cse_cx
    settings = Settings.load(overrides=overrides or None)
    base = get_base_dir()
    service = ProfileService(base=base)

    profile_id = profile or settings.active_profile
    if not profile_id:
        typer.secho("No active profile. Pass --profile or run `profiles use <id>`.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    binding, profile_config, terms_list, loc, qdr = _load_profile_search_defaults(
        service, profile_id
    )

    profile_source = profile_config.search.source if profile_config and profile_config.search else None
    effective_source = (source or profile_source or "lever-google").strip()
    if effective_source != "lever-google":
        typer.secho(
            f"Unsupported source '{effective_source}'. Supported sources: lever-google.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    if terms:
        terms_list = [t for t in terms.split(" ") if t.strip()]
    if not terms_list:
        terms_list = ["front end"]
    if location is not None:
        loc = location
    if not loc:
        loc = "remote us"
    if time_window is not None:
        qdr = time_window
    if not qdr:
        qdr = "d"

    payload = _build_lever_plan_payload(
        profile_id=profile_id,
        binding=binding,
        terms=terms_list,
        location=loc,
        time_window=qdr,
        pages=pages,
    )

    plan_preferences = {
        "browser_discovery": bool(settings.plan_browser_discovery),
        "programmable_search": bool(settings.plan_programmable_search),
        "google_cse_key": settings.plan_google_cse_key,
        "google_cse_cx": settings.plan_google_cse_cx,
    }
    profile_plan_overrides: Mapping[str, Any] = {}
    if profile_config is not None:
        profile_plan_overrides = profile_config.resolved_plan_overrides()
    elif binding is not None and binding.plan_overrides:
        profile_plan_overrides = binding.plan_overrides
    if browser_discovery is None and profile_plan_overrides.get("browser_discovery") is not None:
        plan_preferences["browser_discovery"] = bool(
            profile_plan_overrides["browser_discovery"]
        )
    if programmable_search is None and profile_plan_overrides.get("programmable_search") is not None:
        plan_preferences["programmable_search"] = bool(
            profile_plan_overrides["programmable_search"]
        )
    if google_cse_key is None and not plan_preferences["google_cse_key"]:
        if profile_plan_overrides.get("google_cse_key"):
            plan_preferences["google_cse_key"] = profile_plan_overrides["google_cse_key"]
    if google_cse_cx is None and not plan_preferences["google_cse_cx"]:
        if profile_plan_overrides.get("google_cse_cx"):
            plan_preferences["google_cse_cx"] = profile_plan_overrides["google_cse_cx"]

    use_cse = (
        plan_preferences["programmable_search"]
        and bool(plan_preferences["google_cse_key"])
        and bool(plan_preferences["google_cse_cx"])
    )
    if plan_preferences["programmable_search"] and not use_cse:
        log_event(
            {
                "level": "warning",
                "event": "lever.plan.cse_credentials_missing",
                "message": "Programmable Search requested but GOOGLE_CSE_KEY/CX are missing; falling back to other discovery mode.",
            }
        )
    use_browser = bool(plan_preferences["browser_discovery"])
    results: list[LeverSerpResult] = []
    discovery_metadata: dict[str, Any] = {}
    discovery_mode = "http"
    if use_cse:
        results, discovery_metadata = _discover_candidates_with_cse(
            plan_payload=payload,
            api_key=str(plan_preferences["google_cse_key"]),
            cx=str(plan_preferences["google_cse_cx"]),
            time_window=qdr,
            pages=pages,
        )
        discovery_mode = "programmable_search"
    elif use_browser:
        try:
            results, discovery_metadata = _discover_candidates_with_browser(
                plan_payload=payload,
                settings=settings,
                profile_id=profile_id,
                binding=binding,
                base=base,
            )
        except ApiError as error:
            typer.secho(error.to_json(), fg=typer.colors.RED)
            raise typer.Exit(code=1)
        except (BrowserUseError, BrowserLaunchError) as error:
            typer.secho(str(error), fg=typer.colors.RED)
            raise typer.Exit(code=1)
        discovery_mode = "browser"

    if discovery_metadata.get("guardrails"):
        payload.setdefault("guardrails", {})["allowed_domains"] = list(
            discovery_metadata["guardrails"]
        )
    plan_section = payload.setdefault("plan", {})
    if discovery_metadata.get("artifacts"):
        plan_section["artifacts"] = list(discovery_metadata["artifacts"])
    if discovery_metadata.get("summary"):
        summary = plan_section.get("summary", {}) if isinstance(plan_section.get("summary"), Mapping) else {}
        summary.update(discovery_metadata["summary"])
        plan_section["summary"] = summary
    if discovery_metadata.get("mode"):
        plan_section["discoveryMode"] = discovery_metadata["mode"]
    if discovery_metadata.get("run_id"):
        plan_section["runId"] = discovery_metadata["run_id"]
    if discovery_metadata.get("run_dir"):
        plan_section["runDir"] = discovery_metadata["run_dir"]
    if discovery_metadata.get("apiCalls"):
        summary = plan_section.get("summary", {}) if isinstance(plan_section.get("summary"), Mapping) else {}
        summary.setdefault("apiCalls", discovery_metadata["apiCalls"])
        plan_section["summary"] = summary
    if results:
        payload["results"] = [
            {"title": item.title, "href": item.href, "mode": item.mode}
            for item in results
        ]

    if discovery_mode == "browser" and discovery_metadata.get("run_dir"):
        run_dir_path = Path(discovery_metadata["run_dir"])
        plan_output_path = run_dir_path / "plan" / "plan.json"
        plan_output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if discovery_mode != "http":
        log_event(
            {
                "event": "lever.plan.discovery_completed",
                "mode": discovery_mode,
                "results": len(results),
            }
        )

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@apply_app.command("lever-plan")
def apply_lever_plan(
    terms: Optional[str] = typer.Option(
        None, "--terms", help="Quoted terms (space-separated). Defaults to profile.search.terms."
    ),
    location: Optional[str] = typer.Option(
        None, "--location", help="Location string (e.g., 'remote us'). Defaults to profile.search.location."
    ),
    time_window: Optional[str] = typer.Option(
        None, "--time-window", help="Google qdr window: h|d|w|m|y. Defaults to profile.search.time_window (d)."
    ),
    pages: int = typer.Option(1, "--pages", min=1, help="Number of SERP pages (10 results each)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Profile identifier to bind."),
):
    """Backward-compatible wrapper for `apply plan --source lever-google`."""

    apply_plan(
        source="lever-google",
        terms=terms,
        location=location,
        time_window=time_window,
        pages=pages,
        profile=profile,
    )


@apply_app.command("run")
def apply_run(
    source: str = typer.Option(
        "lever-google",
        "--source",
        "-s",
        help="Automation source identifier (lever-google).",
    ),
    plan: Optional[Path] = typer.Option(
        None,
        "--plan",
        help="Path to plan JSON produced by `apply plan --source lever-google`.",
    ),
    terms: Optional[str] = typer.Option(
        None,
        "--terms",
        help="Terms used when generating a Lever plan on the fly.",
    ),
    location: Optional[str] = typer.Option(
        None,
        "--location",
        help="Location hint when generating a Lever plan on the fly.",
    ),
    time_window: Optional[str] = typer.Option(
        None,
        "--time-window",
        help="Google qdr window (h|d|w|m|y) when generating a plan on the fly.",
    ),
    pages: int = typer.Option(1, "--pages", min=1, help="SERP pages to include when generating a plan."),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-n", help="Maximum number of candidates to process from the plan."
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="Profile identifier to bind."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Force dry-run review mode."),
    mode: str = typer.Option("review", "--mode", help="Run mode (review only)."),
    model: Optional[str] = typer.Option(None, "--model", help="Override Browser-Use model for this run."),
) -> str | None:
    """Execute Lever apply automation end-to-end and populate the review queue."""

    effective_source = source.strip().lower()
    if effective_source != "lever-google":
        typer.secho(
            f"Unsupported source '{source}'. Only lever-google is available.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    if mode != "review":
        typer.secho(
            "Only review mode is supported for Lever automation runs in Epic 4.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    overrides: dict[str, Any] = {"dry_run": dry_run}
    if profile:
        overrides["active_profile"] = profile
    if model:
        overrides["browser.model"] = model

    settings = Settings.load(overrides=overrides)
    base = get_base_dir()
    ensure_runtime_dirs(base)

    service = ProfileService(base=base)
    profile_id = profile or settings.active_profile
    if not profile_id:
        typer.secho(
            "No active profile set. Pass --profile or run `profiles use <id>` first.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        binding = service.bind_profile(profile_id, require_resume=False)
    except ApiError as error:
        typer.secho(error.to_json(), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        profile_config = service.load_profile(profile_id)
    except (FileNotFoundError, ValueError):
        profile_config = None

    plan_payload: dict[str, Any]
    if plan is not None:
        plan_path = plan if plan.is_absolute() else plan.resolve()
        if not plan_path.exists():
            typer.secho(f"Plan file not found at {plan_path}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            typer.secho(f"Plan file is not valid JSON: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    else:
        _, _, default_terms, default_location, default_window = _load_profile_search_defaults(
            service, profile_id
        )
        terms_list = list(default_terms or [])
        if terms:
            terms_list = [token for token in terms.split(" ") if token.strip()]
        if not terms_list:
            terms_list = ["front end"]
        location_value = default_location or "remote us"
        if location is not None:
            location_value = location or ""
        if not location_value:
            location_value = "remote us"
        window_value = default_window or "d"
        if time_window:
            window_value = time_window.strip() or window_value
        plan_payload = _build_lever_plan_payload(
            profile_id=profile_id,
            binding=binding,
            terms=terms_list,
            location=location_value,
            time_window=window_value,
            pages=pages,
        )

    plan_payload.setdefault("source", effective_source)
    candidates = _plan_candidates(plan_payload)
    if limit is not None and limit >= 0:
        candidates = candidates[: limit]
    if not candidates:
        typer.secho(
            "No Lever apply candidates discovered from the provided plan.",
            fg=typer.colors.YELLOW,
        )
        return None

    binding.user_data_dir.mkdir(parents=True, exist_ok=True)

    profile_model = binding.model_overrides.get("llm") if binding.model_overrides else None
    effective_model = model or profile_model or settings.OPENROUTER_MODEL or settings.browser_model
    if not effective_model:
        typer.secho(
            "No Browser-Use model configured. Set --model, profile browser.model, or OPENROUTER_MODEL.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    wait_range = tuple(int(value) for value in settings.browser_pacing_wait_jitter_ms)
    think_range = tuple(float(value) for value in settings.browser_pacing_think_time_range_s)
    launch_config = BrowserLaunchConfig(
        profile_id=profile_id,
        user_data_dir=binding.user_data_dir,
        model=effective_model,
        viewport_width=settings.browser_viewport_width,
        viewport_height=settings.browser_viewport_height,
        locale=settings.browser_locale,
        timezone=settings.browser_timezone,
        chrome_path=settings.chrome_path,
        guardrail_domains=tuple(_lever_guardrail_domains()),
        wait_jitter_ms=wait_range,
        think_time_range_s=think_range,
        profile_metadata={"mode": mode, "source": effective_source},
        profile_binding=binding.telemetry_payload(),
    )

    try:
        controller = BrowserUseController(launch_config)
    except (BrowserUseError, BrowserLaunchError) as error:
        typer.secho(str(error), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    selectors_path = base / "sites" / "lever" / "selectors" / "form-fields.json"
    if not selectors_path.exists():
        typer.secho(
            f"Lever selector configuration not found at {selectors_path}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    try:
        planner = LeverFormPlanner.load(selectors_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(f"Failed to load Lever form selectors: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    run_store = RunStore(base=base)
    run_record = run_store.start_lever_run(
        profile_id=profile_id,
        mode=mode,
        dry_run=dry_run,
        source=effective_source,
        plan_payload=plan_payload,
        profile_binding=binding.cli_payload(),
    )

    lever_dir = run_record.run_dir / "lever"
    lever_dir.mkdir(parents=True, exist_ok=True)
    plan_output_path = lever_dir / "plan.json"
    plan_output_path.write_text(
        json.dumps(plan_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    resolver = ProfileAnswerResolver(profile=profile_config, binding=binding)
    executor = LeverFormExecutor()
    summary_builder = LeverSummaryBuilder(source=effective_source)
    navigator = LeverNavigator(controller)
    resume_step_lookup = {"lever-form": "Lever apply form"}
    resume_uploader = ResumeUploader(
        controller,
        resume_path=binding.resume_path,
        dry_run=dry_run,
        run_dir=run_record.run_dir,
        step_lookup=resume_step_lookup,
    )

    queue_manager = ReviewQueueManager(
        run_store=run_store,
        run_record=run_record,
        mode=mode,
    )
    processed = 0

    for candidate in candidates:
        candidate_dir = lever_dir / _lever_candidate_id(candidate.href)
        candidate_dir.mkdir(parents=True, exist_ok=True)
        apply_html_path = candidate_dir / "apply.html"
        form_plan_path = candidate_dir / "form-plan.json"
        form_summary_path = candidate_dir / "form-summary.json"
        resume_payload_path = candidate_dir / "resume-upload.json"
        preview_dir = candidate_dir / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = preview_dir / "pre-submit.png"

        candidate_id = candidate_dir.name
        discovered_at = _iso_now()
        posting_payload = {
            "postingUrl": candidate.href,
            "title": candidate.title,
            "company": None,
            "location": None,
        }

        queue_candidate = ApplicationCandidate(
            id=candidate_id,
            posting=posting_payload,
            form_plan_path=str(form_plan_path),
            discovered_at=discovered_at,
            state="discovered",
        )
        queue_manager.enqueue(queue_candidate)

        candidate_payload: dict[str, Any] = {
            "id": candidate_id,
            "result": {
                "title": candidate.title,
                "href": candidate.href,
                "mode": candidate.mode,
            },
            "discoveredAt": discovered_at,
            "state": "discovered",
            "artifacts": {
                "applyHtml": str(apply_html_path),
                "plan": str(form_plan_path),
                "summary": str(form_summary_path),
                "resume": str(resume_payload_path),
                "previewScreenshot": str(screenshot_path),
            },
        }

        navigation = navigator.open_result(candidate)
        navigation_payload = navigation.to_payload()
        if navigation.html:
            apply_html_path.write_text(navigation.html, encoding="utf-8")
        candidate_payload["navigation"] = navigation_payload
        run_store.upsert_lever_candidate(run_record, candidate_id, candidate_payload)

        if navigation.status != "ok" or not navigation.html:
            queue_manager.update_state(candidate_id, "shelved")
            candidate_payload["state"] = "shelved"
            run_store.upsert_lever_candidate(run_record, candidate_id, candidate_payload)
            continue

        plan_result = planner.plan_from_html(navigation.html)
        plan_json = plan_result.to_payload()
        form_plan_path.write_text(
            json.dumps(plan_json, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        queue_manager.update_state(
            candidate_id,
            "planned",
            form_plan_path=str(form_plan_path),
        )
        candidate_payload["formPlan"] = {"path": str(form_plan_path), "fields": len(plan_result.fields)}
        run_store.upsert_lever_candidate(run_record, candidate_id, candidate_payload)

        answers: dict[str, Any] = {}
        for field in plan_result.fields:
            resolved = resolver.resolve(profile_field=field.value_key, label=field.label)
            if resolved.value not in (None, ""):
                answers[field.value_key] = resolved.value
        form_summary = executor.execute(plan_result, profile_answers=answers)
        form_summary_path.write_text(
            json.dumps(form_summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        candidate_payload["formSummary"] = form_summary
        run_store.upsert_lever_candidate(run_record, candidate_id, candidate_payload)

        resume_success: bool | None = None
        if binding.resume_path.exists():
            resume_result = resume_uploader.upload(
                selector=plan_result.resume_selector, step_id="lever-form"
            )
            resume_payload = resume_result.to_payload()
            resume_payload_path.write_text(
                json.dumps(resume_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            candidate_payload["resumeUpload"] = resume_payload
            candidate_payload.setdefault("telemetry", {})[
                "resumeUpload"
            ] = resume_result.telemetry_payload()
            resume_success = resume_result.status in {"uploaded", "simulated"}
            run_store.upsert_lever_candidate(run_record, candidate_id, candidate_payload)

        summary_payload = summary_builder.build(
            run_id=run_record.id,
            dry_run=dry_run,
            posting=posting_payload,
            form_summary=form_summary,
            resume_success=resume_success,
        )
        preview_result = summary_builder.capture_preview(
            controller,
            summary_payload,
            output_path=screenshot_path,
        )
        preview_summary_path = candidate_dir / "preview-summary.json"
        preview_summary_path.write_text(
            json.dumps(summary_payload.to_preview_payload(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        preview_telemetry_path = candidate_dir / "preview-telemetry.json"
        preview_telemetry_path.write_text(
            json.dumps(preview_result.telemetry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        candidate_payload["preview"] = preview_result.summary
        candidate_payload.setdefault("telemetry", {})["preview"] = preview_result.telemetry
        candidate_payload["artifacts"]["previewScreenshot"] = preview_result.screenshot.get("path")
        candidate_payload["state"] = "awaiting_decision"
        run_store.upsert_lever_candidate(run_record, candidate_id, candidate_payload)

        run_store.record_preview_summary(
            run_record,
            summary=summary_payload.to_preview_payload(),
            screenshot=preview_result.screenshot,
        )

        queue_manager.update_state(candidate_id, "awaiting_decision")

        processed += 1

    summary_output = {
        "runId": run_record.id,
        "candidatesProcessed": processed,
        "queuePending": len(queue_manager.snapshot.pending),
    }
    typer.echo(json.dumps(summary_output, ensure_ascii=False))
    set_run_context(None)
    return run_record.id


@apply_app.command("open")
def apply_open(
    search_url: str = typer.Argument(..., help="SimplyHired search URL to open."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Enforce dry-run guardrails."),
    limit: int = typer.Option(
        2,
        "--limit",
        "-n",
        min=1,
        help="Maximum number of Quick Apply openings to stage.",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="Profile identifier to bind."),
    model: Optional[str] = typer.Option(None, "--model", help="Override Browser-Use model."),
    chrome_path: Optional[str] = typer.Option(
        None,
        "--chrome-path",
        help="Override Chrome executable path for this session.",
    ),
    session_backups: Optional[bool] = typer.Option(
        None,
        "--session-backups/--no-session-backups",
        help="Enable or disable Browser-Use session backups for this run.",
    ),
    simple_click: bool = typer.Option(
        False,
        "--simple-click",
        help="Click the Quick Apply anchor directly (no preflight/filters).",
    ),
):
    """Launch Browser-Use with stealth defaults and open the provided URL."""

    overrides: dict[str, object] = {"dry_run": dry_run}
    if profile:
        overrides["active_profile"] = profile
    if model:
        overrides["browser.model"] = model
    if chrome_path:
        overrides["chrome_path"] = chrome_path
    if session_backups is not None:
        overrides["browser_session_backups.enabled"] = session_backups
    settings = Settings.load(overrides=overrides)
    base = get_base_dir()
    ensure_runtime_dirs(base)

    profile_id = profile or settings.active_profile
    if not profile_id:
        if dry_run:
            profile_id = "demo"
            log_event(
                {
                    "level": "warning",
                    "event": "profiles.missing_fallback",
                    "message": "No active profile set; using demo profile for dry-run.",
                }
            )
        else:
            typer.secho(
                "No active profile set. Run `python app.py profiles use <id>` first.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    service = ProfileService(base=base)
    if (
        profile_id == "demo"
        and dry_run
        and not service.profile_path(profile_id).exists()
    ):
        binding = ProfileBinding.demo(base, profile_id=profile_id)
        log_event(
            {
                "level": "warning",
                "event": "profiles.demo_fallback",
                "message": "Using demo profile binding because no active profile is configured.",
                "profile": binding.telemetry_payload(),
            }
        )
    else:
        try:
            binding = service.bind_profile(profile_id)
        except ApiError as error:
            typer.secho(error.to_json(), fg=typer.colors.RED)
            raise typer.Exit(code=1)

    profile_config = None
    try:
        profile_config = service.load_profile(profile_id)
    except (FileNotFoundError, ValueError):
        profile_config = None

    browser_overrides: dict[str, Any] = dict(binding.browser_overrides)
    user_data_dir = binding.user_data_dir

    user_data_dir.mkdir(parents=True, exist_ok=True)

    backups_enabled = settings.browser_session_backups_enabled
    if binding.session_backups_enabled is not None:
        backups_enabled = binding.session_backups_enabled
    # Default: disable backups for live runs unless explicitly enabled by CLI or profile
    if not dry_run and session_backups is None and binding.session_backups_enabled is None:
        backups_enabled = False
    backups_retention = settings.browser_session_backups_retention
    if binding.session_backups_retention is not None:
        try:
            backups_retention = max(1, int(binding.session_backups_retention))
        except (TypeError, ValueError):
            backups_retention = settings.browser_session_backups_retention

    backup_manager = SessionBackupManager(
        base=base,
        enabled=backups_enabled,
        retention=backups_retention,
    )
    restore_summary_payload: dict[str, Any] | None = None
    backup_summary_payload: dict[str, Any] | None = None

    def detect_session_corruption(directory: Path) -> tuple[bool, str]:
        if not directory.exists():
            return True, "missing_session_dir"
        preferences = directory / "Preferences"
        if not preferences.exists():
            return True, "missing_preferences"
        singleton_lock = directory / "SingletonLock"
        if singleton_lock.exists():
            return True, "singleton_lock_present"
        legacy_lock = directory / "LOCK"
        if legacy_lock.exists():
            return True, "lock_present"
        return False, ""

    viewport_override = browser_overrides.get("viewport", {}) if browser_overrides else {}
    profile_model = browser_overrides.get("model") if browser_overrides else None
    if not profile_model:
        profile_model = binding.model_overrides.get("llm")

    effective_model = (
        model
        or profile_model
        or settings.OPENROUTER_MODEL
        or settings.browser_model
    )
    if not effective_model:
        typer.secho(
            "No model configured. Set --model, profile.browser.model, or OPENROUTER_MODEL.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    effective_locale = browser_overrides.get("locale") if browser_overrides else None
    effective_timezone = browser_overrides.get("timezone") if browser_overrides else None
    viewport_width = viewport_override.get("width") if isinstance(viewport_override, dict) else None
    viewport_height = viewport_override.get("height") if isinstance(viewport_override, dict) else None

    allowed_domains_override = (
        browser_overrides.get("allowed_domains") if browser_overrides else None
    )
    pacing_override = browser_overrides.get("pacing") if browser_overrides else None

    readiness_retry_attempts = max(0, int(settings.search_ready_retry_attempts))
    readiness_backoff_seconds = max(0.0, float(settings.search_ready_backoff_seconds))
    readiness_min_cards = max(1, int(settings.search_ready_min_cards))
    selector_override = settings.search_ready_selector_override
    search_ready_override = None
    if browser_overrides:
        search_ready_override = (
            browser_overrides.get("search_ready")
            or browser_overrides.get("search_readiness")
        )
    if isinstance(search_ready_override, dict):
        if "retry_attempts" in search_ready_override:
            try:
                readiness_retry_attempts = max(0, int(search_ready_override["retry_attempts"]))
            except (TypeError, ValueError):
                pass
        if "backoff_seconds" in search_ready_override:
            try:
                readiness_backoff_seconds = max(
                    0.0, float(search_ready_override["backoff_seconds"])
                )
            except (TypeError, ValueError):
                pass
        if "min_cards" in search_ready_override:
            try:
                readiness_min_cards = max(1, int(search_ready_override["min_cards"]))
            except (TypeError, ValueError):
                pass
        if search_ready_override.get("selector_file"):
            selector_override = str(search_ready_override["selector_file"])
        elif search_ready_override.get("selector_override"):
            selector_override = str(search_ready_override["selector_override"])

    locale = effective_locale or settings.browser_locale
    timezone = effective_timezone or settings.browser_timezone
    width = viewport_width or settings.browser_viewport_width
    height = viewport_height or settings.browser_viewport_height
    chrome = (
        chrome_path
        or (browser_overrides.get("chrome_path") if browser_overrides else None)
        or settings.chrome_path
    )
    if isinstance(allowed_domains_override, (list, tuple, set)):
        allowed_domains = tuple(str(value).strip() for value in allowed_domains_override if str(value).strip())
    elif isinstance(allowed_domains_override, str):
        allowed_domains = tuple(part.strip() for part in allowed_domains_override.split(",") if part.strip())
    else:
        allowed_domains = settings.browser_allowed_domains
    wait_jitter_ms = (
        tuple(pacing_override.get("wait_jitter_ms"))
        if isinstance(pacing_override, dict)
        and pacing_override.get("wait_jitter_ms")
        and len(pacing_override["wait_jitter_ms"]) == 2
        else settings.browser_pacing_wait_jitter_ms
    )
    think_time_range_s = (
        tuple(pacing_override.get("think_time_range_s"))
        if isinstance(pacing_override, dict)
        and pacing_override.get("think_time_range_s")
        and len(pacing_override["think_time_range_s"]) == 2
        else settings.browser_pacing_think_time_range_s
    )

    log_event(
        {
            "event": "browser.session.prepared",
            "profileId": profile_id,
            "profile": binding.telemetry_payload(),
            "userDataDir": str(user_data_dir),
            "viewport": {"width": width, "height": height},
            "locale": locale,
            "timezone": timezone,
            "model": effective_model,
            "keepAlive": True,
            "guardrails": {"allowedDomains": list(allowed_domains)},
            "pacing": {
                "waitJitterMs": list(wait_jitter_ms),
                "thinkTimeRangeS": list(think_time_range_s),
            },
        }
    )
    if dry_run:
        log_event(
            {
                "event": "guardrail.dry_run.no_network",
                "message": "Dry-run mode prevents SimplyHired navigation side-effects.",
                "domains": list(allowed_domains),
                "profileId": profile_id,
                "profile": binding.telemetry_payload(),
            }
        )

    launch_config = BrowserLaunchConfig(
        profile_id=profile_id,
        user_data_dir=user_data_dir,
        model=str(effective_model),
        viewport_width=int(width),
        viewport_height=int(height),
        locale=str(locale),
        timezone=str(timezone),
        chrome_path=str(chrome) if chrome else None,
        keep_alive=True,
        guardrail_domains=tuple(allowed_domains),
        wait_jitter_ms=tuple(int(value) for value in wait_jitter_ms),
        think_time_range_s=tuple(float(value) for value in think_time_range_s),
        profile_metadata=binding.telemetry_payload(),
        profile_binding=binding.cli_payload(),
    )

    log_event(
        {
            "event": "guardrail.browser.stealth",
            "message": "Launching Browser-Use with stealth guardrails.",
            "profileId": profile_id,
            "profile": binding.telemetry_payload(),
            "sessionDir": str(user_data_dir),
            "guardrails": list(launch_config.guardrail_domains),
            "keepAlive": True,
            "pacing": {
                "waitJitterMs": list(launch_config.wait_jitter_ms),
                "thinkTimeRangeS": list(launch_config.think_time_range_s),
            },
        }
    )

    controller = BrowserUseController(launch_config)
    restore_attempted = False

    def attempt_open() -> Any:
        nonlocal controller, restore_attempted, restore_summary_payload
        while True:
            try:
                return controller.open_url(search_url)
            except BrowserUseError as exc:
                corrupted, reason = detect_session_corruption(user_data_dir)
                should_restore = not restore_attempted and (
                    isinstance(exc, BrowserLaunchError) or corrupted
                )
                if not should_restore:
                    raise
                summary = backup_manager.restore_latest(
                    profile_id,
                    user_data_dir,
                    run_id=None,
                )
                restore_summary_payload = summary.to_payload()
                restore_summary_payload["detectedReason"] = reason or "launch_error"
                restore_attempted = True
                if summary.status != "restored":
                    raise
                controller = BrowserUseController(launch_config)

    try:
        result = attempt_open()
    except BrowserUseError as exc:
        typer.secho(f"Failed to launch Browser-Use: {exc}", fg=typer.colors.RED)
        if restore_summary_payload:
            typer.echo(json.dumps({"restore": restore_summary_payload}, ensure_ascii=False))
        raise typer.Exit(code=1) from exc

    if result.status is BrowserActionStatus.ERROR:
        typer.secho(
            "Browser-Use failed to open the requested URL. See logs for details.",
            fg=typer.colors.RED,
        )
        typer.echo(json.dumps(result.details, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    summary_compiler = SummaryCompiler()

    payload: dict[str, Any] = {
        "status": result.status.value,
        "sessionId": controller.session_id,
        "profileId": profile_id,
        "userDataDir": str(user_data_dir),
        "model": str(effective_model),
        "locale": locale,
        "timezone": timezone,
        "viewport": {"width": width, "height": height},
        "chromePath": chrome,
        "dryRun": dry_run,
        "details": result.details,
        "telemetry": result.telemetry,
        "guardrails": {
            "allowedDomains": list(allowed_domains),
            "pacing": {
                "waitJitterMs": list(wait_jitter_ms),
                "thinkTimeRangeS": list(think_time_range_s),
            },
        },
        "profile": binding.cli_payload(),
        "preview": {},
    }
    payload["backups"] = {
        "enabled": backup_manager.is_enabled,
        "retention": backups_retention,
        "restoreAttempt": restore_summary_payload,
    }
    telemetry_payload = payload.setdefault("telemetry", {})
    telemetry_payload["sessionBackups"] = {
        "enabled": backup_manager.is_enabled,
        "retention": backups_retention,
        "restoreAttempt": restore_summary_payload,
    }

    store = RunStore(base=base)
    selectors_base = (
        base / "sites" / "simplyhired" / "selectors" / "search-readiness.json"
    )
    override_paths: list[Path] = []
    if selector_override:
        override_path = Path(selector_override)
        if not override_path.is_absolute():
            override_path = (base / selector_override).resolve()
        if override_path.exists():
            override_paths.append(override_path)
        else:
            log_event(
                {
                    "level": "warning",
                    "event": "search.readiness.selector_missing",
                    "message": "Configured selector override not found; using base selectors.",
                    "path": str(override_path),
                }
            )
    if not selectors_base.exists():
        typer.secho(
            f"Selector map not found at {selectors_base}.", fg=typer.colors.RED
        )
        raise typer.Exit(code=1)

    quick_apply_selectors_base = (
        base / "sites" / "simplyhired" / "selectors" / "quick-apply.json"
    )
    quick_apply_override_paths: list[Path] = []
    quick_apply_inline_overrides: list[Mapping[str, Any]] = []
    qa_selector_override = settings.quick_apply_selector_override
    if qa_selector_override:
        qa_path = Path(qa_selector_override)
        if not qa_path.is_absolute():
            qa_path = (base / qa_selector_override).resolve()
        if qa_path.exists():
            quick_apply_override_paths.append(qa_path)
        else:
            log_event(
                {
                    "level": "warning",
                    "event": "quick_apply.selector_missing",
                    "message": "Configured Quick Apply selector override not found; using base selectors.",
                    "path": str(qa_path),
                }
            )
    qa_overrides = binding.qa_overrides or {}
    qa_override_keys = (
        "quick_apply_selector_override",
        "quick_apply_selector_file",
        "quick_apply_selectors",
    )
    for key in qa_override_keys:
        if key not in qa_overrides:
            continue
        value = qa_overrides[key]
        if value is None:
            continue
        if isinstance(value, Mapping):
            quick_apply_inline_overrides.append(value)
            continue
        text_value = str(value).strip()
        if not text_value:
            continue
        if text_value.startswith("{"):
            try:
                quick_apply_inline_overrides.append(json.loads(text_value))
            except json.JSONDecodeError as exc:
                log_event(
                    {
                        "level": "warning",
                        "event": "quick_apply.selector_inline_invalid",
                        "message": "Failed to parse inline Quick Apply selector override; ignoring.",
                        "error": str(exc),
                    }
                )
            continue
        override_path = Path(text_value)
        if not override_path.is_absolute():
            override_path = (base / text_value).resolve()
        if override_path.exists():
            if override_path not in quick_apply_override_paths:
                quick_apply_override_paths.append(override_path)
        else:
            log_event(
                {
                    "level": "warning",
                    "event": "quick_apply.selector_missing",
                    "message": "Profile Quick Apply selector override not found; using base selectors.",
                    "path": str(override_path),
                }
            )

    readiness_record = None
    try:
        readiness_record = store.start_search_readiness_run(
            profile_id=profile_id,
            search_url=search_url,
            dry_run=dry_run,
            profile_binding=binding.telemetry_payload(),
        )
        readiness_dir = readiness_record.run_dir / "search-ready"
        readiness_dir.mkdir(parents=True, exist_ok=True)

        detector = SearchReadinessDetector.load(
            selectors_base, overrides=override_paths
        )
        if readiness_min_cards != detector.config.min_cards:
            detector.config.min_cards = readiness_min_cards

        attempts_payload: list[dict[str, Any]] = []
        artifacts_html: list[str] = []
        success_result = None
        last_result = None
        failure_reason: str | None = None
        start_time = time.monotonic()
        total_attempts = 1 + readiness_retry_attempts
        backup_executor: ThreadPoolExecutor | None = None
        backup_future = None

        for attempt in range(1, total_attempts + 1):
            idle_result = controller.wait_for_idle(timeout=5.0)
            if idle_result.status is BrowserActionStatus.ERROR:
                error_message = idle_result.details.get("error")
                failure_reason = "wait_for_idle_failed"
                attempts_payload.append(
                    {
                        "attempt": attempt,
                        "ok": False,
                        "error": error_message,
                        "artifact": None,
                    }
                )
                log_event(
                    {
                        "level": "error",
                        "event": "search.readiness.wait_failed",
                        "runId": readiness_record.id,
                        "attempt": attempt,
                        "error": error_message,
                    }
                )
                break

            html_result = controller.get_page_html()
            if html_result.status is BrowserActionStatus.ERROR:
                error_message = html_result.details.get("error")
                failure_reason = "capture_failed"
                attempts_payload.append(
                    {
                        "attempt": attempt,
                        "ok": False,
                        "error": error_message,
                        "artifact": None,
                    }
                )
                log_event(
                    {
                        "level": "error",
                        "event": "search.readiness.capture_failed",
                        "runId": readiness_record.id,
                        "attempt": attempt,
                        "error": error_message,
                    }
                )
                break

            html = html_result.details.get("html", "")
            html_path = readiness_dir / f"attempt-{attempt}.html"
            html_path.write_text(html, encoding="utf-8")
            result_eval = detector.evaluate(html)
            last_result = result_eval
            attempt_payload = {
                "attempt": attempt,
                "ok": result_eval.ok,
                "jobCards": result_eval.job_card_count,
                "detailFound": result_eval.detail_found,
                "variant": result_eval.variant_id,
                "jobCardSelector": result_eval.job_card_selector,
                "detailSelector": result_eval.detail_selector,
                "artifact": str(html_path),
                "reason": result_eval.diagnostics.get("reason"),
            }
            attempts_payload.append(attempt_payload)
            artifacts_html.append(str(html_path))
            log_event(
                {
                    "event": "search.readiness.attempt",
                    "runId": readiness_record.id,
                    "attempt": attempt,
                    "jobCards": result_eval.job_card_count,
                    "detailFound": result_eval.detail_found,
                    "variant": result_eval.variant_id,
                }
            )
            if result_eval.ok:
                success_result = result_eval
                break
            failure_reason = attempt_payload["reason"] or "incomplete"
            if attempt < total_attempts:
                log_event(
                    {
                        "event": "search.readiness.retry",
                        "runId": readiness_record.id,
                        "attempt": attempt,
                        "reason": failure_reason,
                        "waitSeconds": readiness_backoff_seconds,
                        "remaining": total_attempts - attempt,
                    }
                )
                if readiness_backoff_seconds > 0:
                    time.sleep(readiness_backoff_seconds)

        duration = round(time.monotonic() - start_time, 3)
        selectors_info = {
            "base": str(selectors_base),
            "overrides": [str(path) for path in override_paths],
        }
        if success_result:
            readiness_payload = {
                "status": "ready",
                "runId": readiness_record.id,
                "variant": success_result.variant_id,
                "jobCardCount": success_result.job_card_count,
                "detailFound": success_result.detail_found,
            }
            log_event(
                {
                    "event": "SEARCH_READY",
                    "runId": readiness_record.id,
                    "variant": success_result.variant_id,
                    "jobCards": success_result.job_card_count,
                    "detailFound": True,
                    "attempts": len(attempts_payload),
                    "durationSeconds": duration,
                    "artifactHtml": attempts_payload[-1]["artifact"],
                }
            )
            if backup_manager.is_enabled:
                backup_executor = ThreadPoolExecutor(max_workers=1)
                backup_future = backup_executor.submit(
                    backup_manager.create_backup,
                    profile_id,
                    user_data_dir,
                    run_id=readiness_record.id,
                )
            else:
                summary = backup_manager.create_backup(
                    profile_id,
                    user_data_dir,
                    run_id=readiness_record.id,
                )
                backup_summary_payload = summary.to_payload()
        else:
            job_cards = last_result.job_card_count if last_result else 0
            detail_found = last_result.detail_found if last_result else False
            variant_id = last_result.variant_id if last_result else None
            reason = failure_reason or (
                last_result.diagnostics.get("reason") if last_result else "unknown"
            )
            readiness_payload = {
                "status": "unready",
                "runId": readiness_record.id,
                "variant": variant_id,
                "jobCardCount": job_cards,
                "detailFound": detail_found,
                "reason": reason,
            }
            log_event(
                {
                    "level": "error",
                    "event": "SEARCH_UNREADY",
                    "runId": readiness_record.id,
                    "variant": variant_id,
                    "jobCards": job_cards,
                    "detailFound": detail_found,
                    "reason": reason,
                    "attempts": len(attempts_payload),
                    "durationSeconds": duration,
                    "artifactHtml": attempts_payload[-1]["artifact"]
                    if attempts_payload
                    else None,
                }
            )

        readiness_payload.update(
            {
                "selectors": selectors_info,
                "retry": {
                    "maxRetries": readiness_retry_attempts,
                    "backoffSeconds": readiness_backoff_seconds,
                },
                "attempts": attempts_payload,
                "artifacts": {"html": artifacts_html},
                "durationSeconds": duration,
                "minCardCount": detector.config.min_cards,
            }
        )
        store.record_search_readiness(readiness_record, readiness_payload)

        if backup_future:
            try:
                summary = backup_future.result()
                backup_summary_payload = summary.to_payload()
            finally:
                if backup_executor:
                    backup_executor.shutdown(wait=False)

        if readiness_record and restore_summary_payload and "runId" not in restore_summary_payload:
            restore_summary_payload["runId"] = readiness_record.id

        store.record_session_backup(
            readiness_record,
            enabled=backup_manager.is_enabled,
            retention=backups_retention,
            last_backup=backup_summary_payload,
            restore=restore_summary_payload,
        )

        payload["run"] = {
            "id": readiness_record.id,
            "artifactsDir": str(readiness_record.run_dir),
        }
        payload["readiness"] = readiness_payload
        payload["telemetry"]["searchReadiness"] = {
            "status": readiness_payload["status"],
            "attempts": len(attempts_payload),
            "durationSeconds": duration,
            "variant": readiness_payload.get("variant"),
        }
        if backup_summary_payload:
            payload["backups"]["lastBackup"] = backup_summary_payload
            payload["telemetry"]["sessionBackups"]["lastBackup"] = backup_summary_payload
        payload["limit"] = limit

        if readiness_payload["status"] != "ready":
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            raise typer.Exit(code=1)

        if not quick_apply_selectors_base.exists():
            typer.secho(
                f"Quick Apply selector map not found at {quick_apply_selectors_base}.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        discovery_dir = readiness_record.run_dir / "quick-apply"
        discovery = QuickApplyDiscovery.load(
            quick_apply_selectors_base,
            overrides=quick_apply_override_paths,
            inline_overrides=quick_apply_inline_overrides,
            attempt_trigger=(not dry_run),
            simple_click=simple_click,
        )
        summary = discovery.run(
            controller,
            run_dir=discovery_dir,
            limit=limit,
        )
        discovery_payload = summary.to_payload()
        discovery_payload["selectors"] = {
            "base": str(quick_apply_selectors_base),
            "overrides": [str(path) for path in quick_apply_override_paths],
            "inlineOverrideCount": len(quick_apply_inline_overrides),
        }
        store.record_quick_apply_discovery(readiness_record, discovery_payload)
        payload["discovery"] = discovery_payload
        payload["telemetry"]["quickApplyDiscovery"] = summary.telemetry_payload()

        form_selectors_base = (
            base / "sites" / "simplyhired" / "selectors" / "form-fields.json"
        )
        if not form_selectors_base.exists():
            typer.secho(
                f"Form selector map not found at {form_selectors_base}.",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

        form_selector_overrides: list[Path] = []
        if profile_id:
            profile_override = (
                base
                / "data"
                / "profiles"
                / profile_id
                / "selectors"
                / "form-fields.json"
            )
            if profile_override.exists():
                form_selector_overrides.append(profile_override)

        try:
            selector_library = FormSelectorLibrary.load(
                form_selectors_base, overrides=form_selector_overrides
            )
        except (FileNotFoundError, ValueError) as exc:
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc

        form_plan_artifacts: list[dict[str, Any]] = []
        generated_plans: list[tuple[FormFillPlan, str]] = []
        total_steps = 0
        total_mapped = 0
        total_unmapped = 0
        browser_use_version = "0.7.9"

        for artifact_path in discovery_payload.get("artifacts", []):
            artifact = Path(artifact_path)
            if not artifact.exists():
                log_event(
                    {
                        "level": "warning",
                        "event": "FORM_ARTIFACT_MISSING",
                        "path": artifact_path,
                    }
                )
                continue
            html = artifact.read_text(encoding="utf-8")
            mapper = FormStructureMapper(html, selector_library)
            plan = mapper.generate_plan()
            generated_plans.append((plan, artifact_path))
            plan_payload = plan.to_payload()
            plan_payload["artifact"] = artifact_path
            form_plan_artifacts.append(plan_payload)
            summary_payload = plan_payload["summary"]
            total_steps += int(summary_payload.get("steps", 0))
            total_mapped += int(summary_payload.get("mappedFields", 0))
            total_unmapped += int(summary_payload.get("unmappedFields", 0))
            for step_plan in plan.steps:
                log_event(
                    {
                        "event": "FORM_MAPPED",
                        "step": step_plan.step_id,
                        "artifact": artifact_path,
                        "mappedFields": len(step_plan.mapped),
                        "unmappedFields": len(step_plan.unmapped),
                        "profileId": profile_id,
                        "browserUseVersion": browser_use_version,
                    }
                )
                for unmapped_field in step_plan.unmapped:
                    log_event(
                        {
                            "level": "warning",
                            "event": "FORM_UNMAPPED",
                            "step": step_plan.step_id,
                            "profileId": profile_id,
                            "reason": unmapped_field.reason,
                            "diagnostics": unmapped_field.diagnostics,
                            "artifact": artifact_path,
                            "browserUseVersion": browser_use_version,
                        }
                    )

        form_plan_summary = {
            "artifacts": len(form_plan_artifacts),
            "steps": total_steps,
            "mappedFields": total_mapped,
            "unmappedFields": total_unmapped,
        }
        form_plan_payload = {
            "artifacts": form_plan_artifacts,
            "summary": form_plan_summary,
            "selectors": {
                "base": str(form_selectors_base),
                "overrides": [str(path) for path in form_selector_overrides],
            },
        }
        payload["formPlan"] = form_plan_payload
        payload["telemetry"]["formMapping"] = form_plan_summary | {
            "browserUseVersion": browser_use_version,
        }
        if readiness_record:
            store.record_form_plan(readiness_record, form_plan_payload)

        history_writer = HistoryWriter(base=base)
        context = get_run_context()
        if context:
            history_writer.append_form_plan(
                context,
                profile_id=profile_id,
                search_url=search_url,
                summary=form_plan_summary,
                dry_run=dry_run,
            )

        form_fill_payload: dict[str, Any] | None = None
        fill_result = None
        resume_result = None
        if generated_plans:
            resolver = ProfileAnswerResolver(profile=profile_config, binding=binding)
            executor = FormFillExecutor(controller, resolver, max_retries=1)
            plan_to_fill, plan_artifact = generated_plans[-1]
            fill_result = executor.execute(plan_to_fill, artifact=plan_artifact)
            form_fill_payload = {
                "artifacts": [fill_result.to_payload()],
                "summary": {
                    "artifacts": 1,
                    "filledFields": fill_result.filled_count(),
                    "skippedFields": fill_result.skipped_count(),
                    "issues": fill_result.issue_count(),
                },
            }
            payload["formFill"] = form_fill_payload
            telemetry_summary = form_fill_payload["summary"]
            payload["telemetry"]["formFill"] = telemetry_summary
            if readiness_record:
                store.record_form_fill(readiness_record, form_fill_payload)
            if fill_result.steps:
                typer.echo("\nForm fill summary:")
                typer.echo(f"{'Step':<28}{'Filled':>8}{'Skipped':>10}{'Issues':>8}")
                for step_result in fill_result.steps:
                    typer.echo(
                        f"{step_result.title[:28]:<28}{len(step_result.filled):>8}{len(step_result.skipped):>10}{len(step_result.issues):>8}"
                    )
            if context:
                history_writer.append_form_fill(
                    context,
                    profile_id=profile_id,
                    search_url=search_url,
                    summary=telemetry_summary,
                    dry_run=dry_run,
                )

            resume_field = None
            for step in plan_to_fill.steps:
                for field in step.mapped:
                    profile_key = field.profile_field.lower()
                    widget = field.widget_type.lower()
                    if "resume" in profile_key or widget == "file":
                        resume_field = field
                        break
                if resume_field:
                    break

            if resume_field and readiness_record:
                step_lookup = {step.step_id: step.title for step in plan_to_fill.steps}
                uploader = ResumeUploader(
                    controller,
                    resume_path=binding.resume_path,
                    dry_run=dry_run,
                    run_dir=readiness_record.run_dir,
                    step_lookup=step_lookup,
                )
                resume_result = uploader.upload(
                    selector=resume_field.selector,
                    step_id=resume_field.step,
                )
                resume_payload = resume_result.to_payload()
                payload["resumeUpload"] = resume_payload
                payload["telemetry"]["resumeUpload"] = resume_result.telemetry_payload()
                store.record_resume_upload(readiness_record, resume_payload)
                typer.echo(
                    "Resume upload: "
                    f"{resume_result.status} (attempts={resume_result.attempts}, simulated={resume_result.simulated})"
                )
                if context:
                    history_writer.append_resume_upload(
                        context,
                        profile_id=profile_id,
                        search_url=search_url,
                        summary=resume_payload,
                        dry_run=dry_run,
                    )
            elif binding.resume_path and readiness_record and plan_to_fill.steps:
                step_lookup = {step.step_id: step.title for step in plan_to_fill.steps}
                uploader = ResumeUploader(
                    controller,
                    resume_path=binding.resume_path,
                    dry_run=dry_run,
                    run_dir=readiness_record.run_dir,
                    step_lookup=step_lookup,
                )
                fallback_step = plan_to_fill.steps[0]
                fallback_selector = "input[type=file]"
                log_event(
                    {
                        "event": "resume.upload.fallback",
                        "selector": fallback_selector,
                        "step": fallback_step.step_id,
                        "profileId": profile_id,
                    }
                )
                resume_result = uploader.upload(
                    selector=fallback_selector,
                    step_id=fallback_step.step_id,
                )
                resume_payload = resume_result.to_payload()
                payload["resumeUpload"] = resume_payload
                payload["telemetry"]["resumeUpload"] = resume_result.telemetry_payload()
                store.record_resume_upload(readiness_record, resume_payload)
                if context:
                    history_writer.append_resume_upload(
                        context,
                        profile_id=profile_id,
                        search_url=search_url,
                        summary=resume_payload,
                        dry_run=dry_run,
                    )
            elif binding.resume_path and readiness_record:
                log_event(
                    {
                        "level": "warning",
                        "event": "resume.upload.skipped",
                        "reason": "selector_missing",
                        "profileId": profile_id,
                    }
                )

        if readiness_record:
            posting_metadata: dict[str, object] = {
                "postingUrl": search_url,
                "title": None,
                "company": None,
                "location": None,
            }
            candidates = discovery_payload.get("candidates") if discovery_payload else None
            if isinstance(candidates, list):
                first_candidate = candidates[0] if candidates else None
                for candidate in candidates or []:
                    if candidate.get("status") == "opened":
                        first_candidate = candidate
                        break
                if isinstance(first_candidate, dict):
                    if first_candidate.get("title"):
                        posting_metadata["title"] = first_candidate.get("title")
                    if first_candidate.get("url"):
                        posting_metadata["postingUrl"] = first_candidate.get("url")
            summary_payload_obj = summary_compiler.compile(
                run_id=readiness_record.id,
                dry_run=dry_run,
                posting=posting_metadata,
                form_result=fill_result,
                resume_result=resume_result,
            )
            summary_preview = summary_payload_obj.to_preview_payload()
            summary_dir = readiness_record.run_dir / "summary"
            summary_dir.mkdir(parents=True, exist_ok=True)
            screenshot_target = summary_dir / "pre-submit.png"
            capture_result = controller.capture_review_artifacts(
                output_path=screenshot_target,
                summary_html=summary_payload_obj.render_html(),
            )
            capture_payload = capture_result.to_payload()
            preview_section = payload.setdefault("preview", {})
            preview_section["summary"] = summary_preview
            preview_section["screenshot"] = capture_payload
            if capture_payload.get("path"):
                preview_section["screenshotPath"] = capture_payload.get("path")
            summary_telemetry = summary_payload_obj.telemetry_payload()
            screenshot_telem = capture_result.telemetry_payload()
            screenshot_telem["path"] = capture_payload.get("path")
            summary_telemetry["screenshot"] = screenshot_telem
            payload["telemetry"]["summary"] = summary_telemetry
            store.record_preview_summary(
                readiness_record,
                summary=summary_preview,
                screenshot=capture_payload,
            )
            if context:
                history_writer.append_preview_summary(
                    context,
                    profile_id=profile_id,
                    search_url=search_url,
                    summary=summary_preview,
                    screenshot=capture_payload,
                    dry_run=dry_run,
                )
            log_event(
                {
                    "event": "SUMMARY_READY",
                    "runId": readiness_record.id,
                    "profileId": profile_id,
                    "dryRun": dry_run,
                    "summary": summary_telemetry,
                }
            )
            typer.echo("\nSubmission summary:")
            headline = summary_preview.get("headline", {})
            typer.echo(f"  Job: {headline.get('title') or 'â€”'}")
            typer.echo(f"  Company: {headline.get('company') or 'â€”'}")
            typer.echo(f"  Location: {headline.get('location') or 'â€”'}")
            form_counts = summary_preview.get("form", {})
            typer.echo(
                f"  Form: filled={form_counts.get('filledFields', 0)} "
                f"skipped={form_counts.get('skippedFields', 0)} "
                f"issues={form_counts.get('issues', 0)}"
            )
            resume_preview = summary_preview.get("resume") or {}
            if resume_preview:
                typer.echo(
                    f"  Resume: status={resume_preview.get('status')} "
                    f"attempts={resume_preview.get('attempts')} "
                    f"simulated={resume_preview.get('simulated')}"
                )
            typer.echo(f"  Screenshot: {capture_payload.get('path')}")

        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    finally:
        if readiness_record:
            set_run_context(None)


@preview_app.command("demo")
def preview_demo(
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Skip launching Chrome in app-mode; server still runs.",
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        min=1024,
        max=65535,
        help="Override preview server port (defaults to config value).",
    ),
):
    """Start the preview FastAPI server and open the UI in Chrome app-mode."""

    overrides = {"dry_run": True}
    if port is not None:
        overrides["preview_port"] = port
    settings = Settings.load(overrides=overrides)
    base = get_base_dir()
    service = ProfileService(base=base)
    binding_payload = None
    if settings.active_profile:
        binding = service.build_binding(settings.active_profile)
        if binding:
            binding_payload = binding.cli_payload()
    run_store = RunStore(base=base)
    record = run_store.start_demo_run(
        profile_id=settings.active_profile,
        profile_binding=binding_payload,
    )
    run_store.bootstrap_demo_preview(record, limit=1, profile_id=settings.active_profile)
    log_event(
        {
            "event": "preview.demo_initialized",
            "message": "Preview server demo session initialized.",
            "port": settings.preview_port,
        }
    )
    log_event(
        {
            "event": "guardrail.demo.no_network",
            "message": "Preview demo enforces dry-run guardrails; no SimplyHired navigation will occur.",
            "domains": ["*.simplyhired.com"],
            "mode": "demo",
        }
    )
    context = get_run_context()
    writer = HistoryWriter()
    if context:
        writer.append_demo_entry(
            context,
            summary="Preview demo session initialized; UI interactions will be redacted.",
            decision="initialized",
        )
    typer.echo(
        f"Starting preview server on http://localhost:{settings.preview_port}/ui (demo mode, dry-run)."
    )
    run_preview_service(
        settings,
        demo=True,
        open_browser=not no_browser,
        run_record=record,
        run_store=run_store,
        history_writer=writer,
        run_context=context,
    )


@preview_app.command("run")
def preview_run(
    run_id: str = typer.Argument(
        ..., help="Existing run identifier (folder name under runs/)."
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Skip launching Chrome; preview server remains available.",
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        min=1024,
        max=65535,
        help="Override preview server port (defaults to config value).",
    ),
):
    """Launch the preview FastAPI server for an existing automation run."""

    overrides: dict[str, object] = {}
    if port is not None:
        overrides["preview_port"] = port
    settings = Settings.load(overrides=overrides)
    base = get_base_dir()
    run_store = RunStore(base=base)
    try:
        record = run_store.load_run_record(run_id)
    except FileNotFoundError:
        typer.secho(
            f"Run '{run_id}' was not found under {run_store.runs_dir}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    except json.JSONDecodeError as exc:
        typer.secho(
            f"Run '{run_id}' has an invalid run.json: {exc}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1) from exc

    context = RunContext(
        id=record.id,
        started_at=record.started_at,
        run_dir=record.run_dir,
        run_json_path=record.run_json_path,
        logs_path=record.logs_path,
        profile_id=record.profile_id,
        mode="review",
    )
    previous_context = set_run_context(context)
    history_writer = HistoryWriter(base=base)
    log_event(
        {
            "event": "preview.run.launch",
            "message": "Launching preview server for existing run.",
            "runId": record.id,
            "port": settings.preview_port,
        }
    )
    typer.echo(
        f"Starting preview server for run {record.id} on "
        f"http://localhost:{settings.preview_port}/ui"
    )
    try:
        run_preview_service(
            settings,
            demo=False,
            open_browser=not no_browser,
            run_record=record,
            run_store=run_store,
            history_writer=history_writer,
            run_context=context,
        )
    finally:
        set_run_context(previous_context)


@profiles_app.command("new")
def profiles_new(
    profile_id: str = typer.Argument(..., help="Profile identifier (slug)."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing profile template."),
):
    """Create a new profile YAML template and supporting directories."""

    service = ProfileService()
    try:
        created = service.create_profile(profile_id, force=force)
    except FileExistsError as exc:
        typer.secho("Profile already exists; use --force to overwrite.", fg=typer.colors.RED)
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.secho(f"Profile template created at {created}", fg=typer.colors.GREEN)
    resume_hint = service.resumes_dir / profile_id / "resume.pdf"
    typer.echo("Next steps:")
    typer.echo("  - Fill in identity/contact fields and QA overrides in the YAML file.")
    typer.echo(f"  - Place a resume PDF at {resume_hint}.")
    typer.echo(
        f"  - Run `python app.py profiles validate {profile_id}` to confirm the profile is ready."
    )


@profiles_app.command("validate")
def profiles_validate(profile_id: str = typer.Argument(..., help="Profile identifier to validate.")):
    """Validate a profile YAML against the schema and resume requirements."""

    service = ProfileService()
    try:
        binding = service.bind_profile(profile_id)
    except ApiError as error:
        typer.secho(error.to_json(), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"Profile '{profile_id}' is valid.", fg=typer.colors.GREEN)
    typer.echo(json.dumps(binding.cli_payload(), ensure_ascii=False, indent=2))


@profiles_app.command("list")
def profiles_list():
    """List available profiles with their validation status."""

    service = ProfileService()
    data = service.list_profiles()
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@profiles_app.command("use")
def profiles_use(profile_id: str = typer.Argument(..., help="Profile identifier to activate.")):
    """Set the active profile for subsequent CLI runs."""

    service = ProfileService()
    try:
        binding = service.bind_profile(profile_id)
    except ApiError as error:
        typer.secho(error.to_json(), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    marker = service.set_active_profile(profile_id)
    typer.secho(f"Active profile set to '{profile_id}'.", fg=typer.colors.GREEN)
    typer.echo(
        json.dumps(
            {"marker": str(marker), "profile": binding.cli_payload()},
            ensure_ascii=False,
            indent=2,
        )
    )


@profiles_app.command("current")
def profiles_current():
    """Display the active profile metadata."""

    service = ProfileService()
    data = service.current_profile()
    if not data:
        typer.secho("No active profile set. Use `profiles use <id>` first.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@history_app.command("path")
def history_path():
    """Show history folder path."""
    base = get_base_dir()
    typer.echo(str((base / "history").resolve()))


@history_app.command("summary")
def history_summary(
    last: bool = typer.Option(False, "--last", help="Show only the most recent entry."),
    limit: int = typer.Option(5, "--limit", min=1, max=100, help="Number of entries to display."),
    json_output: bool = typer.Option(
        False, "--json", help="Return structured JSON instead of a table."
    ),
):
    """Render aggregated decision history with queue depth metrics."""

    base = get_base_dir()
    history_path = base / "history" / "history.jsonl"
    if not history_path.exists():
        typer.secho("No history entries found. Run a preview/apply session first.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    lines = history_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        typer.secho("History file is empty.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    count = 1 if last else limit
    selected = lines[-count:]
    summaries = []
    for line in reversed(selected):  # newest first
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        summaries.append(_summarize_history_entry(entry))

    if not summaries:
        typer.secho("No parsable history entries were found.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(summaries, ensure_ascii=False, indent=2))
        return

    _print_history_table(summaries)


def _summarize_history_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    decisions = entry.get("decisions") or {}
    by_outcome = decisions.get("byOutcome") or {}
    queue_depth = entry.get("queueDepth") or {}
    approved = _safe_int(by_outcome.get("approve"))
    aborted = _safe_int(by_outcome.get("abort"))
    needs_review_direct = _safe_int(by_outcome.get("needs_review"))
    edit_requests = _safe_int(by_outcome.get("edit_request"))
    needs_review_total = needs_review_direct + edit_requests
    escalated = _safe_int(queue_depth.get("escalated"))
    pending = _safe_int(queue_depth.get("pending"))
    decided = _safe_int(queue_depth.get("decided"))
    decision_ref = entry.get("decision") or {}
    return {
        "runId": entry.get("id"),
        "mode": entry.get("mode"),
        "status": entry.get("status"),
        "timestamp": entry.get("timestamp"),
        "profileId": entry.get("profileId"),
        "postingUrl": entry.get("postingUrl"),
        "jobTitle": entry.get("jobTitle"),
        "company": entry.get("company"),
        "location": entry.get("location"),
        "approved": approved,
        "aborted": aborted,
        "needs_review": needs_review_total,
        "edit_requests": edit_requests,
        "escalated": escalated,
        "queue_pending": pending,
        "queue_decided": decided,
        "lastDecisionAt": decisions.get("lastDecisionAt"),
        "decisionId": decision_ref.get("id"),
        "rationaleRedacted": bool(decision_ref.get("rationaleRedacted", False)),
    }


@apply_app.command("queue")
def apply_queue(
    run: str = typer.Option(..., help="Run identifier to modify."),
    candidate: str = typer.Option(..., help="Candidate identifier to override."),
    action: str = typer.Option(
        ..., help="Action to perform: escalate or assign-ai.", case_sensitive=False
    ),
    reason: Optional[str] = typer.Option(
        None,
        help="Optional human-readable reason stored with the override entry.",
    ),
):
    """Manage queue overrides for a run without using the UI."""

    base = get_base_dir()
    store = RunStore(base=base)
    try:
        record = store.load_run_record(run)
    except FileNotFoundError:
        typer.secho(f"Run {run} not found.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    manager = ReviewQueueManager(run_store=store, run_record=record)
    candidate_obj = manager.snapshot.find_candidate(candidate)
    if not candidate_obj:
        typer.secho(
            f"Candidate {candidate} not present in queue {run}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    normalized = action.lower().replace("_", "-")
    trigger = "cli_override"
    desired_mode: str
    if normalized == "escalate":
        desired_mode = "human"
        default_reason = "escalate"
        success_message = (
            f"Candidate {candidate} escalated to human lane for run {run}."
        )
    elif normalized in {"assign-ai", "assignai", "assign"}:
        desired_mode = "ai"
        default_reason = "assign_ai"
        success_message = (
            f"Candidate {candidate} reassigned to AI lane for run {run}."
        )
    else:
        typer.secho(
            "Unsupported action. Use 'escalate' or 'assign-ai'.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if candidate_obj.assigned_mode == desired_mode:
        typer.secho(
            f"Candidate {candidate} already assigned to {desired_mode} mode.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=0)

    try:
        manager.assign_mode(
            candidate,
            desired_mode,
            trigger=trigger,
            reason=reason or default_reason,
        )
    except KeyError:
        typer.secho(
            f"Candidate {candidate} not present in queue {run}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    store.record_queue_override(
        record,
        candidate_id=candidate,
        assigned_mode=desired_mode,
        reason=reason or default_reason,
        trigger=trigger,
    )

    timeout = int(os.environ.get("JAA_QUEUE_WATCHDOG_TIMEOUT", "30"))
    triggered = manager.enforce_watchdog(timeout)
    if triggered:
        typer.secho(
            f"Watchdog reassigned {len(triggered)} candidate(s) to human lane.",
            fg=typer.colors.YELLOW,
        )

    typer.secho(success_message, fg=typer.colors.GREEN)


def _print_history_table(rows: Sequence[Mapping[str, Any]]) -> None:
    headers = [
        "Run",
        "Mode",
        "Status",
        "Approved",
        "Escalated",
        "Aborted",
        "NeedsRev",
        "Queue P/E/D",
        "Last Decision",
        "Redacted",
    ]
    table = []
    for row in rows:
        queue_repr = f"{row['queue_pending']}/{row['escalated']}/{row['queue_decided']}"
        table.append(
            [
                str(row.get("runId") or "-"),
                str(row.get("mode") or "-"),
                str(row.get("status") or "-"),
                str(row.get("approved", 0)),
                str(row.get("escalated", 0)),
                str(row.get("aborted", 0)),
                str(row.get("needs_review", 0)),
                queue_repr,
                str(row.get("lastDecisionAt") or "-"),
                "yes" if row.get("rationaleRedacted") else "no",
            ]
        )

    widths = [
        max(len(header), *(len(row[idx]) for row in table))
        for idx, header in enumerate(headers)
    ]
    header_line = "  ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    typer.secho(header_line, fg=typer.colors.CYAN)
    divider = "  ".join("-" * width for width in widths)
    typer.secho(divider, fg=typer.colors.CYAN)
    for row in table:
        typer.echo("  ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


app.add_typer(apply_app, name="apply")
app.add_typer(preview_app, name="preview")
app.add_typer(profiles_app, name="profiles")
app.add_typer(config_app, name="config")
app.add_typer(history_app, name="history")



def main():
    """Primary entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
