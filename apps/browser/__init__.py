"""Browser automation wrapper package for Job AI Auto Apply."""

from .controller import (
    BrowserUseController,
    BrowserLaunchConfig,
    BrowserLaunchError,
    BrowserActionResult,
    BrowserActionStatus,
    BrowserUseError,
    ReviewArtifactCapture,
)
from .guardrails import NavigationGuardrails
from .session_backup import SessionBackupManager

__all__ = [
    "BrowserUseController",
    "BrowserLaunchConfig",
    "BrowserLaunchError",
    "BrowserActionResult",
    "BrowserActionStatus",
    "BrowserUseError",
    "ReviewArtifactCapture",
    "NavigationGuardrails",
    "SessionBackupManager",
]
