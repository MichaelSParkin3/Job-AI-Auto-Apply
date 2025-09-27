"""Browser automation wrapper package for Job AI Auto Apply."""

from .controller import (
    BrowserUseController,
    BrowserLaunchConfig,
    BrowserActionResult,
    BrowserActionStatus,
    BrowserUseError,
)
from .guardrails import NavigationGuardrails

__all__ = [
    "BrowserUseController",
    "BrowserLaunchConfig",
    "BrowserActionResult",
    "BrowserActionStatus",
    "BrowserUseError",
    "NavigationGuardrails",
]
