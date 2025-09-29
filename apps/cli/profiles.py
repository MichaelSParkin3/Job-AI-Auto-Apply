"""Profile configuration models and CLI helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import re
import unicodedata

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


def _normalize_key(value: str) -> str:
    """Return a canonical key for override lookups."""

    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def _collapse_whitespace(value: str) -> str:
    """Collapse whitespace for deterministic preview strings."""

    return re.sub(r"\s+", " ", value).strip()


def _normalize_phone(value: str) -> str | None:
    """Return the phone number formatted as `+1 555 555 5555` when possible."""

    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return None
    if len(digits) == 10:
        return f"+1 {digits[0:3]} {digits[3:6]} {digits[6:]}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+1 {digits[1:4]} {digits[4:7]} {digits[7:]}"
    return "+" + digits


@dataclass(slots=True)
class ResolvedAnswer:
    """Represents a resolved answer from the active profile."""

    value: str | bool | None
    status: str
    source: str | None = None
    reason: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved"


@dataclass(frozen=True)
class ProfileBinding:
    """Resolved metadata required to bind a profile to runtime sessions."""

    profile_id: str
    display_name: str
    resume_path: Path
    user_data_dir: Path
    qa_overrides: Dict[str, str]
    model_overrides: Dict[str, Any]
    browser_overrides: Dict[str, Any]
    session_backups_enabled: bool | None
    session_backups_retention: int | None
    resume_exists: bool
    errors: List[Dict[str, Any]]

    @property
    def is_valid(self) -> bool:
        """Return True when validation produced no blocking errors."""

        return not self.errors and self.resume_exists

    def cli_payload(self) -> Dict[str, Any]:
        """Return a JSON-serialisable payload for CLI consumers."""

        return {
            "id": self.profile_id,
            "display_name": self.display_name,
            "valid": self.is_valid,
            "resume": {
                "path": str(self.resume_path),
                "exists": self.resume_exists,
            },
            "user_data_dir": str(self.user_data_dir),
            "qa_overrides": dict(self.qa_overrides),
            "model_overrides": dict(self.model_overrides),
            "browser": dict(self.browser_overrides),
            "session_backups": {
                "enabled": self.session_backups_enabled,
                "retention": self.session_backups_retention,
            },
            "errors": [dict(error) for error in self.errors],
        }

    def telemetry_payload(self) -> Dict[str, Any]:
        """Return a redaction-friendly structure for log events and guardrails."""

        return {
            "id": self.profile_id,
            "displayName": self.display_name,
            "resume": {
                "exists": self.resume_exists,
            },
            "userDataDir": str(self.user_data_dir),
            "qaOverrideKeys": sorted(self.qa_overrides.keys()),
            "model": self.model_overrides.get("llm"),
            "browser": dict(self.browser_overrides),
            "sessionBackups": {
                "enabled": self.session_backups_enabled,
                "retention": self.session_backups_retention,
            },
        }

    def list_payload(self, *, active: bool) -> Dict[str, Any]:
        """Return the structure used by `profiles list`."""

        payload = self.cli_payload()
        payload["active"] = active
        return payload

    @classmethod
    def from_validation(
        cls, base: Path, result: "ProfileValidationResult"
    ) -> "ProfileBinding":
        """Build a binding from a successful validation result."""

        if not result.profile:
            raise ValueError("Cannot build binding without a parsed profile.")

        profile = result.profile
        resume_path = profile.resolved_resume_path(base)
        user_data_dir = profile.resolved_user_data_dir(base)
        return cls(
            profile_id=profile.id,
            display_name=profile.display_name,
            resume_path=resume_path,
            user_data_dir=user_data_dir,
            qa_overrides=dict(profile.qa_overrides),
            model_overrides=dict(profile.model_overrides),
            browser_overrides=profile.resolved_browser_overrides(),
            session_backups_enabled=profile.session_backups.enabled
            if profile.session_backups
            else None,
            session_backups_retention=profile.session_backups.retention
            if profile.session_backups
            else None,
            resume_exists=result.resume_exists,
            errors=[dict(error) for error in result.errors],
        )

    @classmethod
    def demo(cls, base: Path, profile_id: str = "demo") -> "ProfileBinding":
        """Return a permissive binding for the dry-run demo fallback."""

        resume_path = (base / "data" / "resumes" / profile_id / "resume.pdf").resolve()
        user_data_dir = (base / ".local" / "browser" / "profiles" / profile_id).resolve()
        return cls(
            profile_id=profile_id,
            display_name="Demo profile",
            resume_path=resume_path,
            user_data_dir=user_data_dir,
            qa_overrides={},
            model_overrides={},
            browser_overrides={},
            session_backups_enabled=None,
            session_backups_retention=None,
            resume_exists=resume_path.exists(),
            errors=[],
        )


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


class SessionBackupConfig(BaseModel):
    """Optional session backup overrides stored on the profile."""

    enabled: bool | None = Field(default=None, description="Enable session backups")
    retention: int | None = Field(default=None, description="Maximum backups to keep")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_retention(self) -> "SessionBackupConfig":
        if self.retention is not None and self.retention < 1:
            raise ValueError("session_backups.retention must be >= 1")
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
    # New: search/source configuration for discovery
    class SearchConfig(BaseModel):
        source: str = Field(
            default="lever-google",
            description="Discovery provider id (e.g., lever-google)",
            alias="source",
        )
        terms: list[str] = Field(default_factory=list, description="Role keywords")
        location: str | None = Field(default=None, description="Location string")
        time_window: str = Field(
            default="d",
            description="Google qdr window: h|d|w|m|y (default d=past 24h)",
            alias="time_window",
        )

        model_config = ConfigDict(populate_by_name=True, extra="ignore")

        @field_validator("time_window")
        @classmethod
        def validate_window(cls, value: str) -> str:
            allowed = {"h", "d", "w", "m", "y"}
            if value not in allowed:
                raise ValueError("time_window must be one of h|d|w|m|y")
            return value

    search: SearchConfig | None = Field(default=None, alias="search")
    browser: BrowserOverridesConfig | None = Field(
        default=None,
        alias="browser",
        description="Browser-Use overrides for this profile",
    )
    session_backups: SessionBackupConfig | None = Field(
        default=None,
        alias="session_backups",
        description="Session backup overrides",
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
    "  allowed_domains:\n"
    "    - '*.simplyhired.com'\n"
    "    - 'jobs.lever.co'\n"
    "    - '*.jobs.lever.co'\n"
    "    - 'api.lever.co'\n"
    "    - 'newassets.hcaptcha.com'\n"
    "search:\n"
    "  source: lever-google\n"
    "  terms: ['front end']\n"
    "  location: 'remote us'\n"
    "  time_window: d\n"
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
            binding = self._binding_from_result(result)
            if binding:
                items.append(binding.list_payload(active=profile_id == active))
            else:
                items.append(
                    {
                        "id": profile_id,
                        "display_name": None,
                        "valid": False,
                        "resume": {
                            "exists": False,
                            "path": None,
                        },
                        "user_data_dir": None,
                        "qa_overrides": {},
                        "model_overrides": {},
                        "browser": {},
                        "errors": result.errors,
                        "active": profile_id == active,
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
        binding = self._binding_from_result(result)
        if binding:
            return binding.cli_payload()
        return {
            "id": active,
            "display_name": None,
            "valid": False,
            "resume": {"exists": False, "path": None},
            "user_data_dir": None,
            "qa_overrides": {},
            "model_overrides": {},
            "browser": {},
            "errors": result.errors,
        }

    # ------------------------------------------------------------------
    # Binding helpers
    # ------------------------------------------------------------------
    def _binding_from_result(
        self, result: ProfileValidationResult
    ) -> ProfileBinding | None:
        """Internal helper to convert validation results to bindings."""

        if not result.profile:
            return None
        return ProfileBinding.from_validation(self.base, result)

    def build_binding(self, profile_id: str) -> ProfileBinding | None:
        """Return a binding even when the profile is not fully valid."""

        result = self.validate_profile(profile_id)
        return self._binding_from_result(result)

    def bind_profile(
        self,
        profile_id: str,
        *,
        require_resume: bool = True,
        allow_missing_profile: bool = False,
    ) -> ProfileBinding:
        """Return a validated binding or raise a structured error."""

        result = self.validate_profile(profile_id)
        binding = self._binding_from_result(result)
        if not binding:
            if allow_missing_profile:
                return ProfileBinding.demo(self.base, profile_id=profile_id)
            error = ApiError(
                code="profiles.not_found",
                message=f"Profile '{profile_id}' was not found.",
                details={"errors": result.errors},
            )
            raise error

        errors = list(result.errors)
        if not require_resume:
            errors = [err for err in errors if err.get("code") != "profiles.resume_missing"]

        if errors or (require_resume and not binding.resume_exists):
            error = ApiError(
                code="profiles.validation_failed",
                message=f"Profile '{profile_id}' failed validation.",
                details={"errors": result.errors},
            )
            raise error

        return binding


class ProfileAnswerResolver:
    """Resolve form answers using profile identity and overrides."""

    def __init__(
        self,
        *,
        profile: ProfileConfig | None,
        binding: ProfileBinding | None = None,
    ) -> None:
        self._profile = profile
        self.profile_id = (
            binding.profile_id
            if binding is not None
            else (profile.id if profile is not None else None)
        )
        self.display_name = (
            binding.display_name
            if binding is not None
            else (profile.display_name if profile is not None else None)
        )
        self._override_index: Dict[str, str] = {}
        if profile is not None:
            self._register_overrides(profile.qa_overrides)
        if binding is not None:
            self._register_overrides(binding.qa_overrides)
        self._links_index: Dict[str, str] = {}
        if profile is not None:
            for key, value in profile.links.items():
                if isinstance(value, str) and value.strip():
                    self._links_index[_normalize_key(key)] = value.strip()
            # Allow quick lookups for canonical keys such as "linkedin"
            for key, value in profile.links.items():
                if isinstance(value, str) and value.strip():
                    lowered = key.lower()
                    if "linkedin" in lowered:
                        self._links_index.setdefault("linkedin", value.strip())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def resolve(
        self,
        *,
        profile_field: str,
        label: str | None = None,
        options: Sequence[Mapping[str, Any]] | None = None,
        synonyms: Iterable[str] | None = None,
    ) -> ResolvedAnswer:
        handler = getattr(self, f"_resolve_{profile_field}", None)
        if handler:
            answer = handler(label=label, options=options, synonyms=synonyms)
            if isinstance(answer, ResolvedAnswer):
                return answer

        return self._resolve_from_overrides(
            profile_field,
            label=label,
            options=options,
            synonyms=synonyms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _register_overrides(self, overrides: Mapping[str, Any]) -> None:
        for key, value in overrides.items():
            if not isinstance(value, str):
                value = str(value)
            normalized = _normalize_key(key)
            if normalized:
                self._override_index[normalized] = value.strip()

    def _candidate_keys(
        self,
        profile_field: str,
        *,
        label: str | None,
        options: Sequence[Mapping[str, Any]] | None,
        synonyms: Iterable[str] | None,
        extra: Iterable[str] | None = None,
    ) -> list[str]:
        candidates: list[str] = []
        if profile_field:
            candidates.append(profile_field)
            spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", profile_field)
            if spaced and spaced != profile_field:
                candidates.append(spaced)
        if label:
            candidates.append(label)
        if synonyms:
            candidates.extend(synonyms)
        if options:
            for option in options:
                label_value = option.get("label")
                if isinstance(label_value, str) and label_value.strip():
                    candidates.append(label_value)
                value = option.get("value")
                if isinstance(value, str) and value.strip():
                    candidates.append(value)
        if extra:
            candidates.extend(extra)
        # Remove empty entries while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in candidates:
            normalized = _normalize_key(candidate)
            if normalized and normalized not in seen:
                seen.add(normalized)
                ordered.append(candidate)
        return ordered

    def _resolve_from_overrides(
        self,
        profile_field: str,
        *,
        label: str | None,
        options: Sequence[Mapping[str, Any]] | None,
        synonyms: Iterable[str] | None,
        extra: Iterable[str] | None = None,
    ) -> ResolvedAnswer:
        candidates = self._candidate_keys(
            profile_field,
            label=label,
            options=options,
            synonyms=synonyms,
            extra=extra,
        )
        for candidate in candidates:
            normalized = _normalize_key(candidate)
            if normalized and normalized in self._override_index:
                value = _collapse_whitespace(self._override_index[normalized])
                return ResolvedAnswer(
                    value=value,
                    status="resolved",
                    source="qa_override",
                )
        return ResolvedAnswer(
            value=None,
            status="missing",
            source="qa_override",
            reason="profile_missing",
        )

    # ------------------------------------------------------------------
    # Field-specific resolvers
    # ------------------------------------------------------------------
    def _resolve_fullName(self, **_kwargs: Any) -> ResolvedAnswer:
        if self._profile and self._profile.identity.full_name:
            value = _collapse_whitespace(self._profile.identity.full_name)
            return ResolvedAnswer(value=value, status="resolved", source="identity.full_name")
        return ResolvedAnswer(
            value=None,
            status="missing",
            source="identity.full_name",
            reason="profile_missing",
        )

    def _resolve_email(self, **_kwargs: Any) -> ResolvedAnswer:
        if self._profile and self._profile.identity.email:
            email = _collapse_whitespace(self._profile.identity.email)
            return ResolvedAnswer(value=email.casefold(), status="resolved", source="identity.email")
        return ResolvedAnswer(
            value=None,
            status="missing",
            source="identity.email",
            reason="profile_missing",
        )

    def _resolve_phone(self, **_kwargs: Any) -> ResolvedAnswer:
        if self._profile and self._profile.identity.phone:
            normalized = _normalize_phone(self._profile.identity.phone)
            if normalized:
                return ResolvedAnswer(value=normalized, status="resolved", source="identity.phone")
        return ResolvedAnswer(
            value=None,
            status="missing",
            source="identity.phone",
            reason="profile_missing",
        )

    def _resolve_preferredName(self, **_kwargs: Any) -> ResolvedAnswer:
        override = self._resolve_from_overrides("preferredName", label=None, options=None, synonyms=None)
        if override.is_resolved:
            return override
        full_name = None
        if self._profile and self._profile.identity.full_name:
            full_name = self._profile.identity.full_name.strip()
        elif self.display_name:
            full_name = self.display_name.strip()
        if full_name:
            first = full_name.split()[0]
            if first:
                return ResolvedAnswer(value=first, status="resolved", source="identity.full_name")
        return ResolvedAnswer(
            value=None,
            status="missing",
            source="preferredName",
            reason="profile_missing",
        )

    def _resolve_linkedinUrl(self, **_kwargs: Any) -> ResolvedAnswer:
        override = self._resolve_from_overrides("linkedin", label=None, options=None, synonyms=None, extra=["linkedinurl"])
        if override.is_resolved:
            return override
        if "linkedin" in self._links_index:
            return ResolvedAnswer(
                value=self._links_index["linkedin"],
                status="resolved",
                source="links.linkedin",
            )
        if self._profile and self._profile.identity.portfolio:
            for entry in self._profile.identity.portfolio:
                if isinstance(entry, str) and "linkedin" in entry.lower():
                    return ResolvedAnswer(value=entry.strip(), status="resolved", source="identity.portfolio")
        return ResolvedAnswer(
            value=None,
            status="missing",
            source="links.linkedin",
            reason="profile_missing",
        )

    def _resolve_coverLetter(self, **_kwargs: Any) -> ResolvedAnswer:
        override = self._resolve_from_overrides("coverLetter", label=None, options=None, synonyms=None)
        if override.is_resolved:
            return override
        if not self._profile or not self._profile.identity.full_name:
            return ResolvedAnswer(
                value=None,
                status="missing",
                source="coverLetter",
                reason="profile_missing",
            )
        first_name = self._profile.identity.full_name.split()[0]
        location = self._profile.identity.location or "remote"
        summary = (
            f"Hello, I'm {first_name}. I am interested in this opportunity and have experience working {location.lower()}."
        )
        return ResolvedAnswer(
            value=summary,
            status="resolved",
            source="identity.narrative",
        )

    def _resolve_workAuthorization(
        self,
        *,
        label: str | None,
        options: Sequence[Mapping[str, Any]] | None,
        synonyms: Iterable[str] | None,
    ) -> ResolvedAnswer:
        return self._resolve_from_overrides(
            "workAuthorization",
            label=label,
            options=options,
            synonyms=synonyms,
            extra=["authorized", "authorization"],
        )

    def _resolve_relocation(
        self,
        *,
        label: str | None,
        options: Sequence[Mapping[str, Any]] | None,
        synonyms: Iterable[str] | None,
    ) -> ResolvedAnswer:
        return self._resolve_from_overrides(
            "relocation",
            label=label,
            options=options,
            synonyms=synonyms,
        )

    def _resolve_experienceLevel(
        self,
        *,
        label: str | None,
        options: Sequence[Mapping[str, Any]] | None,
        synonyms: Iterable[str] | None,
    ) -> ResolvedAnswer:
        return self._resolve_from_overrides(
            "experienceLevel",
            label=label,
            options=options,
            synonyms=synonyms,
            extra=["experience"],
        )
