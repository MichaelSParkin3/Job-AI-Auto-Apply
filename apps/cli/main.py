"""Typer CLI entry points for Job AI Auto Apply operations."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

import json
import time

import typer

from apps.browser import (
    BrowserActionStatus,
    BrowserLaunchConfig,
    BrowserLaunchError,
    BrowserUseController,
    BrowserUseError,
    SessionBackupManager,
)
from apps.preview.runner import run_preview_service
from sites.simplyhired.search_readiness import SearchReadinessDetector
from .config_loader import (
    Settings,
    ensure_runtime_dirs,
    get_base_dir,
    write_default_config,
)
from .history_store import HistoryWriter
from .profiles import ProfileBinding, ProfileService
from .run_store import RunStore
from .runtime_state import get_run_context, set_run_context
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
    session_backups: Optional[bool] = typer.Option(
        None,
        "--session-backups/--no-session-backups",
        help="Enable or disable Browser-Use session backups for this run.",
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

    browser_overrides: dict[str, Any] = dict(binding.browser_overrides)
    user_data_dir = binding.user_data_dir

    user_data_dir.mkdir(parents=True, exist_ok=True)

    backups_enabled = settings.browser_session_backups_enabled
    if binding.session_backups_enabled is not None:
        backups_enabled = binding.session_backups_enabled
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
                    readiness_record.id,
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

        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        if readiness_payload["status"] != "ready":
            raise typer.Exit(code=1)
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
