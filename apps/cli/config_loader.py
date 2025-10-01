from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
from .utils import log_event


DEFAULTS = {
    "log_level": "INFO",
    "artifacts_keep_days": 30,
    "history_keep_days": 60,
    "actions_log_max_mb": 25,
    "active_profile": None,
    "dry_run": False,
    "preview_port": 4950,
    "chrome_path": None,
    "browser_model": "deepseek/deepseek-chat-v3.1:free",
    "browser_locale": "en-US",
    "browser_timezone": "America/Los_Angeles",
    "browser_viewport_width": 1366,
    "browser_viewport_height": 768,
    "browser_allowed_domains": [
        "*.simplyhired.com",
        "jobs.lever.co",
        "*.jobs.lever.co",
        "api.lever.co",
        "newassets.hcaptcha.com",
    ],
    "browser_pacing_wait_jitter_ms": [100, 600],
    "browser_pacing_think_time_range_s": [1.0, 2.0],
    "browser_session_backups_enabled": True,
    "browser_session_backups_retention": 2,
    "search_ready_retry_attempts": 1,
    "search_ready_backoff_seconds": 2.0,
    "search_ready_selector_override": None,
    "search_ready_min_cards": 10,
    "quick_apply_selector_override": None,
    "plan": {
        "browser_discovery": False,
        "programmable_search": False,
        "google_cse_key": None,
        "google_cse_cx": None,
        "model": "deepseek/deepseek-chat-v3.1:free",
        "llm_enabled": True,
    },
    "automation": {
        "answerPolicies": {
            "enabled": True,
            "minConfidence": 0.75,
            "allowSaveToProfile": True,
            "allowLLMFallback": True,
            "model": "openrouter/mistral-small",
        }
    },
}


ACTIVE_PROFILE_FILENAME = "active-profile.json"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def get_base_dir() -> Path:
    """Return project root, searching upwards from this file for pyproject.toml."""
    if env_override := os.environ.get("JAA_BASE_DIR"):
        return Path(env_override).resolve()

    start_dir = Path(__file__).parent
    for path in [start_dir] + list(start_dir.parents):
        if (path / "pyproject.toml").exists():
            return path.resolve()
    # Fallback for edge cases (e.g., weird execution context)
    return Path.cwd()


def ensure_runtime_dirs(base: Path | None = None) -> Dict[str, str]:
    """Ensure all required runtime directories exist.

    Creates the standard folder structure (`config`, `data/profiles`, etc.)
    idempotently.

    Args:
        base (Path | None): The base directory to create folders in.
            If None, uses the project root.

    Returns:
        dict: A confirmation dictionary with the base path.
    """
    base = base or get_base_dir()
    required = [
        base / "config",
        base / "data" / "profiles",
        base / "data" / "resumes",
        base / ".local",
        base / ".local" / "browser",
        base / ".local" / "browser" / "profiles",
        base / ".local" / "state",
        base / "runs",
        base / "history",
    ]
    for d in required:
        d.mkdir(parents=True, exist_ok=True)
    return {"created": "ok", "base": str(base)}


def active_profile_marker_path(base: Path | None = None) -> Path:
    """Return the location of the active profile marker file."""

    base = base or get_base_dir()
    return base / ".local" / "state" / ACTIVE_PROFILE_FILENAME


def load_active_profile(base: Path | None = None) -> str | None:
    """Return the active profile id from the persisted marker if present."""

    marker = active_profile_marker_path(base)
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log_event(
            {
                "level": "error",
                "message": f"Failed to parse {marker}; ignoring active profile marker.",
                "event": "profiles.marker_corrupt",
                "error": str(exc),
            }
        )
        return None
    return data.get("active_profile")


