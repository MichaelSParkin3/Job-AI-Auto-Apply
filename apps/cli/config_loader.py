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
}


def get_base_dir() -> Path:
    return Path(os.environ.get("JAA_BASE_DIR", ".")).resolve()


def ensure_runtime_dirs(base: Path | None = None) -> Dict[str, str]:
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
    return {
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY"),
        "OPENROUTER_MODEL": os.environ.get("OPENROUTER_MODEL"),
    }


def config_path(base: Path | None = None) -> Path:
    base = base or get_base_dir()
    return base / "config" / "config.yaml"


def write_default_config(base: Path | None = None) -> Path:
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
    log_level: str = DEFAULTS["log_level"]
    artifacts_keep_days: int = DEFAULTS["artifacts_keep_days"]
    active_profile: str | None = DEFAULTS["active_profile"]
    # Derived/env
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str | None = None

    @classmethod
    def load(
        cls, *, base: Path | None = None, overrides: Dict[str, Any] | None = None
    ) -> "Settings":
        base = base or get_base_dir()
        ensure_runtime_dirs(base)
        # global defaults
        data: Dict[str, Any] = dict(DEFAULTS)
        # global file
        cfg = config_path(base)
        if cfg.exists():
            try:
                data.update(yaml.safe_load(cfg.read_text(encoding="utf-8")) or {})
            except Exception:
                # If corrupted, fall back to defaults but do not crash
                pass
        # env
        env = load_env(base)
        data.update({k: v for k, v in env.items() if v})
        # CLI overrides last
        if overrides:
            data.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
