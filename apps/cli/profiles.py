"""Profile configuration models and CLI helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .config_loader import (
    active_profile_marker_path,
    ensure_runtime_dirs,
    get_base_dir,
    load_active_profile,
)
from .utils import ApiError, log_event


class IdentityConfig(BaseModel):
    """Represents the identity/contact section for a profile."""

    full_name: str = Field(..., description="Primary contact name")
    email: str | None = Field(default=None, description="Preferred contact email")
    phone: str | None = Field(default=None, description="Primary phone number")
    location: str | None = Field(default=None, description="Primary location text")
    portfolio: List[str] = Field(default_factory=list, description="Portfolio URLs")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        """Ensure the full name is not blank."""

        if not value or not value.strip():
            raise ValueError("identity.full_name is required")
        return value


class DocumentsConfig(BaseModel):
    """Represents resume/document paths for the profile."""

    resume_path: str = Field(..., alias="resume_path", description="Path to resume PDF")

    @field_validator("resume_path")
    @classmethod
    def validate_resume(cls, value: str) -> str:
        """Ensure the resume path is non-empty."""

        if not value or not value.strip():
            raise ValueError("documents.resume_path is required")
        return value


class BrowserPacingOverrides(BaseModel):
    """Optional pacing overrides for guardrailed automation."""

    wait_jitter_ms: List[int] | None = Field(
        default=None, alias="wait_jitter_ms", description="[min,max] jitter in ms"
    )
    think_time_range_s: List[float] | None = Field(
        default=None,
        alias="think_time_range_s",
        description="[min,max] think time in seconds",
    )

    @model_validator(mode="after")
    def validate_ranges(self) -> "BrowserPacingOverrides":
        if self.wait_jitter_ms is not None:
            if len(self.wait_jitter_ms) != 2:
                raise ValueError("browser.pacing.wait_jitter_ms must contain exactly two values")
            if self.wait_jitter_ms[0] < 0 or self.wait_jitter_ms[1] < self.wait_jitter_ms[0]:
                raise ValueError("browser.pacing.wait_jitter_ms must be an increasing range")
        if self.think_time_range_s is not None:
            if len(self.think_time_range_s) != 2:
                raise ValueError(
                    "browser.pacing.think_time_range_s must contain exactly two values"
                )
            if (
                self.think_time_range_s[0] < 0
                or self.think_time_range_s[1] < self.think_time_range_s[0]
            ):
                raise ValueError(
                    "browser.pacing.think_time_range_s must be an increasing range"
                )
        return self


class BrowserOverridesConfig(BaseModel):
    """Optional Browser-Use overrides stored on the profile."""

    model: str | None = Field(default=None, description="Override Browser-Use model")
    locale: str | None = Field(default=None, description="Override browser locale")
    timezone: str | None = Field(default=None, description="Override browser timezone")
    viewport: Dict[str, int | None] = Field(
        default_factory=dict,
        description="Optional viewport overrides with width/height keys",
    )
    chrome_path: str | None = Field(
        default=None, description="Override Chrome executable for this profile"
    )
    allowed_domains: List[str] | None = Field(
        default=None,
        alias="allowed_domains",
        description="Domain allowlist overrides",
    )
    pacing: BrowserPacingOverrides | None = Field(
        default=None,
        alias="pacing",
        description="Guardrail pacing overrides",
    )

    @model_validator(mode="after")
    def validate_viewport(self) -> "BrowserOverridesConfig":
        width = self.viewport.get("width") if isinstance(self.viewport, dict) else None
        height = self.viewport.get("height") if isinstance(self.viewport, dict) else None
        if width is not None and width <= 0:
            raise ValueError("browser.viewport.width must be positive")
        if height is not None and height <= 0:
            raise ValueError("browser.viewport.height must be positive")
        return self


class ProfileConfig(BaseModel):
    """Pydantic model representing a profile configuration."""

    id: str = Field(..., description="Profile identifier/slug")
    display_name: str = Field(..., alias="display_name", description="Human readable name")
    identity: IdentityConfig
    documents: DocumentsConfig
    qa_overrides: Dict[str, str] = Field(default_factory=dict, alias="qa_overrides")
    model_overrides: Dict[str, Any] = Field(default_factory=dict, alias="model_overrides")
    links: Dict[str, Any] = Field(default_factory=dict)
    user_data_dir: str | None = Field(
        default=None,
        alias="user_data_dir",
        description="Browser session directory",
    )
    browser: BrowserOverridesConfig | None = Field(
        default=None,
        alias="browser",
        description="Browser-Use overrides for this profile",
    )

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Ensure the profile id is slug-like."""

        if not value or not value.strip():
            raise ValueError("id is required")
        if any(ch.isspace() for ch in value):
            raise ValueError("id must not contain whitespace")
        return value

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        """Ensure the display name is non-empty."""

        if not value or not value.strip():
            raise ValueError("display_name is required")
        return value

    @model_validator(mode="after")
    def ensure_user_data_dir(self) -> "ProfileConfig":
        """Populate default user data dir when omitted."""

        if not self.user_data_dir:
            self.user_data_dir = f".local/browser/profiles/{self.id}"
        return self

    def resolved_resume_path(self, base: Path) -> Path:
        """Return an absolute path to the configured resume."""

        resume = Path(self.documents.resume_path)
        if not resume.is_absolute():
            resume = (base / resume).resolve()
        return resume

    def resolved_user_data_dir(self, base: Path) -> Path:
        """Return an absolute path to the browser session directory."""

        directory = Path(self.user_data_dir or f".local/browser/profiles/{self.id}")
        if not directory.is_absolute():
            directory = (base / directory).resolve()
        return directory

    def resolved_browser_overrides(self) -> Dict[str, Any]:
        """Return normalized browser overrides for CLI/config merging."""

        if not self.browser:
            return {}
        overrides: Dict[str, Any] = {}
        if self.browser.model:
            overrides["model"] = self.browser.model
        if self.browser.locale:
            overrides["locale"] = self.browser.locale
        if self.browser.timezone:
            overrides["timezone"] = self.browser.timezone
        if isinstance(self.browser.viewport, dict):
            viewport: Dict[str, int] = {}
            width = self.browser.viewport.get("width")
            height = self.browser.viewport.get("height")
            if isinstance(width, int) and width > 0:
                viewport["width"] = width
            if isinstance(height, int) and height > 0:
                viewport["height"] = height
            if viewport:
                overrides["viewport"] = viewport
        if self.browser.chrome_path:
            overrides["chrome_path"] = self.browser.chrome_path
        if self.browser.allowed_domains:
            domains = [value.strip() for value in self.browser.allowed_domains if value.strip()]
            if domains:
                overrides["allowed_domains"] = domains
        if self.browser.pacing:
            pacing: Dict[str, Any] = {}
            if self.browser.pacing.wait_jitter_ms:
                pacing["wait_jitter_ms"] = list(self.browser.pacing.wait_jitter_ms)
            if self.browser.pacing.think_time_range_s:
                pacing["think_time_range_s"] = list(self.browser.pacing.think_time_range_s)
            if pacing:
                overrides["pacing"] = pacing
        return overrides