def load_env(base: Path | None = None) -> Dict[str, Any]:
    """Load environment variables from .env.local if it exists.

    Loads the file and logs a warning if it's not found. Only exposes
    expected variables to the application.

    Args:
        base (Path | None): The base directory to search for `.env.local` in.
            If None, uses the project root.

    Returns:
        dict: A dictionary with the loaded environment variables.
    """
    base = base or get_base_dir()
    env_path = base / ".env.local"
    # load_dotenv returns False if file absent; that's acceptable per AC #3
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        log_event({
            "level": "warning",
            "message": ".env.local not found; proceeding without OpenRouter keys",
            "event": "env.missing",
            "path": str(env_path),
        })
    # Expose only expected keys
    env_config: Dict[str, Any] = {
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY"),
        "OPENROUTER_MODEL": os.environ.get("OPENROUTER_MODEL"),
    }
    if env_config.get("OPENROUTER_MODEL"):
        env_config["plan.model"] = env_config["OPENROUTER_MODEL"]
        env_config["automation.answerPolicies.model"] = env_config["OPENROUTER_MODEL"]
    if google_cse_key := os.environ.get("GOOGLE_CSE_KEY"):
        env_config["plan.google_cse_key"] = google_cse_key
    if google_cse_cx := os.environ.get("GOOGLE_CSE_CX"):
        env_config["plan.google_cse_cx"] = google_cse_cx
    # Allow optional environment overrides for demo helpers
    if chrome_path := os.environ.get("JAA_CHROME_PATH"):
        env_config["chrome_path"] = chrome_path
    if preview_port := os.environ.get("JAA_PREVIEW_PORT"):
        try:
            env_config["preview_port"] = int(preview_port)
        except ValueError:
            log_event({
                "level": "warning",
                "message": f"Invalid JAA_PREVIEW_PORT value '{preview_port}', ignoring.",
                "event": "config.preview_port_invalid",
            })
    if dry_run := os.environ.get("JAA_DRY_RUN"):
        env_config["dry_run"] = dry_run.lower() in {"1", "true", "yes"}
    return env_config


def config_path(base: Path | None = None) -> Path:
    """Return the absolute path to the global config.yaml file.

    Args:
        base (Path | None): The base directory. If None, uses the project root.

    Returns:
        Path: The resolved path to the config file.
    """
    base = base or get_base_dir()
    return base / "config" / "config.yaml"


def write_default_config(base: Path | None = None) -> Path:
    """Write the default config.yaml if it doesn't exist.

    This function is idempotent.

    Args:
        base (Path | None): The base directory. If None, uses the project root.

    Returns:
        Path: The path to the (potentially newly created) config file.
    """
    base = base or get_base_dir()
    ensure_runtime_dirs(base)
    cfg_path = config_path(base)
    if not cfg_path.exists():
        header = (
            "# Job-AI-Auto-Apply configuration\n"
            "# Precedence: CLI > profile YAML > global defaults\n"
            "# Retention fields (artifacts/history/actions log) are placeholders until cleanup is implemented.\n"
        )
        text = header + yaml.safe_dump(DEFAULTS, sort_keys=True)
        cfg_path.write_text(text, encoding="utf-8")
    return cfg_path


