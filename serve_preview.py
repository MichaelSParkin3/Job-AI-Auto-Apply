"""Deprecated shim preserved for backward compatibility.

This module now only informs users to invoke the official Typer command:

    python app.py preview run <run-id>

The new command supports the same behavior and keeps CLI help/docs aligned
with the rest of the tooling.  This stub will be removed in a future release.
"""

from __future__ import annotations

import sys

import typer


def main(run_id: str | None = None) -> None:
    message = (
        "serve_preview.py has been deprecated. Use `python app.py preview run "
        f"{run_id or '<run-id>'}` instead."
    )
    typer.secho(message, fg=typer.colors.YELLOW)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
