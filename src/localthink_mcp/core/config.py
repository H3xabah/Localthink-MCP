"""
LocalThink config persistence.

Config file: ~/.localthink-mcp/config.json  (FIXED path — never env-dependent)
Priority:    config file  >  env vars  >  built-in defaults

Call load_config() once at server startup (before all other imports that read
env vars). Call apply_config(settings) to write + immediately hot-reload every
module that caches env vars at import time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Fixed location — never changes regardless of env vars
CONFIG_DIR  = Path.home() / ".localthink-mcp"
CONFIG_FILE = CONFIG_DIR / "config.json"

# ── Full settings schema ───────────────────────────────────────────────────────
# Each entry: key → {env, default, type, label, section, hint}
SCHEMA: dict[str, dict] = {
    # Ollama
    "ollama_base_url":          {"env": "OLLAMA_BASE_URL",                    "default": "http://localhost:11434",       "type": "str",  "label": "Base URL",                  "section": "Ollama",    "hint": "Ollama server endpoint"},
    "ollama_model":              {"env": "OLLAMA_MODEL",                       "default": "qwen2.5:14b-instruct-q4_K_M", "type": "str",  "label": "Default model",             "section": "Ollama",    "hint": "Main model — quality operations"},
    "ollama_fast_model":         {"env": "OLLAMA_FAST_MODEL",                  "default": "",                            "type": "str",  "label": "Fast model",                "section": "Ollama",    "hint": "Lightweight ops (classify, outline). Blank = same as default"},
    "ollama_tiny_model":         {"env": "OLLAMA_TINY_MODEL",                  "default": "",                            "type": "str",  "label": "Tiny model",                "section": "Ollama",    "hint": "Ultra-fast tier. Blank = same as fast"},
    # Timeouts
    "timeout_generate":          {"env": "LOCALTHINK_TIMEOUT",                 "default": 360,                           "type": "int",  "label": "Main timeout (s)",          "section": "Timeouts",  "hint": "Timeout for quality generate calls"},
    "timeout_fast":              {"env": "LOCALTHINK_FAST_TIMEOUT",            "default": 180,                           "type": "int",  "label": "Fast timeout (s)",          "section": "Timeouts",  "hint": "Timeout for fast model calls"},
    "timeout_tiny":              {"env": "LOCALTHINK_TINY_TIMEOUT",            "default": 60,                            "type": "int",  "label": "Tiny timeout (s)",          "section": "Timeouts",  "hint": "Timeout for tiny model calls"},
    "timeout_health":            {"env": "LOCALTHINK_HEALTH_TIMEOUT",          "default": 2,                             "type": "int",  "label": "Health check (s)",          "section": "Timeouts",  "hint": "Timeout for Ollama reachability probe"},
    "timeout_code_surface":      {"env": "LOCALTHINK_CODE_SURFACE_TIMEOUT",    "default": 600,                           "type": "int",  "label": "code_surface timeout (s)",  "section": "Timeouts",  "hint": "Timeout for code_surface on large files"},
    # Limits
    "max_file_bytes":            {"env": "LOCALTHINK_MAX_FILE_BYTES",          "default": 200000,                        "type": "int",  "label": "Max file size (bytes)",     "section": "Limits",    "hint": "Files larger than this are truncated before processing"},
    "max_pipeline_steps":        {"env": "LOCALTHINK_MAX_PIPELINE_STEPS",      "default": 5,                             "type": "int",  "label": "Max pipeline steps",        "section": "Limits",    "hint": "Maximum steps allowed in local_pipeline"},
    "max_scan_files":            {"env": "LOCALTHINK_MAX_SCAN_FILES",          "default": 20,                            "type": "int",  "label": "Max scan files",            "section": "Limits",    "hint": "Maximum files processed per local_scan_dir call"},
    "classify_sample":           {"env": "LOCALTHINK_CLASSIFY_SAMPLE",         "default": 8000,                          "type": "int",  "label": "Classify sample (chars)",   "section": "Limits",    "hint": "Characters sampled for local_classify"},
    "max_concurrency":           {"env": "LOCALTHINK_MAX_CONCURRENCY",         "default": 4,                             "type": "int",  "label": "Batch concurrency",         "section": "Limits",    "hint": "Parallel workers for local_batch_answer and local_scan_dir"},
    # Cache
    "cache_dir":                 {"env": "LOCALTHINK_CACHE_DIR",               "default": "",                            "type": "dir",  "label": "Cache directory",           "section": "Cache",     "hint": "Blank = ~/.cache/localthink-mcp"},
    "cache_ttl_days":            {"env": "LOCALTHINK_CACHE_TTL_DAYS",          "default": 30,                            "type": "int",  "label": "Cache TTL (days)",          "section": "Cache",     "hint": "How long cache entries live before expiry"},
    # Memo / Notes
    "memo_dir":                  {"env": "LOCALTHINK_MEMO_DIR",                "default": "",                            "type": "dir",  "label": "Memo directory",            "section": "Memo",      "hint": "Blank = ~/.localthink-mcp"},
    "memo_compact_threshold":    {"env": "LOCALTHINK_COMPACT_THRESHOLD",       "default": 3000,                          "type": "int",  "label": "Compact threshold (chars)", "section": "Memo",      "hint": "Auto-compact a scratchpad section when it exceeds this size"},
}

SECTIONS = ["Ollama", "Timeouts", "Limits", "Cache", "Memo"]


def _defaults() -> dict[str, Any]:
    return {k: v["default"] for k, v in SCHEMA.items()}


def read() -> dict[str, Any]:
    """Return saved config merged over defaults. Never raises."""
    base = _defaults()
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in data.items():
                if k in SCHEMA:
                    base[k] = v
    except Exception:
        pass
    return base


def write(settings: dict[str, Any]) -> None:
    """Persist settings dict to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    clean: dict[str, Any] = {}
    for k, meta in SCHEMA.items():
        val = settings.get(k, meta["default"])
        if meta["type"] == "int":
            try:
                val = int(val)
            except (TypeError, ValueError):
                val = meta["default"]
        else:
            val = str(val) if val is not None else ""
        clean[k] = val
    CONFIG_FILE.write_text(json.dumps(clean, indent=2), encoding="utf-8")


