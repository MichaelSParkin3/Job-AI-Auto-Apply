"""Manage runtime state for CLI operations such as the active run context."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RunContext:
    """Represents metadata about the currently active run directory."""

    id: str
    started_at: datetime
    run_dir: Path
    run_json_path: Path
    logs_path: Path
    profile_id: Optional[str]


_run_context: contextvars.ContextVar[Optional[RunContext]] = contextvars.ContextVar(
    "run_context", default=None
)


def set_run_context(context: Optional[RunContext]) -> Optional[RunContext]:
    """Set the active run context, returning the previous value."""

    previous = _run_context.get(None)
    _run_context.set(context)
    return previous


def get_run_context() -> Optional[RunContext]:
    """Return the currently active run context if one has been registered."""

    return _run_context.get(None)