@dataclass
class ProfileValidationResult:
    """Represents the outcome of validating a profile."""

    profile_id: str
    profile: ProfileConfig | None
    errors: List[Dict[str, Any]]
    resume_path: Path | None

    @property
    def is_valid(self) -> bool:
        """Return True when no validation errors were recorded."""

        return not self.errors

    @property
    def resume_exists(self) -> bool:
        """Return True if a resume path was resolved and exists."""

        return self.resume_path is not None and self.resume_path.exists()


PROFILE_TEMPLATE = (
    "# Profile configuration for Job AI Auto Apply\n"
    "# Fill in identity/contact information and customize overrides as needed.\n"
    "id: {profile_id}\n"
    "display_name: {display_name}\n"
    "identity:\n"
    "  full_name: \"\"  # Required\n"
    "  email: \"\"\n"
    "  phone: \"\"\n"
    "  location: \"\"\n"
    "  portfolio: []\n"
    "documents:\n"
    "  resume_path: data/resumes/{profile_id}/resume.pdf\n"
    "model_overrides:\n"
    "  llm: deepseek/deepseek-chat-v3.1:free\n"
    "qa_overrides: {{}}\n"
    "links: {{}}\n"
    "user_data_dir: .local/browser/profiles/{profile_id}\n"
    "browser:\n"
    "  model: null\n"
    "  locale: null\n"
    "  timezone: null\n"
    "  viewport:\n"
    "    width: null\n"
    "    height: null\n"
    "  chrome_path: null\n"
)


