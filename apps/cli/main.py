from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import json

import typer

from apps.preview.runner import run_preview_service
from .config_loader import Settings, ensure_runtime_dirs, write_default_config
from .profiles import ProfileService
from .utils import ApiError


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
def apply_demo(limit: int = typer.Option(1, help="Limit demo items"), dry_run: bool = True):
    """Run a placeholder demo of the application flow.

    This command simulates a dry-run of the job application process
    to demonstrate the flow without taking real action.

    Args:
        limit (int): The number of demo items to process.
        dry_run (bool): If True, runs in simulation mode.
    """
    _ = Settings.load(overrides={"dry_run": dry_run})
    typer.echo(f"Demo run initialized (limit={limit}, dry_run={dry_run})")


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
    typer.echo(
        f"Starting preview server on http://localhost:{settings.preview_port}/ui (demo mode, dry-run)."
    )
    run_preview_service(settings, demo=True, open_browser=not no_browser)


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
    result = service.validate_profile(profile_id)
    if result.is_valid and result.profile:
        typer.secho(f"Profile '{profile_id}' is valid.", fg=typer.colors.GREEN)
        output = {
            "id": profile_id,
            "display_name": result.profile.display_name,
            "resume_path": str(result.resume_path) if result.resume_path else None,
            "user_data_dir": str(result.profile.resolved_user_data_dir(service.base)),
        }
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
        return

    error = ApiError(
        code="profiles.validation_failed",
        message=f"Profile '{profile_id}' failed validation.",
        details={"errors": result.errors},
    )
    typer.secho(error.to_json(), fg=typer.colors.RED)
    raise typer.Exit(code=1)


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
    result = service.validate_profile(profile_id)
    if not result.profile:
        error = ApiError(
            code="profiles.not_found",
            message=f"Profile '{profile_id}' does not exist.",
            details={"errors": result.errors},
        )
        typer.secho(error.to_json(), fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if not result.is_valid:
        error = ApiError(
            code="profiles.invalid",
            message=f"Profile '{profile_id}' must pass validation before use.",
            details={"errors": result.errors},
        )
        typer.secho(error.to_json(), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    marker = service.set_active_profile(profile_id)
    typer.secho(f"Active profile set to '{profile_id}'.", fg=typer.colors.GREEN)
    typer.echo(json.dumps({"marker": str(marker)}, ensure_ascii=False, indent=2))


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
    typer.echo(str((Path.cwd() / "history").resolve()))


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
