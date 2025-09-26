from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from apps.preview.runner import run_preview_service
from .config_loader import Settings, ensure_runtime_dirs, write_default_config


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
profiles_app = typer.Typer(help="Profile management (skeleton)")
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


@profiles_app.command("list")
def profiles_list():
    """List available profiles (skeleton)."""
    base = Path.cwd() / "data" / "profiles"
    if not base.exists():
        typer.echo("[]")
        return
    items = [p.stem for p in base.glob("*.yaml")]
    typer.echo(str(items))


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
