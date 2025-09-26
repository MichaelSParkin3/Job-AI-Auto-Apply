"""Shared constants for preview demo flows."""

from __future__ import annotations

PLACEHOLDER_SCREENSHOT_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)
PLACEHOLDER_SCREENSHOT_DATA_URI = (
    f"data:image/png;base64,{PLACEHOLDER_SCREENSHOT_BASE64}"
)

PLACEHOLDER_SUMMARY = (
    "Dry-run preview generated for demo purposes. This snapshot represents the "
    "final review step the automation captured before submission."
)

PLACEHOLDER_NOTES = "Approve, edit, or abort using shortcuts."


def placeholder_screenshot_bytes() -> bytes:
    """Return the decoded PNG bytes for the placeholder screenshot."""

    import base64

    return base64.b64decode(PLACEHOLDER_SCREENSHOT_BASE64)


__all__ = [
    "PLACEHOLDER_NOTES",
    "PLACEHOLDER_SCREENSHOT_BASE64",
    "PLACEHOLDER_SCREENSHOT_DATA_URI",
    "PLACEHOLDER_SUMMARY",
    "placeholder_screenshot_bytes",
]