def _set_env(settings: dict[str, Any]) -> None:
    """Apply settings dict to os.environ."""
    for k, meta in SCHEMA.items():
        val = settings.get(k, meta["default"])
        env_var = meta["env"]
        str_val = str(val) if val is not None else ""
        if str_val.strip():
            os.environ[env_var] = str_val
        else:
            os.environ.pop(env_var, None)


def load_config() -> None:
    """Apply saved config to os.environ. Call once at server startup."""
    _set_env(read())


def apply_config(settings: dict[str, Any]) -> None:
    """Write settings, apply to os.environ, and hot-reload all cached module globals."""
    write(settings)
    _set_env(settings)
    _hot_reload()


def _hot_reload() -> None:
    """Tell each module that cached env vars at import time to re-read them."""
    import sys
    mods = [
        "ollama_client",
        "core.cache",
        "core.memo",
        "core.async_batch",
        "core.router",
    ]
    for name in mods:
        mod = sys.modules.get(name)
        if mod and hasattr(mod, "reload_env"):
            try:
                mod.reload_env()
            except Exception:
                pass
    # server.py constants
    srv = sys.modules.get("server") or sys.modules.get("localthink_mcp.server")
    if srv and hasattr(srv, "reload_env"):
        try:
            srv.reload_env()
        except Exception:
            pass


def current_as_dict() -> dict[str, Any]:
    """Live snapshot: saved config merged with active env vars (env wins)."""
    cfg = read()
    for k, meta in SCHEMA.items():
        env_val = os.environ.get(meta["env"], "")
        if env_val:
            if meta["type"] == "int":
                try:
                    cfg[k] = int(env_val)
                except (TypeError, ValueError):
                    pass
            else:
                cfg[k] = env_val
    return cfg