class ProfileService:
    """High-level helpers for profile CLI commands."""

    def __init__(self, base: Path | None = None) -> None:
        self.base = base or get_base_dir()
        ensure_runtime_dirs(self.base)
        self.profiles_dir = self.base / "data" / "profiles"
        self.resumes_dir = self.base / "data" / "resumes"
        self.browser_profiles_dir = self.base / ".local" / "browser" / "profiles"

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------
    def profile_path(self, profile_id: str) -> Path:
        """Return the YAML path for a profile id."""

        return self.profiles_dir / f"{profile_id}.yaml"

    def create_profile(self, profile_id: str, *, force: bool = False) -> Path:
        """Create a new profile YAML from the template."""

        profile_path = self.profile_path(profile_id)
        if profile_path.exists() and not force:
            error = ApiError(
                code="profiles.exists",
                message=f"Profile '{profile_id}' already exists. Use --force to overwrite.",
                details={"path": str(profile_path)},
            )
            raise FileExistsError(error.to_json())

        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        (self.resumes_dir / profile_id).mkdir(parents=True, exist_ok=True)
        (self.browser_profiles_dir / profile_id).mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            PROFILE_TEMPLATE.format(profile_id=profile_id, display_name=profile_id.replace("-", " ").title()),
            encoding="utf-8",
        )
        log_event(
            {
                "level": "info",
                "event": "profiles.created",
                "profile_id": profile_id,
                "path": str(profile_path),
            }
        )
        return profile_path

    def load_profile(self, profile_id: str) -> ProfileConfig:
        """Load a profile YAML and return the parsed configuration."""

        path = self.profile_path(profile_id)
        if not path.exists():
            raise FileNotFoundError(f"Profile '{profile_id}' does not exist at {path}")

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse YAML for profile '{profile_id}': {exc}") from exc

        try:
            return ProfileConfig.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(json.dumps(exc.errors(), ensure_ascii=False)) from exc

    # ------------------------------------------------------------------
    # Validation & listing
    # ------------------------------------------------------------------
    def validate_profile(self, profile_id: str) -> ProfileValidationResult:
        """Validate a profile configuration and resume presence."""

        errors: List[Dict[str, Any]] = []
        resume_path: Path | None = None
        profile: ProfileConfig | None = None
        path = self.profile_path(profile_id)

        if not path.exists():
            errors.append(
                {
                    "code": "profiles.missing",
                    "message": f"Profile '{profile_id}' was not found.",
                    "details": {"path": str(path)},
                }
            )
            return ProfileValidationResult(profile_id, None, errors, None)

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            errors.append(
                {
                    "code": "profiles.yaml_invalid",
                    "message": f"Profile '{profile_id}' YAML is invalid.",
                    "details": {"path": str(path), "error": str(exc)},
                }
            )
            return ProfileValidationResult(profile_id, None, errors, None)

        try:
            profile = ProfileConfig.model_validate(raw)
        except ValidationError as exc:
            for err in exc.errors():
                errors.append(
                    {
                        "code": "profiles.schema_invalid",
                        "message": err.get("msg", "Invalid field"),
                        "details": {
                            "location": err.get("loc"),
                            "type": err.get("type"),
                        },
                    }
                )
            return ProfileValidationResult(profile_id, None, errors, None)

        resume_path = profile.resolved_resume_path(self.base)
        if not resume_path.exists():
            errors.append(
                {
                    "code": "profiles.resume_missing",
                    "message": f"Resume PDF not found for '{profile_id}'.",
                    "details": {"expected": str(resume_path)},
                }
            )

        return ProfileValidationResult(profile_id, profile, errors, resume_path)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """Return profile metadata for CLI consumption."""

        ensure_runtime_dirs(self.base)
        active = load_active_profile(self.base)
        items: List[Dict[str, Any]] = []
        for path in sorted(self.profiles_dir.glob("*.yaml")):
            profile_id = path.stem
            result = self.validate_profile(profile_id)
            items.append(
                {
                    "id": profile_id,
                    "valid": result.is_valid,
                    "resume": {
                        "exists": result.resume_exists,
                        "path": str(result.resume_path) if result.resume_path else None,
                    },
                    "active": profile_id == active,
                    "errors": result.errors,
                }
            )
        return items

    # ------------------------------------------------------------------
    # Active profile helpers
    # ------------------------------------------------------------------
    def set_active_profile(self, profile_id: str) -> Path:
        """Persist the active profile marker for subsequent CLI runs."""

        marker = active_profile_marker_path(self.base)
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_profile": profile_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log_event(
            {
                "level": "info",
                "event": "profiles.active_set",
                "profile_id": profile_id,
                "path": str(marker),
            }
        )
        return marker

    def current_profile(self) -> Dict[str, Any] | None:
        """Return metadata for the active profile, if any."""

        active = load_active_profile(self.base)
        if not active:
            return None
        result = self.validate_profile(active)
        data = {
            "id": active,
            "valid": result.is_valid,
            "resume": {
                "exists": result.resume_exists,
                "path": str(result.resume_path) if result.resume_path else None,
            },
            "errors": result.errors,
        }
        if result.profile:
            data.update(
                {
                    "display_name": result.profile.display_name,
                    "user_data_dir": str(result.profile.resolved_user_data_dir(self.base)),
                    "browser": result.profile.resolved_browser_overrides(),
                }
            )
        return data
