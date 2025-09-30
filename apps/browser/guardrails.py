"""Navigation guardrail utilities for the Browser-Use controller."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Sequence
from urllib.parse import urlparse


@dataclass(slots=True)
class GuardrailDecision:
    """Represents the outcome of evaluating a guardrail condition."""

    allowed: bool
    event: Dict[str, Any]
    telemetry: Dict[str, Any]
    wait_seconds: float = 0.0
    reason: str | None = None


class NavigationGuardrails:
    """Encapsulates domain allowlisting, tab suppression, and pacing."""

    def __init__(
        self,
        *,
        allowed_domains: Sequence[str],
        wait_jitter_ms: Sequence[int],
        think_time_range_s: Sequence[float],
        event_logger,
        sleep: Callable[[float], Any] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._allowed_domains = tuple(self._normalize_pattern(p) for p in allowed_domains if p)
        if len(wait_jitter_ms) != 2:
            raise ValueError("wait_jitter_ms must contain [min, max] values")
        if len(think_time_range_s) != 2:
            raise ValueError("think_time_range_s must contain [min, max] values")
        self._wait_range = (int(wait_jitter_ms[0]), int(wait_jitter_ms[1]))
        if self._wait_range[0] < 0 or self._wait_range[1] < self._wait_range[0]:
            raise ValueError("wait_jitter_ms range is invalid")
        self._think_range = (float(think_time_range_s[0]), float(think_time_range_s[1]))
        if self._think_range[0] < 0 or self._think_range[1] < self._think_range[0]:
            raise ValueError("think_time_range_s range is invalid")
        self._log_event = event_logger
        self._sleep = sleep or time.sleep
        self._rng = rng or random.Random()
        self._tab_count = 1
        self._blocked_tab_attempts = 0

    # ------------------------------------------------------------------
    # Domain helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_pattern(pattern: str) -> str:
        token = pattern.strip()
        wildcard = token.startswith("*.")
        if wildcard:
            token = token[2:]
        parsed = urlparse(token if "://" in token else f"https://{token}")
        host = parsed.hostname or token
        host = host.lower().lstrip(".")
        if wildcard:
            return f"*.{host}"
        return host

    def _hostname_matches(self, hostname: str, pattern: str) -> bool:
        host = hostname.lower()
        if pattern.startswith("*."):
            suffix = pattern[2:]
            return host == suffix or host.endswith(f".{suffix}")
        return host == pattern

    def _is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return False
        return any(self._hostname_matches(host, pattern) for pattern in self._allowed_domains)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def before_navigation(self, url: str, payload: Dict[str, Any]) -> GuardrailDecision:
        """Validate navigation guardrails and emit pacing events."""

        event_payload = payload | {
            "guardrails": {
                "allowedDomains": list(self._allowed_domains),
                "tabCount": self._tab_count,
                "blockedTabAttempts": self._blocked_tab_attempts,
            }
        }
        if not self._is_allowed(url):
            event = event_payload | {
                "event": "guardrail.browser.BLOCKED_DOMAIN",
                "url": url,
                "reason": "blocked_domain",
            }
            self._log_event(event)
            return GuardrailDecision(
                allowed=False,
                event=event,
                telemetry=event_payload | {"guardrailEvent": event},
                reason="blocked_domain",
            )

        wait_ms = 0.0
        if self._wait_range[1] > 0:
            wait_ms = self._rng.uniform(self._wait_range[0], self._wait_range[1])
            self._sleep(wait_ms / 1000.0)
        event = event_payload | {
            "event": "guardrail.browser.NAVIGATE",
            "url": url,
            "waitMs": wait_ms,
        }
        self._log_event(event)
        return GuardrailDecision(
            allowed=True,
            event=event,
            telemetry=event_payload | {"guardrailEvent": event},
            wait_seconds=wait_ms / 1000.0,
        )

    def check_current_domain(
        self, url: str, payload: Dict[str, Any], *, reason: str = "post_action"
    ) -> GuardrailDecision:
        """Lightweight domain check for the current URL without pacing.

        Used after or before actions to ensure the active page remains within
        the allowed domain set. Emits a BLOCKED_DOMAIN event on violation but
        does not sleep or emit NAVIGATE.
        """

        event_payload = payload | {
            "guardrails": {
                "allowedDomains": list(self._allowed_domains),
                "tabCount": self._tab_count,
                "blockedTabAttempts": self._blocked_tab_attempts,
            }
        }
        if not self._is_allowed(url):
            event = event_payload | {
                "event": "guardrail.browser.BLOCKED_DOMAIN",
                "url": url,
                "reason": reason,
            }
            self._log_event(event)
            return GuardrailDecision(
                allowed=False,
                event=event,
                telemetry=event_payload | {"guardrailEvent": event},
                reason="blocked_domain",
            )

        event = event_payload | {
            "event": "guardrail.browser.CURRENT_DOMAIN_ALLOWED",
            "url": url,
            "reason": reason,
        }
        self._log_event(event)
        return GuardrailDecision(
            allowed=True,
            event=event,
            telemetry=event_payload | {"guardrailEvent": event},
        )

    def block_new_tab(self, payload: Dict[str, Any], *, reason: str) -> GuardrailDecision:
        """Record a new-tab attempt and return a blocking decision."""

        self._blocked_tab_attempts += 1
        event_payload = payload | {
            "guardrails": {
                "allowedDomains": list(self._allowed_domains),
                "tabCount": self._tab_count,
                "blockedTabAttempts": self._blocked_tab_attempts,
            }
        }
        event = event_payload | {
            "event": "guardrail.browser.NEW_TAB_ATTEMPT",
            "reason": reason,
        }
        self._log_event(event)
        return GuardrailDecision(
            allowed=False,
            event=event,
            telemetry=event_payload | {"guardrailEvent": event},
            reason="new_tab",
        )

    def think_time(self, payload: Dict[str, Any], *, reason: str) -> Dict[str, Any]:
        """Apply think-time pacing and emit telemetry."""

        seconds = 0.0
        if self._think_range[1] > 0:
            seconds = self._rng.uniform(self._think_range[0], self._think_range[1])
            self._sleep(seconds)
        event = payload | {
            "event": "guardrail.browser.THINK_TIME",
            "reason": reason,
            "seconds": seconds,
        }
        self._log_event(event)
        return event

    @property
    def allowed_domains(self) -> tuple[str, ...]:
        """Return the normalized allowed domain patterns."""

        return self._allowed_domains

    @property
    def wait_range_ms(self) -> tuple[int, int]:
        """Return the configured jitter range in milliseconds."""

        return self._wait_range

    @property
    def think_time_range_s(self) -> tuple[float, float]:
        """Return the configured think-time range in seconds."""

        return self._think_range

