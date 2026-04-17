"""Model tier selection: routes tasks to tiny / fast / main based on task type and input size.

Tiers (from cheapest to most capable):
  tiny  — OLLAMA_TINY_MODEL  (falls back to fast if unset)
  fast  — OLLAMA_FAST_MODEL  (falls back to main if unset)
  main  — OLLAMA_MODEL       (always set)

Routing rules:
  main   — quality-critical tasks regardless of input size
  tiny   — classification / structure tasks with small inputs
  fast   — everything else
"""
from __future__ import annotations

import os

_MAIN = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")
_FAST = os.environ.get("OLLAMA_FAST_MODEL", "") or _MAIN
_TINY = os.environ.get("OLLAMA_TINY_MODEL", "") or _FAST


def reload_env() -> None:
    """Re-read model env vars. Called by config.apply_config() after GUI save."""
    global _MAIN, _FAST, _TINY
    _MAIN = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")
    _FAST = os.environ.get("OLLAMA_FAST_MODEL", "") or _MAIN
    _TINY = os.environ.get("OLLAMA_TINY_MODEL", "") or _FAST

# Tasks that must always use the full model
_MAIN_TASKS = frozenset({
    "summarize", "shrink_file", "extract", "answer",
    "compress_log", "compress_stack_trace", "compress_data",
    "session_compress", "prompt_compress",
    "find_impl", "audit", "preplan", "improve_prompt",
    "diff", "diff_files", "strip_to_skeleton", "diff_semantic",
    "chat", "auto", "pipeline", "grep_semantic", "refine",
    "batch_answer",  # individual answers in batch use main
})

# Tasks eligible for tiny when input is short
_TINY_ELIGIBLE = frozenset({
    "classify", "symbols", "outline", "timeline",
    "schema_infer", "code_surface", "translate", "gate",
})

_TINY_THRESHOLD = 2_000  # chars


def pick_model(task: str, input_len: int = 0) -> str:
    """Return the Ollama model string appropriate for this task and input length."""
    if task in _MAIN_TASKS:
        return _MAIN
    if task in _TINY_ELIGIBLE and input_len < _TINY_THRESHOLD:
        return _TINY
    return _FAST


def tiny() -> str:
    return _TINY


def fast() -> str:
    return _FAST


def main() -> str:
    return _MAIN


def all_models() -> dict[str, str]:
    return {"main": _MAIN, "fast": _FAST, "tiny": _TINY}