@dataclass
class Settings:
    """Manages application settings with a layered loading mechanism.

    This class consolidates settings from default values, a global `config.yaml`
    file, environment variables (`.env.local`), and direct CLI overrides.
    """

    log_level: str = DEFAULTS["log_level"]
    artifacts_keep_days: int = DEFAULTS["artifacts_keep_days"]
    history_keep_days: int = DEFAULTS["history_keep_days"]
    actions_log_max_mb: int = DEFAULTS["actions_log_max_mb"]
    active_profile: str | None = DEFAULTS["active_profile"]
    dry_run: bool = DEFAULTS["dry_run"]
    preview_port: int = DEFAULTS["preview_port"]
    chrome_path: str | None = DEFAULTS["chrome_path"]
    browser_model: str = DEFAULTS["browser_model"]
    browser_locale: str = DEFAULTS["browser_locale"]
    browser_timezone: str = DEFAULTS["browser_timezone"]
    browser_viewport_width: int = DEFAULTS["browser_viewport_width"]
    browser_viewport_height: int = DEFAULTS["browser_viewport_height"]
    browser_allowed_domains: tuple[str, ...] = tuple(DEFAULTS["browser_allowed_domains"])
    browser_pacing_wait_jitter_ms: tuple[int, int] = tuple(
        DEFAULTS["browser_pacing_wait_jitter_ms"]
    )
    browser_pacing_think_time_range_s: tuple[float, float] = tuple(
        DEFAULTS["browser_pacing_think_time_range_s"]
    )
    browser_session_backups_enabled: bool = DEFAULTS["browser_session_backups_enabled"]
    browser_session_backups_retention: int = DEFAULTS["browser_session_backups_retention"]
    search_ready_retry_attempts: int = DEFAULTS["search_ready_retry_attempts"]
    search_ready_backoff_seconds: float = DEFAULTS["search_ready_backoff_seconds"]
    search_ready_selector_override: str | None = DEFAULTS["search_ready_selector_override"]
    search_ready_min_cards: int = DEFAULTS["search_ready_min_cards"]
    quick_apply_selector_override: str | None = DEFAULTS["quick_apply_selector_override"]
    plan_browser_discovery: bool = False
    plan_programmable_search: bool = False
    plan_google_cse_key: str | None = None
    plan_google_cse_cx: str | None = None
    plan_model: str | None = DEFAULTS["plan"]["model"]
    plan_llm_enabled: bool = DEFAULTS["plan"]["llm_enabled"]
    # Derived/env
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str | None = None
    answer_policies_enabled: bool = DEFAULTS["automation"]["answerPolicies"]["enabled"]
    answer_policies_min_confidence: float = DEFAULTS["automation"]["answerPolicies"]["minConfidence"]
    answer_policies_allow_save_to_profile: bool = DEFAULTS["automation"]["answerPolicies"]["allowSaveToProfile"]
    answer_policies_allow_llm_fallback: bool = DEFAULTS["automation"]["answerPolicies"]["allowLLMFallback"]
    answer_policies_model: str = DEFAULTS["automation"]["answerPolicies"]["model"]

    @classmethod
    def load(
        cls, *, base: Path | None = None, overrides: Dict[str, Any] | None = None
    ) -> "Settings":
        """Load settings from all sources with defined precedence.

        The loading order is:
        1. Hardcoded DEFAULTS.
        2. Global `config.yaml` file.
        3. `.env.local` file and JAA_* overrides.
        4. `overrides` dictionary (typically from CLI flags).

        Args:
            base (Path | None): The base directory. If None, uses the project root.
            overrides (dict | None): A dictionary of settings to apply last,
                taking highest precedence.

        Returns:
            Settings: An instance of the Settings class.
        """
        base = base or get_base_dir()
        ensure_runtime_dirs(base)
        # global defaults
        data: Dict[str, Any] = dict(DEFAULTS)
        # global file
        cfg = config_path(base)
        if cfg.exists():
            try:
                data.update(yaml.safe_load(cfg.read_text(encoding="utf-8")) or {})
            except yaml.YAMLError as e:
                # If corrupted, fall back to defaults but do not crash
                log_event({
                    "level": "error",
                    "message": f"Config file at {cfg} is corrupted. Using defaults.",
                    "event": "config.corrupted",
                    "error": str(e),
                })
        # env
        env = load_env(base)
        data.update({k: v for k, v in env.items() if v is not None})
        if marker_profile := load_active_profile(base):
            data["active_profile"] = marker_profile
        plan_dict = data.pop("plan", {}) or {}

        def _assign_plan_option(target: Dict[str, Any], key: str, value: Any) -> None:
            if value is None:
                return
            if key == "browser_discovery":
                target["plan_browser_discovery"] = _to_bool(value)
            elif key == "programmable_search":
                target["plan_programmable_search"] = _to_bool(value)
            elif key == "google_cse_key":
                target["plan_google_cse_key"] = str(value)
            elif key == "google_cse_cx":
                target["plan_google_cse_cx"] = str(value)
            elif key == "model":
                target["plan_model"] = str(value)
            elif key in {"llm_enabled", "llm"}:
                target["plan_llm_enabled"] = _to_bool(value)

        if isinstance(plan_dict, dict):
            for key, value in plan_dict.items():
                _assign_plan_option(data, str(key), value)
        for dotted_key in [key for key in list(data.keys()) if key.startswith("plan.")]:
            _, subkey = dotted_key.split(".", 1)
            _assign_plan_option(data, subkey, data.pop(dotted_key))
        if "plan_browser_discovery" in data:
            _assign_plan_option(data, "browser_discovery", data.pop("plan_browser_discovery"))
        if "plan_programmable_search" in data:
            _assign_plan_option(data, "programmable_search", data.pop("plan_programmable_search"))
        if "plan_google_cse_key" in data:
            _assign_plan_option(data, "google_cse_key", data.pop("plan_google_cse_key"))
        if "plan_google_cse_cx" in data:
            _assign_plan_option(data, "google_cse_cx", data.pop("plan_google_cse_cx"))
        if "plan_model" in data and data["plan_model"] is not None:
            data["plan_model"] = str(data["plan_model"])
        if "plan_llm_enabled" in data and data["plan_llm_enabled"] is not None:
            data["plan_llm_enabled"] = _to_bool(data["plan_llm_enabled"])
        automation_dict = data.pop("automation", {}) or {}

        def _assign_answer_policy(target: Dict[str, Any], key: str, value: Any) -> None:
            if value is None:
                return
            if key == "enabled":
                target["answer_policies_enabled"] = _to_bool(value)
            elif key == "minConfidence":
                target["answer_policies_min_confidence"] = float(value)
            elif key == "allowSaveToProfile":
                target["answer_policies_allow_save_to_profile"] = _to_bool(value)
            elif key == "allowLLMFallback":
                target["answer_policies_allow_llm_fallback"] = _to_bool(value)
            elif key == "model":
                target["answer_policies_model"] = str(value)

        if isinstance(automation_dict, dict):
            answer_dict = automation_dict.get("answerPolicies") or {}
            if isinstance(answer_dict, dict):
                for key, value in answer_dict.items():
                    _assign_answer_policy(data, str(key), value)
        for dotted_key in [
            key for key in list(data.keys()) if key.startswith("automation.answerPolicies.")
        ]:
            _, subkey = dotted_key.split("answerPolicies.", 1)
            _assign_answer_policy(data, subkey, data.pop(dotted_key))
        # Allow nested browser config in YAML/env overrides (browser.* keys)
        browser_dict = data.pop("browser", {}) or {}
        if isinstance(browser_dict, dict):
            if "model" in browser_dict and browser_dict["model"]:
                data["browser_model"] = browser_dict["model"]
            if "locale" in browser_dict and browser_dict["locale"]:
                data["browser_locale"] = browser_dict["locale"]
            if "timezone" in browser_dict and browser_dict["timezone"]:
                data["browser_timezone"] = browser_dict["timezone"]
            viewport = browser_dict.get("viewport")
            if isinstance(viewport, dict):
                width = viewport.get("width")
                height = viewport.get("height")
                if isinstance(width, int) and width > 0:
                    data["browser_viewport_width"] = width
                if isinstance(height, int) and height > 0:
                    data["browser_viewport_height"] = height
            if browser_dict.get("chrome_path"):
                data["chrome_path"] = browser_dict["chrome_path"]
            allowed = browser_dict.get("allowed_domains")
            if isinstance(allowed, (list, tuple, set)):
                domains = [str(item).strip() for item in allowed if str(item).strip()]
                if domains:
                    data["browser_allowed_domains"] = domains
            pacing = browser_dict.get("pacing")
            if isinstance(pacing, dict):
                wait = pacing.get("wait_jitter_ms")
                if isinstance(wait, (list, tuple)) and len(wait) == 2:
                    data["browser_pacing_wait_jitter_ms"] = [int(wait[0]), int(wait[1])]
                think = pacing.get("think_time_range_s")
                if isinstance(think, (list, tuple)) and len(think) == 2:
                    data["browser_pacing_think_time_range_s"] = [
                        float(think[0]),
                        float(think[1]),
                    ]
        backups_dict = data.pop("browser_session_backups", {}) or {}
        if isinstance(backups_dict, dict):
            if backups_dict.get("enabled") is not None:
                data["browser_session_backups_enabled"] = _to_bool(
                    backups_dict["enabled"]
                )
            if backups_dict.get("retention") is not None:
                try:
                    data["browser_session_backups_retention"] = int(
                        backups_dict["retention"]
                    )
                except (TypeError, ValueError):
                    pass
        # CLI overrides last
        if overrides:
            processed: Dict[str, Any] = {}
            for key, value in overrides.items():
                if value is None:
                    continue
                if key.startswith("browser."):
                    _, subkey = key.split(".", 1)
                    if subkey == "model":
                        processed["browser_model"] = value
                    elif subkey == "locale":
                        processed["browser_locale"] = value
                    elif subkey == "timezone":
                        processed["browser_timezone"] = value
                    elif subkey == "viewport_width":
                        processed["browser_viewport_width"] = int(value)
                    elif subkey == "viewport_height":
                        processed["browser_viewport_height"] = int(value)
                    elif subkey == "chrome_path":
                        processed["chrome_path"] = value
                    elif subkey == "allowed_domains":
                        if isinstance(value, str):
                            domains = [item.strip() for item in value.split(",") if item.strip()]
                        else:
                            domains = list(value) if isinstance(value, (list, tuple, set)) else []
                        if domains:
                            processed["browser_allowed_domains"] = domains
                    elif subkey == "pacing.wait_jitter_ms":
                        if isinstance(value, str):
                            parts = [float(part) for part in value.split(",") if part.strip()]
                        else:
                            parts = list(value) if isinstance(value, (list, tuple)) else []
                        if len(parts) == 2:
                            processed["browser_pacing_wait_jitter_ms"] = [int(parts[0]), int(parts[1])]
                    elif subkey == "pacing.think_time_range_s":
                        if isinstance(value, str):
                            parts = [float(part) for part in value.split(",") if part.strip()]
                        else:
                            parts = list(value) if isinstance(value, (list, tuple)) else []
                        if len(parts) == 2:
                            processed["browser_pacing_think_time_range_s"] = [
                                float(parts[0]),
                                float(parts[1]),
                            ]
                elif key.startswith("search_ready."):
                    _, subkey = key.split(".", 1)
                    if subkey == "retry_attempts":
                        processed["search_ready_retry_attempts"] = int(value)
                    elif subkey == "backoff_seconds":
                        processed["search_ready_backoff_seconds"] = float(value)
                    elif subkey == "selector_override":
                        processed["search_ready_selector_override"] = str(value)
                    elif subkey == "min_cards":
                        processed["search_ready_min_cards"] = int(value)
                elif key.startswith("quick_apply."):
                    _, subkey = key.split(".", 1)
                    if subkey == "selector_override":
                        processed["quick_apply_selector_override"] = str(value)
                elif key.startswith("browser_session_backups."):
                    _, subkey = key.split(".", 1)
                    if subkey == "enabled":
                        processed["browser_session_backups_enabled"] = _to_bool(value)
                    elif subkey == "retention":
                        processed["browser_session_backups_retention"] = int(value)
                elif key.startswith("automation.answerPolicies."):
                    _, subkey = key.split("answerPolicies.", 1)
                    _assign_answer_policy(processed, subkey, value)
                elif key.startswith("plan."):
                    _, subkey = key.split(".", 1)
                    _assign_plan_option(processed, subkey, value)
                else:
                    processed[key] = value
            data.update(processed)
        search_ready_dict = data.pop("search_ready", {}) or {}
        if isinstance(search_ready_dict, dict):
            if "retry_attempts" in search_ready_dict and search_ready_dict["retry_attempts"] is not None:
                data["search_ready_retry_attempts"] = int(search_ready_dict["retry_attempts"])
            if "backoff_seconds" in search_ready_dict and search_ready_dict["backoff_seconds"] is not None:
                data["search_ready_backoff_seconds"] = float(search_ready_dict["backoff_seconds"])
            if "selector_override" in search_ready_dict and search_ready_dict["selector_override"]:
                data["search_ready_selector_override"] = str(search_ready_dict["selector_override"])
            if "min_cards" in search_ready_dict and search_ready_dict["min_cards"] is not None:
                data["search_ready_min_cards"] = int(search_ready_dict["min_cards"])
        quick_apply_dict = data.pop("quick_apply", {}) or {}
        if isinstance(quick_apply_dict, dict):
            override = quick_apply_dict.get("selector_override")
            if override:
                data["quick_apply_selector_override"] = str(override)
        if "browser_allowed_domains" in data:
            domains = data["browser_allowed_domains"]
            data["browser_allowed_domains"] = tuple(str(item).strip() for item in domains if str(item).strip())
        if "browser_pacing_wait_jitter_ms" in data:
            wait = data["browser_pacing_wait_jitter_ms"]
            data["browser_pacing_wait_jitter_ms"] = (int(wait[0]), int(wait[1]))
        if "browser_pacing_think_time_range_s" in data:
            think = data["browser_pacing_think_time_range_s"]
            data["browser_pacing_think_time_range_s"] = (float(think[0]), float(think[1]))
        data["search_ready_retry_attempts"] = int(data.get("search_ready_retry_attempts", DEFAULTS["search_ready_retry_attempts"]))
        data["search_ready_backoff_seconds"] = float(
            data.get("search_ready_backoff_seconds", DEFAULTS["search_ready_backoff_seconds"])
        )
        if data.get("search_ready_selector_override"):
            data["search_ready_selector_override"] = str(data["search_ready_selector_override"])
        else:
            data["search_ready_selector_override"] = None
        if data.get("quick_apply_selector_override"):
            data["quick_apply_selector_override"] = str(
                data["quick_apply_selector_override"]
            )
        else:
            data["quick_apply_selector_override"] = None
        data["search_ready_min_cards"] = int(
            data.get("search_ready_min_cards", DEFAULTS["search_ready_min_cards"])
        )
        data["browser_session_backups_enabled"] = _to_bool(
            data.get(
                "browser_session_backups_enabled",
                DEFAULTS["browser_session_backups_enabled"],
            )
        )
        data["browser_session_backups_retention"] = max(
            1,
            int(
                data.get(
                    "browser_session_backups_retention",
                    DEFAULTS["browser_session_backups_retention"],
                )
            ),
        )
        data["plan_browser_discovery"] = _to_bool(
            data.get("plan_browser_discovery", False)
        )
        data["plan_programmable_search"] = _to_bool(
            data.get("plan_programmable_search", False)
        )
        if data.get("plan_google_cse_key"):
            key_value = str(data["plan_google_cse_key"]).strip()
            data["plan_google_cse_key"] = key_value or None
        else:
            data["plan_google_cse_key"] = None
        if data.get("plan_google_cse_cx"):
            cx_value = str(data["plan_google_cse_cx"]).strip()
            data["plan_google_cse_cx"] = cx_value or None
        else:
            data["plan_google_cse_cx"] = None
        return cls(**data)

    def base_answer_policy(self):
        """Return the base AnswerPolicy derived from settings."""

        from core.answers import AnswerPolicy as _AnswerPolicy

        model = self.answer_policies_model or self.browser_model
        return _AnswerPolicy(
            enabled=bool(self.answer_policies_enabled),
            min_confidence=float(self.answer_policies_min_confidence),
            allow_save_to_profile=bool(self.answer_policies_allow_save_to_profile),
            allow_llm_fallback=bool(self.answer_policies_allow_llm_fallback),
            model=str(model),
        )

    def to_json(self) -> str:
        """Serialize the settings object to a JSON string.

        Returns:
            str: A JSON representation of the settings.
        """
        return json.dumps(asdict(self), ensure_ascii=False)
