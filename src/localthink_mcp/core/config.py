"""
LocalThink config persistence.

Config file: ~/.localthink-mcp/config.json
Priority:    config file  >  env vars  >  built-in defaults

Call load_config() once at server startup to apply saved settings to os.environ
before ollama_client / cache modules read them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR  = Path(os.environ.get("LOCALTHINK_MEMO_DIR", "") or Path.home() / ".localthink-mcp")
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "ollama_base_url":    "http://localhost:11434",
    "ollama_model":       "qwen2.5:14b-instruct-q4_K_M",
    "ollama_fast_model":  "",
    "ollama_tiny_model":  "",
    "cache_dir":          "",
    "cache_ttl_days":     30,
    "memo_dir":           "",
}

# Maps config key → env var name
_ENV_MAP: dict[str, str] = {
    "ollama_base_url":   "OLLAMA_BASE_URL",
    "ollama_model":      "OLLAMA_MODEL",
    "ollama_fast_model": "OLLAMA_FAST_MODEL",
    "ollama_tiny_model": "OLLAMA_TINY_MODEL",
    "cache_dir":         "LOCALTHINK_CACHE_DIR",
    "cache_ttl_days":    "LOCALTHINK_CACHE_TTL_DAYS",
    "memo_dir":          "LOCALTHINK_MEMO_DIR",
}


def read() -> dict[str, Any]:
    """Return saved config merged with defaults. Never raises."""
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    except Exception:
        pass
    return dict(DEFAULTS)


def write(settings: dict[str, Any]) -> None:
    """Persist settings to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: settings.get(k, DEFAULTS[k]) for k in DEFAULTS}
    CONFIG_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")


def load_config() -> None:
    """Apply saved config to os.environ. Call once at server startup."""
    cfg = read()
    for key, env_var in _ENV_MAP.items():
        val = cfg.get(key)
        if val and str(val).strip():
            os.environ.setdefault(env_var, str(val))


def apply_config(settings: dict[str, Any]) -> None:
    """Write settings and immediately update os.environ for the running process."""
    write(settings)
    for key, env_var in _ENV_MAP.items():
        val = settings.get(key)
        if val and str(val).strip():
            os.environ[env_var] = str(val)
        else:
            os.environ.pop(env_var, None)


def current_as_dict() -> dict[str, Any]:
    """Live snapshot: config file merged with env vars (env wins)."""
    cfg = read()
    for key, env_var in _ENV_MAP.items():
        env_val = os.environ.get(env_var, "")
        if env_val:
            cfg[key] = int(env_val) if key == "cache_ttl_days" else env_val
    return cfg
