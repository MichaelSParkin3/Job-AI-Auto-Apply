"""Guardrail tests for demo mode: ensure no SimplyHired network activity occurs.

These tests assert that the dry-run demo path does not attempt to resolve or
connect to SimplyHired domains. We patch low-level socket functions to capture
any attempted DNS lookups or network connections during the demo bootstrap.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Callable

import pytest

# Local imports from the repository codebase
from apps.cli.main import preview_demo


@pytest.fixture()
def no_network_guard(monkeypatch: pytest.MonkeyPatch):
    """Patch socket calls to record attempted outbound activity.

    Returns a dict with recorded hostnames and connect targets so the test can
    assert no network usage occurred during the demo preview.
    """

    recorded: dict[str, Any] = {"hostnames": [], "connects": []}

    real_getaddrinfo = socket.getaddrinfo
    real_socket = socket.socket

    def fake_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(host, str):
            recorded["hostnames"].append(host)
        return real_getaddrinfo(host, *args, **kwargs)

    class WrappedSocket(socket.socket):  # type: ignore[misc]
        def connect(self, address):  # type: ignore[override]
            recorded["connects"].append(address)
            return super().connect(address)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(socket, "socket", WrappedSocket)

    return recorded


def test_demo_path_avoids_simplyhired_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_network_guard
):
    """The preview demo should avoid any network to SimplyHired.* domains.

    This protects the user's environment from unintended automation or traffic
    during a dry-run demonstration.
    """

    # Run everything under an isolated base directory
    monkeypatch.setenv("JAA_BASE_DIR", str(tmp_path))

    # Do not actually launch the preview server/browser in this test; stub it.
    monkeypatch.setattr(
        "apps.cli.main.run_preview_service", lambda *args, **kwargs: None
    )

    # Execute the demo bootstrap
    preview_demo(no_browser=True, port=None)

    # Assert that no resolution or connection targeted SimplyHired domains
    hostnames = [h.lower() for h in no_network_guard["hostnames"]]
    assert not any("simplyhired.com" in h for h in hostnames)

    # For completeness also assert that no outbound connects happened at all
    # in this code path (preview_demo should remain local-only here).
    assert not no_network_guard["connects"], (
        "Dry-run demo should not perform outbound socket connections"
    )

