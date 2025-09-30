from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import types
import webbrowser
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any

try:  # pragma: no cover - exercised when typer is not installed
    import typer
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
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
        Exit=RuntimeError,
        secho=_echo_stub,
        echo=_echo_stub,
        colors=types.SimpleNamespace(RED="red", GREEN="green", YELLOW="yellow"),
    )

from apps.cli.config_loader import Settings, get_base_dir
from apps.cli.history_store import HistoryWriter
from apps.cli.run_store import RunRecord, RunStore
from apps.cli.runtime_state import RunContext, set_run_context
from apps.preview.main import create_app

if TYPE_CHECKING:
    from uvicorn import Config, Server


def _resolve_chrome_path(settings: Settings) -> Optional[Path]:
    candidates = []
    if settings.chrome_path:
        candidates.append(Path(settings.chrome_path))
    if env_path := os.environ.get("JAA_CHROME_PATH"):
        candidates.append(Path(env_path))
    if sys.platform.startswith("win"):
        candidates.extend(
            Path(p)
            for p in (
                os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            )
            if p
        )
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def _launch_browser(url: str, settings: Settings) -> Optional[subprocess.Popen]:
    chrome_path = _resolve_chrome_path(settings)
    if chrome_path:
        args = [str(chrome_path), f"--app={url}", "--new-window"]
        try:
            return subprocess.Popen(args)
        except OSError as exc:
            typer.echo(f"Failed to launch Chrome app-mode: {exc}")
    typer.echo("Falling back to default browser (app-mode not available).")
    webbrowser.open(url)
    return None


def run_preview_service(
    settings: Settings,
    *,
    demo: bool = True,
    open_browser: bool = True,
    run_record: RunRecord | None = None,
    run_store: RunStore | None = None,
    history_writer: HistoryWriter | None = None,
    run_context: RunContext | None = None,
) -> None:
    """Run the preview FastAPI service with optional Chrome app-mode launcher."""

    # Defer uvicorn import so that test environments without the dependency can still import CLI modules.
    import uvicorn  # type: ignore

    os.environ.setdefault("JAA_DRY_RUN", "1" if demo else "0")

    base_dir = get_base_dir()
    static_dir = base_dir / "apps" / "ui" / "dist"
    app = create_app(
        static_dir=static_dir,
        demo=demo,
        run_record=run_record,
        run_store=run_store,
        history_writer=history_writer,
        run_context=run_context,
    )

    config: "Config" = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=settings.preview_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )
    server: "Server" = uvicorn.Server(config)

    def _run_server() -> None:
        if run_context:
            set_run_context(run_context)
        server.run()

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    started_attr = getattr(server, "started", None)
    if hasattr(started_attr, "wait"):
        started_attr.wait()
    elif hasattr(started_attr, "is_set"):
        while not started_attr.is_set():
            time.sleep(0.1)
    else:
        time.sleep(0.5)

    url = f"http://localhost:{settings.preview_port}/ui"
    typer.echo(f"Preview server is running at {url}")
    browser_proc: Optional[subprocess.Popen] = None
    if open_browser:
        browser_proc = _launch_browser(url, settings)

    try:
        while server_thread.is_alive():
            if getattr(app.state, "session_complete", False):
                typer.echo("Preview session complete; shutting down preview server.")
                server.should_exit = True
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        typer.echo("Shutting down preview server...")
        server.should_exit = True
    finally:
        if browser_proc and browser_proc.poll() is None:
            browser_proc.terminate()
            try:
                browser_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser_proc.kill()
        server.should_exit = True
        server_thread.join(timeout=5)
