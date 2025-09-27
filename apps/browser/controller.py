"""Browser-Use controller thin wrapper with config merging and telemetry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from apps.cli.utils import log_event
from .guardrails import NavigationGuardrails


class BrowserUseError(RuntimeError):
    """Base error raised for Browser-Use wrapper issues."""


class BrowserLaunchError(BrowserUseError):
    """Raised when the Browser-Use client cannot be created."""


class BrowserActionStatus(str, Enum):
    """Enumeration of wrapper action outcomes."""

    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class BrowserLaunchConfig:
    """Configuration required to bootstrap a Browser-Use session."""

    profile_id: str
    user_data_dir: Path
    model: str
    viewport_width: int
    viewport_height: int
    locale: str
    timezone: str
    chrome_path: Optional[str] = None
    keep_alive: bool = True
    guardrail_domains: tuple[str, ...] = ("*.simplyhired.com",)
    wait_jitter_ms: tuple[int, int] = (100, 600)
    think_time_range_s: tuple[float, float] = (1.0, 2.0)
    profile_metadata: Optional[Dict[str, Any]] = None
    profile_binding: Optional[Dict[str, Any]] = None


@dataclass
class BrowserActionResult:
    """Result payload returned by wrapper primitives."""

    status: BrowserActionStatus
    details: Dict[str, Any]
    telemetry: Dict[str, Any]


class BrowserClient(Protocol):
    """Protocol representing the Browser-Use client we interact with."""

    def open_url(self, url: str) -> Any:  # pragma: no cover - runtime protocol
        """Open a URL in the active tab, returning implementation specific data."""

    def wait_for_idle(self, timeout: float = 5.0) -> Any:  # pragma: no cover - runtime protocol
        """Block until Browser-Use reports idleness or timeout."""

    def safe_click(self, selector: str, timeout: float | None = None) -> Any:  # pragma: no cover
        """Click a selector while keeping guardrails enforced."""

    def get_page_content(self) -> str:  # pragma: no cover - runtime protocol
        """Return the current page HTML content."""


ClientFactory = Callable[[BrowserLaunchConfig], BrowserClient]


def create_browser_client(config: BrowserLaunchConfig) -> BrowserClient:
    """Instantiate a Browser-Use client using the official library."""

    try:
        from browser_use.browser import BrowserSession  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only when dependency missing
        raise BrowserLaunchError(
            "browser-use package is not installed. Install it to launch headful Chrome."
        ) from exc

    session = BrowserSession(
        headless=False,
        user_data_dir=str(config.user_data_dir),
        executable_path=config.chrome_path,
        window_size=(config.viewport_width, config.viewport_height),
        locale=config.locale,
        timezone_id=config.timezone,
        keep_profile_dir=True,
    )
    return session


class BrowserUseController:
    """High-level wrapper providing typed primitives for Browser-Use."""

    def __init__(
        self,
        config: BrowserLaunchConfig,
        *,
        client_factory: ClientFactory | None = None,
        guardrails: NavigationGuardrails | None = None,
    ) -> None:
        self.config = config
        self._client_factory = client_factory or create_browser_client
        self._client: BrowserClient | None = None
        self.session_id = uuid.uuid4().hex
        self.profile_binding = config.profile_binding
        self._guardrails = guardrails or NavigationGuardrails(
            allowed_domains=config.guardrail_domains,
            wait_jitter_ms=config.wait_jitter_ms,
            think_time_range_s=config.think_time_range_s,
            event_logger=log_event,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _ensure_client(self) -> BrowserClient:
        if self._client is None:
            try:
                self._client = self._client_factory(self.config)
            except BrowserUseError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise BrowserLaunchError(str(exc)) from exc
        return self._client

    def _base_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "sessionId": self.session_id,
            "profileId": self.config.profile_id,
            "userDataDir": str(self.config.user_data_dir),
            "model": self.config.model,
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "locale": self.config.locale,
            "timezone": self.config.timezone,
            "guardrails": {
                "allowedDomains": list(self.config.guardrail_domains),
            },
            "pacing": {
                "waitJitterMs": list(self.config.wait_jitter_ms),
                "thinkTimeRangeS": list(self.config.think_time_range_s),
            },
        }
        if self.config.profile_metadata:
            payload["profile"] = dict(self.config.profile_metadata)
        return payload

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def open_url(self, url: str, *, allow_new_tab: bool = False) -> BrowserActionResult:
        """Open the provided URL and return telemetry for downstream orchestration."""

        client = self._ensure_client()
        payload = self._base_payload() | {"url": url}
        if allow_new_tab:
            decision = self._guardrails.block_new_tab(payload, reason="open_url")
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": "new_tab_blocked",
                    "message": "New tab attempts are blocked by guardrails.",
                },
                telemetry=decision.telemetry,
            )

        decision = self._guardrails.before_navigation(url, payload)
        if not decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": decision.reason or "blocked_domain",
                    "message": "Navigation blocked by domain guardrails.",
                    "url": url,
                },
                telemetry=decision.telemetry,
            )
        try:
            result = client.open_url(url)
        except Exception as exc:  # pragma: no cover - error branch covered separately
            log_event(
                {
                    "level": "error",
                    "event": "browser.open.failed",
                    "message": "Browser-Use failed to open URL.",
                    "sessionId": self.session_id,
                    "url": url,
                    "error": str(exc),
                }
            )
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=payload,
            )

        telemetry = payload | {"event": "browser.open.ok"}
        log_event(
            {
                "event": "browser.session.opened",
                "sessionId": self.session_id,
                "url": url,
                "profileId": self.config.profile_id,
                "keepAlive": self.config.keep_alive,
            }
        )
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": result},
            telemetry=telemetry | {"guardrailEvent": decision.event},
        )

    def wait_for_idle(self, timeout: float = 5.0) -> BrowserActionResult:
        """Wait until Browser-Use considers the browser idle."""

        client = self._ensure_client()
        payload = self._base_payload() | {"timeout": timeout}
        try:
            result = client.wait_for_idle(timeout)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.wait_idle.failed",
                    "sessionId": self.session_id,
                    "timeout": timeout,
                    "error": str(exc),
                }
            )
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=payload,
            )
        telemetry = payload | {"event": "browser.wait_idle.ok"}
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": result},
            telemetry=telemetry,
        )

    def get_page_html(self) -> BrowserActionResult:
        """Capture the current page HTML for diagnostics."""

        client = self._ensure_client()
        payload = self._base_payload() | {"event": "browser.page_content"}
        try:
            html = self._extract_page_html(client)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.page_content.failed",
                    "sessionId": self.session_id,
                    "error": str(exc),
                }
            )
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=payload,
            )
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"html": html},
            telemetry=payload,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_page_html(client: BrowserClient) -> str:
        """Return HTML using the most common Browser-Use client shims."""

        if hasattr(client, "get_page_content") and callable(client.get_page_content):
            return client.get_page_content()
        if hasattr(client, "page_content"):
            page_content = getattr(client, "page_content")
            if callable(page_content):
                return page_content()
        page = getattr(client, "page", None)
        if page is not None and hasattr(page, "content"):
            content_fn = getattr(page, "content")
            if callable(content_fn):
                return content_fn()
        raise BrowserUseError("Browser client does not expose a page content API")

    def safe_click(
        self,
        selector: str,
        timeout: float | None = None,
        *,
        think_time: bool = False,
    ) -> BrowserActionResult:
        """Perform a guarded click using Browser-Use primitives."""

        client = self._ensure_client()
        payload = self._base_payload() | {"selector": selector, "timeout": timeout}
        if think_time:
            self._guardrails.think_time(payload, reason="pre_click")
        try:
            result = client.safe_click(selector, timeout)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.safe_click.failed",
                    "sessionId": self.session_id,
                    "selector": selector,
                    "error": str(exc),
                }
            )
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=payload,
            )
        telemetry = payload | {"event": "browser.safe_click.ok"}
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": result},
            telemetry=telemetry,
        )
