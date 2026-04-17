"""Disk-backed sha256 result cache for localthink-mcp tools.

Cache keys are sha256 over canonical JSON of (tool_name, inputs_dict).
File-based tools include the file's mtime so the entry auto-invalidates
when the source file changes.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable

CACHE_DIR     = Path(os.environ.get("LOCALTHINK_CACHE_DIR", "") or (Path.home() / ".cache" / "localthink-mcp"))
CACHE_TTL_DAYS = int(os.environ.get("LOCALTHINK_CACHE_TTL_DAYS", "30"))


def reload_env() -> None:
    """Re-read cache env vars into module globals. Called by config.apply_config()."""
    global CACHE_DIR, CACHE_TTL_DAYS
    CACHE_DIR      = Path(os.environ.get("LOCALTHINK_CACHE_DIR", "") or (Path.home() / ".cache" / "localthink-mcp"))
    CACHE_TTL_DAYS = int(os.environ.get("LOCALTHINK_CACHE_TTL_DAYS", "30"))


def cache_key(tool_name: str, inputs: dict) -> str:
    raw = json.dumps({"_t": tool_name, **inputs}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _entry_path(key: str) -> Path:
    return CACHE_DIR / key[:2] / f"{key}.json"


def get(key: str) -> str | None:
    path = _entry_path(key)
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - entry["ts"] > CACHE_TTL_DAYS * 86400:
            path.unlink(missing_ok=True)
            return None
        return entry["v"]
    except Exception:
        return None


def put(key: str, value: str) -> None:
    path = _entry_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(
            json.dumps({"ts": time.time(), "v": value}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def get_or_compute(tool_name: str, inputs: dict, compute_fn: Callable[[], str]) -> str:
    key = cache_key(tool_name, inputs)
    cached = get(key)
    if cached is not None:
        return cached
    result = compute_fn()
    put(key, result)
    return result


def file_inputs(file_path: str, **extras) -> dict:
    """Build cache inputs for file-based tools; mtime ensures auto-invalidation on change."""
    try:
        mtime = round(os.path.getmtime(file_path), 3)
    except OSError:
        mtime = 0.0
    return {"fp": file_path, "mt": mtime, **extras}


def text_inputs(text: str, **extras) -> dict:
    """Build cache inputs for text-based tools; hashes text to keep the key compact."""
    h = hashlib.sha256(text.encode()).hexdigest()[:20]
    return {"th": h, **extras}


def stats() -> dict:
    if not CACHE_DIR.exists():
        return {"entries": 0, "size_bytes": 0, "cache_dir": str(CACHE_DIR)}
    paths = list(CACHE_DIR.glob("**/*.json"))
    total = sum(p.stat().st_size for p in paths if p.exists())
    return {"entries": len(paths), "size_bytes": total, "cache_dir": str(CACHE_DIR)}


def clear(older_than_days: int = 0) -> int:
    """Remove cache entries. older_than_days=0 clears everything."""
    if not CACHE_DIR.exists():
        return 0
    cutoff = time.time() - older_than_days * 86400
    removed = 0
    for path in CACHE_DIR.glob("**/*.json"):
        try:
            if older_than_days == 0 or path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except Exception:
            pass
    return removed
