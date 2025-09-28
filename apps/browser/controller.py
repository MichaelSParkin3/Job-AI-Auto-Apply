"""Browser-Use controller thin wrapper with config merging and telemetry."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Protocol

from apps.cli.utils import log_event
from .guardrails import NavigationGuardrails

if TYPE_CHECKING:  # pragma: no cover - import for type hints only
    from browser_use.browser import BrowserSession


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


class BrowserSessionAdapter:
    """Adapts async BrowserSession API to legacy synchronous controller expectations."""

    def __init__(self, session: "BrowserSession") -> None:
        self._session = session
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="browser-use-session",
            daemon=True,
        )
        self._loop_thread.start()
        self._closed = False
        # Start the Browser-Use session on the background loop and wait for connection.
        self._run(self._session.start())
        # Wait until BrowserConnectedEvent fires or CDP/agent_focus are set.
        try:
            self._run(self._await_session_ready(timeout=45.0))
        except Exception:
            # Continue; downstream _ensure_focus_ready will raise a clearer error if still not ready
            pass

    # ------------------------------------------------------------------
    # Public API compatible with legacy controller
    # ------------------------------------------------------------------
    def open_url(self, url: str) -> Dict[str, Any]:
        return self._run(self._navigate(url))

    def wait_for_idle(self, timeout: float = 5.0) -> Dict[str, Any]:
        timeout = max(timeout, 0.0)
        result = self._run(self._wait_for_ready_state(timeout))
        return {"readyState": result}

    def safe_click(self, selector: str, timeout: float | None = None) -> Dict[str, Any]:
        result = self._run(self._click_selector(selector, timeout))
        return {"selector": selector, "result": result}

    def get_page_content(self) -> str:
        return self._run(self._get_outer_html())

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._run(self._session.stop())
        except Exception:  # pragma: no cover - best-effort shutdown
            pass
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=1)
            self._closed = True

    def __del__(self) -> None:  # pragma: no cover - destructor safety net
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers running on the background asyncio loop
    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coroutine: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    async def _ensure_focus_ready(self, deadline: float | None = None) -> None:
        if deadline is None:
            deadline = time.monotonic() + 60.0
        while self._session.agent_focus is None or self._session.cdp_url is None:
            if time.monotonic() >= deadline:
                raise RuntimeError("Browser session focus not ready")
            await asyncio.sleep(0.1)

    async def _await_session_ready(self, timeout: float = 45.0) -> None:
        """Await Browser-Use connection readiness by listening for events or polling state."""
        try:
            from browser_use.browser.events import BrowserConnectedEvent, AgentFocusChangedEvent
        except Exception:
            # Fallback to polling
            await self._ensure_focus_ready(time.monotonic() + timeout)
            return

        loop = asyncio.get_running_loop()
        fut = loop.create_future()

        async def on_connected(_event) -> None:
            if not fut.done():
                fut.set_result(True)

        async def on_focus(_event) -> None:
            if self._session.agent_focus is not None and not fut.done():
                fut.set_result(True)

        # Register lightweight one-time listeners
        self._session.event_bus.on(BrowserConnectedEvent, on_connected)
        self._session.event_bus.on(AgentFocusChangedEvent, on_focus)

        # Also race with simple polling in case events were emitted before listeners attached
        async def _poll():
            end = time.monotonic() + timeout
            while time.monotonic() < end and not fut.done():
                if self._session.cdp_url and self._session.agent_focus is not None:
                    if not fut.done():
                        fut.set_result(True)
                        break
                await asyncio.sleep(0.1)
            if not fut.done():
                fut.set_exception(TimeoutError("Timeout waiting for BrowserConnectedEvent"))

        await asyncio.wait_for(asyncio.gather(fut, _poll()), timeout=timeout)

    async def _navigate(self, url: str) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        from browser_use.browser.events import NavigateToUrlEvent

        # Primary path: event-driven navigation
        event = self._session.event_bus.dispatch(NavigateToUrlEvent(url=url, new_tab=False))
        await event
        await event.event_result(raise_if_any=True, raise_if_none=False)

        # Verify navigation actually pointed at the intended origin; if not, force CDP navigate.
        try:
            href = await self._evaluate_js("(() => window.location.href)()")
        except Exception:
            href = None
        if not isinstance(href, str) or href.strip() == "" or href.startswith("chrome://"):
            # Fallback: direct CDP navigate on the focused session
            cdp_session = await self._session.get_or_create_cdp_session()
            await cdp_session.cdp_client.send.Page.navigate(
                params={
                    "url": url,
                    "transitionType": "typed",
                },
                session_id=cdp_session.session_id,
            )
        return {"url": url}

    async def _wait_for_ready_state(self, timeout: float) -> str:
        await self._ensure_focus_ready()
        end = time.monotonic() + timeout
        last_state = "loading"
        while time.monotonic() <= end:
            try:
                state = await self._evaluate_js("(() => document.readyState)()")
                if isinstance(state, str):
                    last_state = state
                    if state.lower() == "complete":
                        return state
            except Exception:
                # Ignore transient evaluation issues during navigation
                pass
            await asyncio.sleep(0.25)
        return last_state

    async def _click_selector(self, selector: str, timeout: float | None) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        deadline = time.monotonic() + (timeout if timeout is not None else 5.0)
        last_error: Dict[str, Any] | None = None
        while True:
            expression = (
                "(() => {\n"
                f"  const selector = {json.dumps(selector)};\n"
                "  const element = document.querySelector(selector);\n"
                "  if (!element) { return { ok: false, reason: 'not_found' }; }\n"
                "  element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });\n"
                "  const rect = element.getBoundingClientRect();\n"
                "  try {\n"
                "    if (typeof element.click === 'function') { element.click(); }\n"
                "    else { element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); }\n"
                "    return { ok: true, rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }, tagName: element.tagName };\n"
                "  } catch (error) {\n"
                "    return { ok: false, reason: 'click_failed', message: String(error), tagName: element.tagName };\n"
                "  }\n"
                "})()"
            )
            try:
                result = await self._evaluate_js(expression)
            except Exception as exc:  # pragma: no cover - propagate evaluation issues
                last_error = {"ok": False, "reason": "evaluation_failed", "message": str(exc)}
                result = last_error
            if isinstance(result, dict) and result.get("ok"):
                return result
            last_error = result if isinstance(result, dict) else {"ok": False, "reason": "unknown", "result": result}
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Failed to click selector {selector}: {last_error}")
            await asyncio.sleep(0.25)

    async def _get_outer_html(self) -> str:
        await self._ensure_focus_ready()
        html = await self._evaluate_js("(() => document.documentElement.outerHTML)()")
        if not isinstance(html, str):
            raise RuntimeError("Browser session did not return HTML content")
        return html

    async def _evaluate_js(self, expression: str) -> Any:
        await self._ensure_focus_ready()
        cdp_session = await self._session.get_or_create_cdp_session()
        result = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=cdp_session.session_id,
        )
        return result.get("result", {}).get("value")


def create_browser_client(config: BrowserLaunchConfig) -> BrowserClient:
    """Instantiate a Browser-Use client using the official library."""

    try:
        from browser_use.browser import BrowserSession  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only when dependency missing
        raise BrowserLaunchError(
            "browser-use package is not installed. Install it to launch headful Chrome."
        ) from exc

    # Browser-Use 0.7+ expects window dimensions as dicts and locale/timezone via env/headers.
    window_size = {"width": config.viewport_width, "height": config.viewport_height}

    def _normalize_locale(value: str) -> str:
        normalized = value.replace("-", "_")
        return normalized if "." in normalized else f"{normalized}.UTF-8"

    env: Dict[str, str] = {}
    if config.timezone:
        env["TZ"] = config.timezone
    if config.locale:
        env_locale = _normalize_locale(config.locale)
        env.update({
            "LANG": env_locale,
            "LC_ALL": env_locale,
        })

    headers: Dict[str, str] = {}
    if config.locale:
        headers["Accept-Language"] = f"{config.locale},en;q=0.8"

    args = [f"--lang={config.locale}"] if config.locale else []

    session = BrowserSession(
        headless=False,
        user_data_dir=str(config.user_data_dir),
        executable_path=config.chrome_path,
        window_size=window_size,
        allowed_domains=list(config.guardrail_domains),
        keep_alive=config.keep_alive,
        enable_default_extensions=False,
        env=env or None,
        headers=headers or None,
        args=args or None,
    )
    return BrowserSessionAdapter(session)


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
