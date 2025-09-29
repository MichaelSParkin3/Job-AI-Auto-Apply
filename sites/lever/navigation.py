from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from apps.browser import BrowserActionStatus, BrowserUseController

from .lever_google_discovery import LeverSerpResult


@dataclass(slots=True)
class LeverNavigationStep:
    """Diagnostic breadcrumb recorded while navigating to a Lever form."""

    action: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LeverNavigationOutcome:
    """Represents the result of attempting to land on a Lever apply form."""

    result: LeverSerpResult
    status: str
    landing_url: str | None
    html: str | None
    steps: list[LeverNavigationStep] = field(default_factory=list)
    apply_url: str | None = None
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "mode": self.result.mode,
            "result": {
                "title": self.result.title,
                "href": self.result.href,
                "isApply": self.result.is_apply,
            },
        }
        if self.apply_url:
            payload["applyUrl"] = self.apply_url
        if self.landing_url:
            payload["landingUrl"] = self.landing_url
        if self.error:
            payload["error"] = self.error
        if self.steps:
            payload["steps"] = [
                {"action": step.action, "details": dict(step.details)} for step in self.steps
            ]
        return payload


class LeverNavigator:
    """Navigate from Google SERP results to Lever apply forms."""

    def __init__(self, controller: BrowserUseController) -> None:
        self._controller = controller

    def open_result(
        self,
        result: LeverSerpResult,
        *,
        idle_timeout: float = 6.0,
    ) -> LeverNavigationOutcome:
        """Open the SERP result and attempt to reach the Lever apply form."""

        steps: list[LeverNavigationStep] = []
        open_result = self._controller.open_url(result.href)
        steps.append(
            LeverNavigationStep(
                action="open",
                details={"url": result.href, "status": open_result.status.value},
            )
        )
        if open_result.status is not BrowserActionStatus.OK:
            return LeverNavigationOutcome(
                result=result,
                status="open_failed",
                landing_url=None,
                html=None,
                steps=steps,
                error=str(open_result.details.get("error")),
            )

        self._controller.wait_for_idle(idle_timeout)
        html_result = self._controller.get_page_html()
        html = html_result.details.get("html") if html_result.status is BrowserActionStatus.OK else ""
        current_url = self._current_url()

        if result.is_apply and _contains_apply_form(html):
            return LeverNavigationOutcome(
                result=result,
                status="ok",
                landing_url=current_url,
                html=html,
                steps=steps,
                apply_url=current_url or result.href,
            )

        selector, apply_url = _resolve_apply_target(result.href, html)
        if not apply_url:
            return LeverNavigationOutcome(
                result=result,
                status="apply_link_missing",
                landing_url=current_url,
                html=html,
                steps=steps,
            )

        steps.append(
            LeverNavigationStep(
                action="resolve_apply",
                details={"selector": selector, "url": apply_url},
            )
        )

        navigation_error: str | None = None
        if selector:
            click_result = self._controller.safe_click(selector, timeout=10.0)
            steps.append(
                LeverNavigationStep(
                    action="click",
                    details={"selector": selector, "status": click_result.status.value},
                )
            )
            if click_result.status is not BrowserActionStatus.OK:
                navigation_error = str(click_result.details.get("error"))
        else:
            navigation_error = "no_selector"

        if navigation_error:
            apply_open = self._controller.open_url(apply_url)
            steps.append(
                LeverNavigationStep(
                    action="open_apply",
                    details={"url": apply_url, "status": apply_open.status.value},
                )
            )
            if apply_open.status is not BrowserActionStatus.OK:
                return LeverNavigationOutcome(
                    result=result,
                    status="apply_open_failed",
                    landing_url=self._current_url(),
                    html=None,
                    steps=steps,
                    apply_url=apply_url,
                    error=str(apply_open.details.get("error")),
                )

        self._controller.wait_for_idle(idle_timeout)
        final_html_result = self._controller.get_page_html()
        final_html = (
            final_html_result.details.get("html")
            if final_html_result.status is BrowserActionStatus.OK
            else html
        )
        final_url = self._current_url() or apply_url
        status = "ok" if _contains_apply_form(final_html) else "apply_form_missing"
        error = None
        if status != "ok":
            error = "apply_form_not_detected"
        return LeverNavigationOutcome(
            result=result,
            status=status,
            landing_url=final_url,
            html=final_html,
            steps=steps,
            apply_url=apply_url,
            error=error,
        )

    def _current_url(self) -> str | None:
        current = self._controller.get_current_url()
        if current.status is BrowserActionStatus.OK:
            return str(current.details.get("url")) if current.details.get("url") else None
        return None


_FORM_RE = re.compile(r"<form[^>]+id=['\"]application-form['\"]", re.IGNORECASE)
_SUBMIT_RE = re.compile(r"<button[^>]+id=['\"]btn-submit['\"][^>]+data-qa=['\"]btn-submit['\"]", re.IGNORECASE)


def _contains_apply_form(html: str | None) -> bool:
    if not html:
        return False
    if _FORM_RE.search(html):
        return True
    if _SUBMIT_RE.search(html):
        return True
    return False


_ANCHOR_RE = re.compile(
    r"<a[^>]+href=['\"](?P<href>[^'\"]+)['\"][^>]*>",
    re.IGNORECASE,
)
_BUTTON_URL_RE = re.compile(
    r"<button[^>]+data-url=['\"](?P<url>[^'\"]+)['\"][^>]*>",
    re.IGNORECASE,
)


def _resolve_apply_target(base_url: str, html: str) -> tuple[str | None, str | None]:
    if not html:
        return None, None
    for match in _ANCHOR_RE.finditer(html):
        href = match.group("href")
        if "/apply" not in href.lower():
            continue
        segment = match.group(0)
        selector = "a[href*='/apply']"
        if "postings-btn" in segment:
            selector = "a.postings-btn.template-btn-submit[href*='/apply']"
        resolved = _normalize_apply_url(base_url, href)
        if resolved:
            return selector, resolved
    for match in _BUTTON_URL_RE.finditer(html):
        href = match.group("url")
        if "/apply" not in href.lower():
            continue
        resolved = _normalize_apply_url(base_url, href)
        if resolved:
            return None, resolved
    return None, None


def _normalize_apply_url(base: str, href: str) -> str | None:
    parsed = urlparse(href)
    if parsed.scheme and parsed.netloc:
        return href
    if href.startswith("//"):
        base_parsed = urlparse(base)
        scheme = base_parsed.scheme or "https"
        return f"{scheme}:{href}"
    return urljoin(base, href)


__all__ = [
    "LeverNavigator",
    "LeverNavigationOutcome",
    "LeverNavigationStep",
]

