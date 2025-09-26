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
    "active_profile": None,
    "dry_run": False,
    "preview_port": 4950,
    "chrome_path": None,
}


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
        base / ".local",
        base / "runs",
        base / "history",
    ]
    for d in required:
        d.mkdir(parents=True, exist_ok=True)
    return {"created": "ok", "base": str(base)}


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
            "# Edit values as needed.\n"
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
    active_profile: str | None = DEFAULTS["active_profile"]
    dry_run: bool = DEFAULTS["dry_run"]
    preview_port: int = DEFAULTS["preview_port"]
    chrome_path: str | None = DEFAULTS["chrome_path"]
    # Derived/env
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str | None = None

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
        # CLI overrides last
        if overrides:
            data.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**data)

    def to_json(self) -> str:
        """Serialize the settings object to a JSON string.

        Returns:
            str: A JSON representation of the settings.
        """
        return json.dumps(asdict(self), ensure_ascii=False)
