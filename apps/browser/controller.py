"""Browser-Use controller thin wrapper with config merging and telemetry."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
    Protocol,
    Sequence,
)

from apps.cli.utils import log_event
from apps.preview.constants import placeholder_screenshot_bytes
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


@dataclass(slots=True)
class ReviewArtifactCapture:
    """Represents the outcome of capturing a review screenshot."""

    screenshot_path: Path
    method: str
    html_path: Path | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": str(self.screenshot_path),
            "method": self.method,
        }
        if self.html_path is not None:
            payload["htmlPath"] = str(self.html_path)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def telemetry_payload(self) -> dict[str, Any]:
        payload = {"method": self.method}
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


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

    def focus(self, selector: str, timeout: float | None = None) -> Any:  # pragma: no cover
        """Set focus on the provided selector."""

    def fill_text(self, selector: str, value: str, *, clear: bool = True) -> Any:  # pragma: no cover
        """Assign text value to an input/textarea selector."""

    def set_select_value(self, selector: str, value: str) -> Any:  # pragma: no cover
        """Set a <select> element to the given value."""

    def set_radio_value(self, selector: str, value: str) -> Any:  # pragma: no cover
        """Mark the radio group containing selector as checked for the given value."""

    def set_checkbox_state(self, selector: str, checked: bool) -> Any:  # pragma: no cover
        """Toggle a checkbox input state."""

    def get_field_state(self, selector: str, widget_type: str) -> Any:  # pragma: no cover
        """Return the current value/checked state for validation."""

    def set_input_files(self, selector: str, paths: Sequence[str]) -> Any:  # pragma: no cover
        """Attach files to an <input type="file"> element."""

    def capture_review_screenshot(self, path: str) -> Any:  # pragma: no cover - optional
        """Optional helper provided by Browser-Use to capture review screenshots."""

    # Optional but recommended: provide current URL for post-click confirmation
    def get_current_url(self) -> str:  # pragma: no cover - runtime protocol
        """Return the current window.location.href if available."""

    # Optional: resolve the final URL after redirects without navigating the tab
    def resolve_redirect(self, url: str) -> str:  # pragma: no cover - runtime protocol
        """Return the final resolved URL for the given target if possible."""


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

    def focus(self, selector: str, timeout: float | None = None) -> Dict[str, Any]:
        result = self._run(self._focus_selector(selector, timeout))
        return {"selector": selector, "result": result}

    def fill_text(
        self, selector: str, value: str, *, clear: bool = True
    ) -> Dict[str, Any]:
        result = self._run(self._fill_text(selector, value, clear=clear))
        return {"selector": selector, "result": result}

    def set_select_value(self, selector: str, value: str) -> Dict[str, Any]:
        result = self._run(self._set_select_value(selector, value))
        return {"selector": selector, "result": result}

    def set_radio_value(self, selector: str, value: str) -> Dict[str, Any]:
        result = self._run(self._set_radio_value(selector, value))
        return {"selector": selector, "result": result}

    def set_checkbox_state(self, selector: str, checked: bool) -> Dict[str, Any]:
        result = self._run(self._set_checkbox_state(selector, checked))
        return {"selector": selector, "result": result}

    def get_field_state(self, selector: str, widget_type: str) -> Dict[str, Any]:
        result = self._run(self._get_field_state(selector, widget_type))
        return {"selector": selector, "result": result}

    def set_input_files(self, selector: str, paths: Sequence[str]) -> Dict[str, Any]:
        result = self._run(self._set_input_files(selector, paths))
        return {"selector": selector, "result": result}

    def capture_review_screenshot(self, path: str) -> Dict[str, Any]:
        output = Path(path)
        result = self._run(self._capture_review_screenshot(output))
        return result

    def get_current_url(self) -> str:
        """Return the current page URL via a lightweight JS evaluation.

        We intentionally avoid exposing the underlying Playwright page or
        event loop; this stays consistent with other adapter methods.
        """
        return str(self._run(self._evaluate_js("(() => window.location.href)()")))

    def resolve_redirect(self, url: str) -> str:
        """Resolve final URL for a target via in-page fetch following redirects."""
        expression = (
            "(() => {\n"
            f"  const u = {json.dumps(url)};\n"
            "  return fetch(u, { redirect: 'follow', method: 'GET', credentials: 'include' })\n"
            "    .then(r => r && r.url ? r.url : null)\n"
            "    .catch(() => null);\n"
            "})()"
        )
        return str(self._run(self._evaluate_js(expression)))

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

    async def _focus_selector(self, selector: str, timeout: float | None) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        deadline = time.monotonic() + (timeout if timeout is not None else 5.0)
        last_error: Dict[str, Any] | None = None
        while True:
            expression = (
                "(() => {\n"
                f"  const selector = {json.dumps(selector)};\n"
                "  const element = document.querySelector(selector);\n"
                "  if (!element) { return { ok: false, reason: 'not_found' }; }\n"
                "  try {\n"
                "    element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });\n"
                "    if (typeof element.focus === 'function') { element.focus({ preventScroll: true }); }\n"
                "    return { ok: true, tagName: element.tagName };\n"
                "  } catch (error) {\n"
                "    return { ok: false, reason: 'focus_failed', message: String(error) };\n"
                "  }\n"
                "})()"
            )
            try:
                result = await self._evaluate_js(expression)
            except Exception as exc:
                last_error = {"ok": False, "reason": "evaluation_failed", "message": str(exc)}
                result = last_error
            if isinstance(result, dict) and result.get("ok"):
                return result
            last_error = result if isinstance(result, dict) else {"ok": False, "reason": "unknown", "result": result}
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Failed to focus selector {selector}: {last_error}")
            await asyncio.sleep(0.25)

    async def _fill_text(self, selector: str, value: str, *, clear: bool) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        expression = (
            "(() => {\n"
            f"  const selector = {json.dumps(selector)};\n"
            f"  const text = {json.dumps(value)};\n"
            f"  const shouldClear = {json.dumps(clear)};\n"
            "  const element = document.querySelector(selector);\n"
            "  if (!element) { return { ok: false, reason: 'not_found' }; }\n"
            "  try {\n"
            "    element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });\n"
            "    if (typeof element.focus === 'function') { element.focus({ preventScroll: true }); }\n"
            "    if (shouldClear && 'value' in element) { element.value = ''; }\n"
            "    if ('value' in element) { element.value = text; }\n"
            "    else if ('textContent' in element) { element.textContent = text; }\n"
            "    element.dispatchEvent(new Event('input', { bubbles: true }));\n"
            "    element.dispatchEvent(new Event('change', { bubbles: true }));\n"
            "    return { ok: true, value: ('value' in element) ? element.value : text, tagName: element.tagName };\n"
            "  } catch (error) {\n"
            "    return { ok: false, reason: 'fill_failed', message: String(error) };\n"
            "  }\n"
            "})()"
        )
        return await self._evaluate_js(expression)

    async def _set_select_value(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        expression = (
            "(() => {\n"
            f"  const selector = {json.dumps(selector)};\n"
            f"  const desired = {json.dumps(value)};\n"
            "  const element = document.querySelector(selector);\n"
            "  if (!element || element.tagName !== 'SELECT') { return { ok: false, reason: 'not_found' }; }\n"
            "  const options = Array.from(element.options || []);\n"
            "  const normalize = (text) => (text || '').toString().trim().toLowerCase();\n"
            "  const target = options.find(option => normalize(option.value) === normalize(desired))\n"
            "    || options.find(option => normalize(option.textContent) === normalize(desired));\n"
            "  if (!target) {\n"
            "    return { ok: false, reason: 'option_missing', options: options.map(opt => opt.value) };\n"
            "  }\n"
            "  element.value = target.value;\n"
            "  element.dispatchEvent(new Event('input', { bubbles: true }));\n"
            "  element.dispatchEvent(new Event('change', { bubbles: true }));\n"
            "  return { ok: true, value: element.value, label: (target.textContent || '').trim() };\n"
            "})()"
        )
        return await self._evaluate_js(expression)

    async def _set_radio_value(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        expression = (
            "(() => {\n"
            f"  const selector = {json.dumps(selector)};\n"
            f"  const desired = {json.dumps(value)};\n"
            "  const normalize = (text) => (text || '').toString().trim().toLowerCase();\n"
            "  const element = document.querySelector(selector);\n"
            "  if (!element) { return { ok: false, reason: 'not_found' }; }\n"
            "  const name = element.getAttribute('name');\n"
            "  const candidates = name\n"
            "    ? Array.from(document.querySelectorAll(`input[type=\"radio\"][name=\"${name}\"]`))\n"
            "    : [element];\n"
            "  const target = candidates.find(opt => normalize(opt.value) === normalize(desired))\n"
            "    || candidates.find(opt => normalize(opt.getAttribute('aria-label')) === normalize(desired))\n"
            "    || candidates.find(opt => {\n"
            "         const label = opt.closest('label');\n"
            "         return label && normalize(label.textContent) === normalize(desired);\n"
            "       });\n"
            "  if (!target) { return { ok: false, reason: 'option_missing' }; }\n"
            "  candidates.forEach(opt => { opt.checked = opt === target; });\n"
            "  target.dispatchEvent(new Event('input', { bubbles: true }));\n"
            "  target.dispatchEvent(new Event('change', { bubbles: true }));\n"
            "  const label = target.getAttribute('aria-label')\n"
            "    || (target.closest('label') ? target.closest('label').textContent : '');\n"
            "  return { ok: true, value: target.value, label: (label || '').trim() };\n"
            "})()"
        )
        return await self._evaluate_js(expression)

    async def _set_checkbox_state(self, selector: str, checked: bool) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        expression = (
            "(() => {\n"
            f"  const selector = {json.dumps(selector)};\n"
            f"  const desired = {json.dumps(bool(checked))};\n"
            "  const element = document.querySelector(selector);\n"
            "  if (!element) { return { ok: false, reason: 'not_found' }; }\n"
            "  element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });\n"
            "  element.checked = desired;\n"
            "  element.dispatchEvent(new Event('input', { bubbles: true }));\n"
            "  element.dispatchEvent(new Event('change', { bubbles: true }));\n"
            "  return { ok: true, checked: Boolean(element.checked) };\n"
            "})()"
        )
        return await self._evaluate_js(expression)

    async def _get_field_state(self, selector: str, widget_type: str) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        expression = (
            "(() => {\n"
            f"  const selector = {json.dumps(selector)};\n"
            f"  const widget = {json.dumps(widget_type)}.toString().toLowerCase();\n"
            "  const element = document.querySelector(selector);\n"
            "  if (!element) { return { ok: false, reason: 'not_found' }; }\n"
            "  const normalize = (text) => (text || '').toString().trim();\n"
            "  if (widget === 'text' || widget === 'textarea') {\n"
            "    const value = normalize('value' in element ? element.value : element.textContent);\n"
            "    return { ok: true, value, empty: value.length === 0 };\n"
            "  }\n"
            "  if (widget === 'select') {\n"
            "    const value = normalize(element.value);\n"
            "    const selected = element.options && element.options[element.selectedIndex];\n"
            "    const label = selected ? normalize(selected.textContent) : '';\n"
            "    return { ok: true, value, label, empty: value.length === 0 };\n"
            "  }\n"
            "  if (widget === 'radio') {\n"
            "    const name = element.getAttribute('name');\n"
            "    const candidates = name\n"
            "      ? Array.from(document.querySelectorAll(`input[type=\"radio\"][name=\"${name}\"]`))\n"
            "      : [element];\n"
            "    const checked = candidates.find(opt => opt.checked);\n"
            "    const label = checked\n"
            "      ? (checked.getAttribute('aria-label')\n"
            "        || (checked.closest('label') ? checked.closest('label').textContent : ''))\n"
            "      : '';\n"
            "    return { ok: true, value: checked ? normalize(checked.value) : '', label: normalize(label), checked: Boolean(checked) };\n"
            "  }\n"
            "  if (widget === 'checkbox') {\n"
            "    return { ok: true, checked: Boolean(element.checked) };\n"
            "  }\n"
            "  if (widget === 'file') {\n"
            "    const files = Array.from(element.files || []).map(file => ({\n"
            "      name: file.name,\n"
            "      size: typeof file.size === 'number' ? file.size : null,\n"
            "      type: file.type || null\n"
            "    }));\n"
            "    return { ok: true, files, count: files.length };\n"
            "  }\n"
            "  return { ok: false, reason: 'unsupported_widget' };\n"
            "})()"
        )
        return await self._evaluate_js(expression)

    async def _set_input_files(self, selector: str, paths: Sequence[str]) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        normalized = [str(Path(path)) for path in paths]
        cdp_session = await self._session.get_or_create_cdp_session()
        cdp_client = cdp_session.cdp_client
        session_id = cdp_session.session_id
        await cdp_client.send.DOM.enable(session_id=session_id)
        check_expression = (
            "(() => {\n"
            f"  const selector = {json.dumps(selector)};\n"
            "  const element = document.querySelector(selector);\n"
            "  if (!element) { return { ok: false, reason: 'not_found' }; }\n"
            "  const tagName = element.tagName ? element.tagName.toLowerCase() : '';\n"
            "  const type = (element.getAttribute('type') || '').toLowerCase();\n"
            "  const isFileInput = tagName === 'input' && type === 'file';\n"
            "  const reason = isFileInput ? null : `not_file_input:${tagName || 'unknown'}/${type || 'unknown'}`;\n"
            "  return { ok: isFileInput, tagName, type, reason };\n"
            "})()"
        )
        metadata = await self._evaluate_js(check_expression)
        if not isinstance(metadata, Mapping):
            raise RuntimeError("Unable to inspect file input selector")
        if not metadata.get("ok"):
            raise RuntimeError(f"File input selector failed: {metadata.get('reason', 'not_file_input')}")
        evaluation = await cdp_client.send.Runtime.evaluate(
            params={
                "expression": f"(() => document.querySelector({json.dumps(selector)}))()",
                "objectGroup": "file-upload",
                "includeCommandLineAPI": True,
                "returnByValue": False,
            },
            session_id=session_id,
        )
        remote = evaluation.get("result", {})
        if remote.get("subtype") == "null":
            raise RuntimeError("File input element not found during upload")
        object_id = remote.get("objectId")
        if not object_id:
            raise RuntimeError("Unable to resolve DOM object for file input")
        try:
            await cdp_client.send.DOM.setFileInputFiles(
                params={
                    "files": normalized,
                    "objectId": object_id,
                },
                session_id=session_id,
            )
        finally:
            try:
                await cdp_client.send.Runtime.releaseObjectGroup(  # type: ignore[attr-defined]
                    params={"objectGroup": "file-upload"},
                    session_id=session_id,
                )
            except Exception:
                pass
        files = [
            {
                "name": Path(path).name,
                "path": str(Path(path)),
            }
            for path in normalized
        ]
        return {"ok": True, "files": files}

    async def _capture_review_screenshot(self, output_path: Path) -> Dict[str, Any]:
        await self._ensure_focus_ready()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cdp_session = await self._session.get_or_create_cdp_session()
        screenshot = await cdp_session.cdp_client.send.Page.captureScreenshot(
            params={
                "format": "png",
                "captureBeyondViewport": False,
            },
            session_id=cdp_session.session_id,
        )
        data = screenshot.get("data")
        if not isinstance(data, str) or not data:
            raise RuntimeError("captureScreenshot returned no data")
        output_path.write_bytes(base64.b64decode(data))
        return {
            "path": str(output_path),
            "method": "cdp",
            "captureBeyondViewport": False,
        }

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

    # Lightweight helpers to validate current domain around actions without
    # incurring extra pacing. These avoid the full get_current_url telemetry
    # to keep action logs clean while still surfacing guardrail events.
    def _resolve_current_url(self) -> str | None:
        try:
            client = self._ensure_client()
        except Exception:  # pragma: no cover - defensive
            return None
        try:
            get_url = getattr(client, "get_current_url", None)
            if callable(get_url):
                value = get_url()
                if value:
                    return str(value)
            page = getattr(client, "page", None)
            if page is not None:
                value = getattr(page, "url", None)
                if callable(value):
                    return str(value())
                if value is not None:
                    return str(value)
        except Exception:  # pragma: no cover - best-effort
            return None
        return None

    def _guard_current_domain(self, payload: Dict[str, Any], *, reason: str):
        url = self._resolve_current_url()
        if not url:
            return None
        return self._guardrails.check_current_domain(url, payload, reason=reason)

    @staticmethod
    def _extract_client_result(result: Any) -> Any:
        if isinstance(result, Mapping) and "result" in result:
            return result["result"]
        return result

    @staticmethod
    def _sanitize_widget_result(result: Any, *, original: str | None = None) -> Dict[str, Any]:
        data = BrowserUseController._extract_client_result(result)
        if isinstance(data, Mapping):
            sanitized: Dict[str, Any] = {}
            for key, value in data.items():
                if key == "value":
                    sanitized["valueLength"] = len(str(value))
                elif key == "options":
                    if isinstance(value, Sequence):
                        sanitized["optionsCount"] = len(value)
                    else:
                        sanitized["options"] = value
                elif key == "files":
                    if isinstance(value, Sequence):
                        sanitized["fileCount"] = len(value)
                        sanitized["files"] = [
                            {
                                "name": str(item.get("name")) if isinstance(item, Mapping) else str(item),
                                "size": item.get("size") if isinstance(item, Mapping) else None,
                            }
                            for item in value
                        ]
                    else:
                        sanitized["files"] = value
                else:
                    sanitized[key] = value
            if original is not None:
                sanitized.setdefault("valueLength", len(original))
            return sanitized
        return {"ok": bool(data)}

    @staticmethod
    def _describe_file(path: Path) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "name": path.name,
            "exists": path.exists(),
        }
        try:
            info["sizeBytes"] = path.stat().st_size
        except OSError:
            info["sizeBytes"] = None
        if info["exists"]:
            digest = hashlib.sha256()
            try:
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(8192), b""):
                        digest.update(chunk)
            except OSError:
                info["sha256"] = None
            else:
                info["sha256"] = digest.hexdigest()
        else:
            info["sha256"] = None
        return info

    @staticmethod
    def _sanitize_capture_result(result: Any) -> Dict[str, Any]:
        if isinstance(result, Mapping):
            sanitized: Dict[str, Any] = {}
            for key, value in result.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    sanitized[key] = value
                elif isinstance(value, Mapping):
                    sanitized[key] = {
                        k: v
                        for k, v in value.items()
                        if isinstance(v, (str, int, float, bool)) or v is None
                    }
            return sanitized
        return {}

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

    def capture_element_screenshot(
        self, selector: str, output_path: Path
    ) -> BrowserActionResult:
        """Capture a focused screenshot for the provided selector."""

        client = self._ensure_client()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = self._base_payload() | {
            "selector": selector,
            "path": str(output),
        }
        metadata: Dict[str, Any] = {}
        method = "browser-use"
        try:
            capture_fn = getattr(client, "capture_element_screenshot", None)
            if callable(capture_fn):
                result = capture_fn(selector=selector, path=str(output))
                metadata = self._sanitize_capture_result(result)
                method = metadata.pop("method", method) or method
            else:
                page = getattr(client, "page", None)
                if page is None:
                    raise AttributeError("capture_element_missing")
                locator_factory = getattr(page, "locator", None)
                if callable(locator_factory):
                    locator = locator_factory(selector)
                    screenshot_fn = getattr(locator, "screenshot", None)
                    if not callable(screenshot_fn):
                        raise AttributeError("locator_screenshot_missing")
                    screenshot_fn(path=str(output))
                    method = "playwright.locator"
                elif hasattr(page, "screenshot"):
                    screenshot_fn = getattr(page, "screenshot")
                    screenshot_fn(path=str(output), full_page=False)
                    method = "playwright.page"
                else:
                    raise AttributeError("page_screenshot_missing")
        except Exception as exc:  # pragma: no cover - defensive
            event = payload | {
                "event": "browser.capture_element.failed",
                "error": str(exc),
            }
            log_event(event | {"level": "error"})
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=event,
            )

        if not output.exists() or output.stat().st_size == 0:
            event = payload | {
                "event": "browser.capture_element.empty",
                "error": "screenshot_empty",
            }
            log_event(event | {"level": "error"})
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": "screenshot_empty"},
                telemetry=event,
            )

        telemetry = payload | {
            "event": "browser.capture_element.completed",
            "method": method,
        }
        if metadata:
            telemetry["metadata"] = metadata
        log_event(telemetry)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"path": str(output), "method": method},
            telemetry=telemetry,
        )

    def get_current_url(self) -> BrowserActionResult:
        """Return the current page URL using client shims (no event-loop dependency)."""

        client = self._ensure_client()
        payload = self._base_payload() | {"event": "browser.url"}
        try:
            url: str | None = None
            # Prefer an explicit client method if available
            get_url = getattr(client, "get_current_url", None)
            if callable(get_url):
                url = str(get_url())
            else:
                page = getattr(client, "page", None)
                if page is not None:
                    # Playwright exposes page.url (property) or page.url() (callable in some wrappers)
                    value = getattr(page, "url", None)
                    url = str(value() if callable(value) else value) if value is not None else None
            if not url:
                raise AttributeError("url_unavailable")
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "warning",
                    "event": "browser.url.failed",
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
            details={"url": url},
            telemetry=payload | {"url": url},
        )

    def resolve_redirect(self, url: str) -> BrowserActionResult:
        """Resolve the final URL after following redirects using in-page fetch.

        Useful for safely preflighting off-platform redirectors (e.g., /out links)
        without navigating the tab. Returns the resolved absolute URL string.
        """

        client = self._ensure_client()
        payload = self._base_payload() | {"event": "browser.resolve_redirect", "target": url}
        try:
            resolver = getattr(client, "resolve_redirect", None)
            final_url = resolver(url) if callable(resolver) else None
            if not isinstance(final_url, str) or not final_url:
                raise RuntimeError("resolve_failed")
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "warning",
                    "event": "browser.resolve_redirect.failed",
                    "sessionId": self.session_id,
                    "error": str(exc),
                    "target": url,
                }
            )
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=payload,
            )
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"url": final_url},
            telemetry=payload | {"resolvedUrl": final_url},
        )

    def upload_file(
        self,
        selector: str,
        file_path: Path,
        *,
        dry_run: bool = False,
        timeout: float | None = None,
        think_time: bool = True,
    ) -> BrowserActionResult:
        """Deterministically attach a file to an input element."""

        client = self._ensure_client()
        resolved = file_path.resolve()
        file_info = self._describe_file(resolved)
        payload = self._base_payload() | {
            "selector": selector,
            "timeout": timeout,
            "file": file_info,
            "dryRun": dry_run,
        }
        pre_decision = self._guard_current_domain(payload, reason="pre_upload")
        if pre_decision is not None and not pre_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": pre_decision.reason or "blocked_domain",
                    "message": "Action blocked by domain guardrails.",
                    "url": pre_decision.event.get("url"),
                },
                telemetry=pre_decision.telemetry,
            )
        if think_time:
            self._guardrails.think_time(payload, reason="pre_upload")
        start = time.monotonic()
        log_event(payload | {"event": "UPLOAD_STARTED"})
        if dry_run:
            telemetry = payload | {
                "event": "UPLOAD_COMPLETED",
                "simulated": True,
                "durationSeconds": 0.0,
            }
            log_event(telemetry)
            return BrowserActionResult(
                status=BrowserActionStatus.OK,
                details={"response": {"simulated": True, "file": file_info}},
                telemetry=telemetry,
            )
        try:
            result = client.set_input_files(selector, [str(resolved)])
        except Exception as exc:  # pragma: no cover - defensive
            failure_event = payload | {
                "event": "UPLOAD_FAILED",
                "error": str(exc),
            }
            log_event(failure_event | {"level": "error"})
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=failure_event,
            )

        duration = round(time.monotonic() - start, 3)
        telemetry = payload | {
            "event": "UPLOAD_COMPLETED",
            "durationSeconds": duration,
        }
        log_event(telemetry)
        sanitized = self._sanitize_widget_result(result)
        sanitized.setdefault("durationSeconds", duration)
        sanitized.setdefault("file", file_info)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": sanitized},
            telemetry=telemetry,
        )

    def capture_review_artifacts(
        self,
        *,
        output_path: Path,
        summary_html: str | None = None,
    ) -> ReviewArtifactCapture:
        """Capture a stable review screenshot with a synthetic fallback."""

        client = self._ensure_client()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata: Dict[str, Any] = {}
        html_path: Path | None = None
        try:
            capture_fn = getattr(client, "capture_review_screenshot", None)
            if callable(capture_fn):
                result = capture_fn(str(output_path))
                metadata = self._sanitize_capture_result(result)
                method = metadata.pop("method", "browser-use") or "browser-use"
            elif hasattr(client, "page") and hasattr(client.page, "screenshot"):
                screenshot_fn = getattr(client.page, "screenshot")
                screenshot_fn(path=str(output_path), full_page=False)
                method = "playwright"
            else:
                raise AttributeError("capture_api_missing")
        except Exception as exc:
            method = "synthetic"
            html_path = output_path.with_suffix(".html")
            fallback_html = summary_html or (
                "<html><body><h1>Preview unavailable</h1><p>"
                "Unable to capture review screen; synthetic summary rendered."
                "</p></body></html>"
            )
            html_path.write_text(fallback_html, encoding="utf-8")
            output_path.write_bytes(placeholder_screenshot_bytes())
            metadata = {"error": str(exc)}
            log_event(
                {
                    "level": "warning",
                    "event": "review.capture.synthetic",
                    "sessionId": self.session_id,
                    "profileId": self.config.profile_id,
                    "path": str(output_path),
                    "htmlPath": str(html_path),
                    "error": str(exc),
                }
            )
            return ReviewArtifactCapture(
                screenshot_path=output_path,
                method=method,
                html_path=html_path,
                metadata=metadata,
            )

        if not output_path.exists():
            output_path.write_bytes(placeholder_screenshot_bytes())

        log_event(
            {
                "event": "review.capture.completed",
                "sessionId": self.session_id,
                "profileId": self.config.profile_id,
                "path": str(output_path),
                "method": method,
            }
        )
        return ReviewArtifactCapture(
            screenshot_path=output_path,
            method=method,
            metadata=metadata,
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
        # Pre-action domain validation (in case a prior step navigated away)
        pre_decision = self._guard_current_domain(payload, reason="pre_click")
        if pre_decision is not None and not pre_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": pre_decision.reason or "blocked_domain",
                    "message": "Action blocked by domain guardrails.",
                    "url": pre_decision.event.get("url"),
                },
                telemetry=pre_decision.telemetry,
            )
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
        # Post-action domain validation (ensure click didn't navigate off-domain)
        post_decision = self._guard_current_domain(payload, reason="post_click")
        if post_decision is not None and not post_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": post_decision.reason or "blocked_domain",
                    "message": "Navigation after click blocked by domain guardrails.",
                    "url": post_decision.event.get("url"),
                },
                telemetry=post_decision.telemetry,
            )
        telemetry = payload | {"event": "browser.safe_click.ok"}
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": result},
            telemetry=telemetry,
        )

    def focus(
        self,
        selector: str,
        *,
        timeout: float | None = None,
        think_time: bool = False,
    ) -> BrowserActionResult:
        """Focus the given selector using Browser-Use primitives."""

        client = self._ensure_client()
        payload = self._base_payload() | {"selector": selector, "timeout": timeout}
        pre_decision = self._guard_current_domain(payload, reason="pre_focus")
        if pre_decision is not None and not pre_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": pre_decision.reason or "blocked_domain",
                    "message": "Action blocked by domain guardrails.",
                    "url": pre_decision.event.get("url"),
                },
                telemetry=pre_decision.telemetry,
            )
        if think_time:
            self._guardrails.think_time(payload, reason="pre_focus")
        try:
            result = client.focus(selector, timeout)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.focus.failed",
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
        telemetry = payload | {"event": "browser.focus.ok"}
        sanitized = self._sanitize_widget_result(result)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": sanitized},
            telemetry=telemetry,
        )

    def fill_text(
        self,
        selector: str,
        value: str,
        *,
        clear: bool = True,
        think_time: bool = True,
    ) -> BrowserActionResult:
        """Fill a text input or textarea with the provided value."""

        client = self._ensure_client()
        payload = self._base_payload() | {
            "selector": selector,
            "clear": clear,
        }
        pre_decision = self._guard_current_domain(payload, reason="pre_fill")
        if pre_decision is not None and not pre_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": pre_decision.reason or "blocked_domain",
                    "message": "Action blocked by domain guardrails.",
                    "url": pre_decision.event.get("url"),
                },
                telemetry=pre_decision.telemetry,
            )
        if think_time:
            self._guardrails.think_time(payload, reason="pre_fill")
        try:
            result = client.fill_text(selector, value, clear=clear)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.fill_text.failed",
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
        telemetry = payload | {"event": "browser.fill_text.ok"}
        sanitized = self._sanitize_widget_result(result, original=value)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": sanitized},
            telemetry=telemetry,
        )

    def set_select_value(
        self,
        selector: str,
        value: str,
        *,
        think_time: bool = True,
    ) -> BrowserActionResult:
        """Set the value of a <select> element."""

        client = self._ensure_client()
        payload = self._base_payload() | {"selector": selector}
        pre_decision = self._guard_current_domain(payload, reason="pre_select")
        if pre_decision is not None and not pre_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": pre_decision.reason or "blocked_domain",
                    "message": "Action blocked by domain guardrails.",
                    "url": pre_decision.event.get("url"),
                },
                telemetry=pre_decision.telemetry,
            )
        if think_time:
            self._guardrails.think_time(payload, reason="pre_select")
        try:
            result = client.set_select_value(selector, value)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.select.failed",
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
        telemetry = payload | {"event": "browser.select.ok"}
        sanitized = self._sanitize_widget_result(result, original=value)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": sanitized},
            telemetry=telemetry,
        )

    def set_radio_value(
        self,
        selector: str,
        value: str,
        *,
        think_time: bool = True,
    ) -> BrowserActionResult:
        """Select a radio option in the group containing selector."""

        client = self._ensure_client()
        payload = self._base_payload() | {"selector": selector}
        pre_decision = self._guard_current_domain(payload, reason="pre_radio")
        if pre_decision is not None and not pre_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": pre_decision.reason or "blocked_domain",
                    "message": "Action blocked by domain guardrails.",
                    "url": pre_decision.event.get("url"),
                },
                telemetry=pre_decision.telemetry,
            )
        if think_time:
            self._guardrails.think_time(payload, reason="pre_radio")
        try:
            result = client.set_radio_value(selector, value)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.radio.failed",
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
        telemetry = payload | {"event": "browser.radio.ok"}
        sanitized = self._sanitize_widget_result(result, original=value)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": sanitized},
            telemetry=telemetry,
        )

    def set_checkbox_state(
        self,
        selector: str,
        checked: bool,
        *,
        think_time: bool = True,
    ) -> BrowserActionResult:
        """Toggle a checkbox state deterministically."""

        client = self._ensure_client()
        payload = self._base_payload() | {"selector": selector, "checked": checked}
        pre_decision = self._guard_current_domain(payload, reason="pre_checkbox")
        if pre_decision is not None and not pre_decision.allowed:
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={
                    "error": pre_decision.reason or "blocked_domain",
                    "message": "Action blocked by domain guardrails.",
                    "url": pre_decision.event.get("url"),
                },
                telemetry=pre_decision.telemetry,
            )
        if think_time:
            self._guardrails.think_time(payload, reason="pre_checkbox")
        try:
            result = client.set_checkbox_state(selector, checked)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.checkbox.failed",
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
        telemetry = payload | {"event": "browser.checkbox.ok"}
        sanitized = self._sanitize_widget_result(result)
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details={"response": sanitized},
            telemetry=telemetry,
        )

    def get_field_state(
        self,
        selector: str,
        widget_type: str,
    ) -> BrowserActionResult:
        """Inspect current DOM state for validation diagnostics."""

        client = self._ensure_client()
        payload = self._base_payload() | {
            "selector": selector,
            "widgetType": widget_type,
        }
        try:
            result = client.get_field_state(selector, widget_type)
        except Exception as exc:  # pragma: no cover - defensive
            log_event(
                {
                    "level": "error",
                    "event": "browser.field_state.failed",
                    "sessionId": self.session_id,
                    "selector": selector,
                    "widgetType": widget_type,
                    "error": str(exc),
                }
            )
            return BrowserActionResult(
                status=BrowserActionStatus.ERROR,
                details={"error": str(exc)},
                telemetry=payload,
            )
        state = self._extract_client_result(result)
        if isinstance(state, Mapping):
            details: Dict[str, Any] = {"state": dict(state)}
        else:
            details = {"state": state}
        telemetry = payload | {"event": "browser.field_state.ok"}
        return BrowserActionResult(
            status=BrowserActionStatus.OK,
            details=details,
            telemetry=telemetry,
        )
