"""Typer CLI entry points for Job AI Auto Apply operations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import json

import typer

from apps.browser import (
    BrowserActionStatus,
    BrowserLaunchConfig,
    BrowserUseController,
    BrowserUseError,
)
from apps.preview.runner import run_preview_service
from .config_loader import (
    Settings,
    ensure_runtime_dirs,
    get_base_dir,
    write_default_config,
)
from .history_store import HistoryWriter
from .profiles import ProfileBinding, ProfileService
from .run_store import RunStore
from .runtime_state import get_run_context
from .utils import ApiError, log_event


app = typer.Typer(help="Job AI Auto Apply CLI")


@app.callback()
def init(_: bool = typer.Option(False, "--version", help="Show version")):
    """Initialize the application state before running any command.

    Ensures that all required runtime directories exist.
    """
    # Create runtime dirs early (AC #4)
    ensure_runtime_dirs()


config_app = typer.Typer(help="Configuration commands")
apply_app = typer.Typer(help="Application/automation commands (skeleton)")
preview_app = typer.Typer(help="Preview server commands")
profiles_app = typer.Typer(help="Profile management commands")
history_app = typer.Typer(help="Run history utilities (skeleton)")


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


@apply_app.command("open")
def apply_open(
    search_url: str = typer.Argument(..., help="SimplyHired search URL to open."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Enforce dry-run guardrails."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Profile identifier to bind."),
    model: Optional[str] = typer.Option(None, "--model", help="Override Browser-Use model."),
    chrome_path: Optional[str] = typer.Option(
        None,
        "--chrome-path",
        help="Override Chrome executable path for this session.",
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

    browser_overrides: dict[str, Any] = dict(binding.browser_overrides)
    user_data_dir = binding.user_data_dir

    user_data_dir.mkdir(parents=True, exist_ok=True)

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
    try:
        result = controller.open_url(search_url)
    except BrowserUseError as exc:
        typer.secho(f"Failed to launch Browser-Use: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if result.status is BrowserActionStatus.ERROR:
        typer.secho(
            "Browser-Use failed to open the requested URL. See logs for details.",
            fg=typer.colors.RED,
        )
        typer.echo(json.dumps(result.details, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    payload = {
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
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


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
