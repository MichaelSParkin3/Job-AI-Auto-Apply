"""Lever provider: Google-SERP discovery and Lever form helpers.

This package hosts the provider modules for the Lever pivot described in
docs/stories/4.0.lever-google-source-pivot.md.

Scope in this scaffold:
- URL builder and planning for Google SERP discovery constrained to Lever.
- Minimal selector JSON for common Lever fields.
- Thin form executor stub to be wired to BrowserUseController later.
"""

from .form_executor import (
    LeverFieldPlan,
    LeverFormExecutor,
    LeverFormPlan,
    LeverFormPlanner,
    detect_resume_success,
)
from .lever_google_discovery import (
    LeverGoogleDiscovery,
    LeverGooglePlan,
    LeverSerpResult,
    build_google_query,
    paginate,
)


__all__ = [
    "LeverFieldPlan",
    "LeverFormExecutor",
    "LeverFormPlan",
    "LeverFormPlanner",
    "LeverGoogleDiscovery",
    "LeverGooglePlan",
    "LeverSerpResult",
    "build_google_query",
    "detect_resume_success",
    "paginate",
]

