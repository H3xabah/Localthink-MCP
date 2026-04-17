#!/usr/bin/env python3
"""
localthink-mcp v2.1.0 — Local Ollama-backed MCP server for Claude Code.

New in v2.1:
  - Smart buffer: local_gate (Phase 1 summary) + local_slice (raw window on demand)
  - Semantic diff: local_diff_semantic — meaning changes only, noise suppressed
  - Execution filters: local_run_tests, local_run_lint, local_run_build
  - Session scratchpad: local_memo_write/read/checkpoint (CONTEXT.md, auto-compacted)
  - Permanent model notes: local_note_write/search (cross-session, never cleared)
  - Extended code_surface timeout: configurable via LOCALTHINK_CODE_SURFACE_TIMEOUT

Tools (45 total):
  Core Q&A / compression:
    local_summarize, local_extract, local_answer, local_shrink_file
    local_diff, local_diff_files, local_batch_answer
  Multi-step:
    local_pipeline, local_auto, local_chat
  Code intelligence:
    local_code_surface, local_symbols, local_find_impl, local_strip_to_skeleton
    local_grep_semantic
  Document analysis:
    local_classify, local_outline, local_audit, local_timeline, local_schema_infer
    local_translate, local_scan_dir
  Compression:
    local_compress_log, local_compress_stack_trace, local_compress_data
    local_session_compress, local_prompt_compress
  Pre-injection (run before Claude):
    local_improve_prompt, local_preplan, local_refine
  Smart Buffer (v2.1):
    local_gate, local_slice, local_diff_semantic
  Execution Filters (v2.1):
    local_run_tests, local_run_lint, local_run_build
  Scratchpad (v2.1):
    local_memo_write, local_memo_read, local_memo_checkpoint
  Model Notes (v2.1):
    local_note_write, local_note_search
  Cache management:
    local_models, local_cache_stats, local_cache_clear
  Settings:
    local_config
"""
import sys
import os
import re
import json
import glob as _glob
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

# Apply saved config to os.environ before any module reads env vars.
from core.config import load_config, current_as_dict as _current_cfg
load_config()

from mcp.server.fastmcp import FastMCP
from ollama_client import (
    generate, generate_fast, generate_tiny, generate_json,
    health_check, list_models,
    DEFAULT_MODEL, FAST_MODEL, TINY_MODEL,
)
from prompts import (
    SUMMARIZE_SYSTEM, EXTRACT_SYSTEM, ANSWER_SYSTEM, DIFF_SYSTEM,
    CHAT_SYSTEM, AUTO_SYSTEM, SEMANTIC_GREP_SYSTEM, SCAN_DIR_SYSTEM,
    CODE_SURFACE_SYSTEM, OUTLINE_SYSTEM, AUDIT_SYSTEM, CLASSIFY_SYSTEM,
    LOG_COMPRESS_SYSTEM, STACK_TRACE_SYSTEM, DATA_COMPRESS_SYSTEM,
    SESSION_COMPRESS_SYSTEM, PROMPT_COMPRESS_SYSTEM, SYMBOLS_SYSTEM,
    FIND_IMPL_SYSTEM, SKELETON_SYSTEM, TRANSLATE_SYSTEM, SCHEMA_INFER_SYSTEM,
    TIMELINE_SYSTEM, IMPROVE_PROMPT_SYSTEM, PREPLAN_SYSTEM,
    REFINE_SYSTEM,
    MEMO_COMPACT_SYSTEM, GATE_SUMMARY_SYSTEM, DIFF_SEMANTIC_SYSTEM,
)
from code_surface import extract_python_surface
import core.cache as cache
import core.router as router
import core.memo as memo_store
from core.async_batch import run_batch
from core.passes import run_passes
import core.structured as structured

mcp = FastMCP("localthink")

_UNAVAILABLE = "[localthink] Ollama is not running. Start it with: ollama serve"
_MAX_FILE_BYTES     = int(os.environ.get("LOCALTHINK_MAX_FILE_BYTES",     "200000"))
_MAX_PIPELINE_STEPS = int(os.environ.get("LOCALTHINK_MAX_PIPELINE_STEPS", "5"))
_MAX_SCAN_FILES     = int(os.environ.get("LOCALTHINK_MAX_SCAN_FILES",     "20"))
_CLASSIFY_SAMPLE    = int(os.environ.get("LOCALTHINK_CLASSIFY_SAMPLE",    "8000"))


def reload_env() -> None:
    """Re-read server-level constants from env. Called by config.apply_config()."""
    global _MAX_FILE_BYTES, _MAX_PIPELINE_STEPS, _MAX_SCAN_FILES, _CLASSIFY_SAMPLE
    _MAX_FILE_BYTES     = int(os.environ.get("LOCALTHINK_MAX_FILE_BYTES",     "200000"))
    _MAX_PIPELINE_STEPS = int(os.environ.get("LOCALTHINK_MAX_PIPELINE_STEPS", "5"))
    _MAX_SCAN_FILES     = int(os.environ.get("LOCALTHINK_MAX_SCAN_FILES",     "20"))
    _CLASSIFY_SAMPLE    = int(os.environ.get("LOCALTHINK_CLASSIFY_SAMPLE",    "8000"))


def _read_file(path: str) -> tuple[str, str]:
    """Return (content, error). Content capped at _MAX_FILE_BYTES. Error is '' on success."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(_MAX_FILE_BYTES), ""
    except Exception as e:
        return "", f"[localthink] Cannot read {path}: {e}"


def _number_lines(text: str) -> str:
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(text.splitlines()))


# ── Core Q&A / Compression ────────────────────────────────────────────────────


@mcp.tool()
def local_summarize(text: str, focus: str = "") -> str:
    """Compress a large text block using a local LLM. Preserves API names, signatures,
    error strings, config keys. Optional focus: topic to prioritize."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text, focus=focus)

    def compute():
        prompt = f"Focus on: {focus}\n\n{text}" if focus else text
        return generate(prompt=prompt, system=SUMMARIZE_SYSTEM)

    return cache.get_or_compute("summarize", inputs, compute)


@mcp.tool()
def local_extract(text: str, query: str) -> str:
    """Extract only the passages relevant to a specific query from a large document.
    Returns cited sections, not a paraphrase."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text, q=query)

    def compute():
        prompt = f"Query: {query}\n\nDocument:\n{text}"
        return generate(prompt=prompt, system=EXTRACT_SYSTEM)

    return cache.get_or_compute("extract", inputs, compute)


@mcp.tool()
def local_answer(file_path: str, question: str, passes: int = 1) -> str:
    """Answer a question from a file without loading it into Claude's context.

    passes=1  Single inference call (default).
    passes=2  Fast draft → main-model refinement for higher accuracy.
    passes=3  + a verify step; re-refines if the verifier finds gaps."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    inputs = cache.file_inputs(file_path, q=question, p=passes)

    def compute():
        prompt = f"Question: {question}\n\nDocument:\n{content}"
        return run_passes(prompt=prompt, system=ANSWER_SYSTEM, passes=passes)

    return cache.get_or_compute("answer", inputs, compute)


@mcp.tool()
def local_shrink_file(file_path: str, focus: str = "") -> str:
    """Compress a file to dense text and return it for repeated in-context reference.
    Typically 20-30% of original size."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    inputs = cache.file_inputs(file_path, focus=focus)

    def compute():
        prompt = f"Focus on: {focus}\n\n{content}" if focus else content
        return generate(prompt=prompt, system=SUMMARIZE_SYSTEM)

    return cache.get_or_compute("shrink_file", inputs, compute)


@mcp.tool()
def local_diff(before: str, after: str, focus: str = "") -> str:
    """Summarize meaningful changes between two text blobs (before → after).
    Optional focus: topic to prioritize (e.g. 'auth', 'breaking changes')."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(before + after, focus=focus)

    def compute():
        focus_line = f"Focus on changes related to: {focus}\n\n" if focus else ""
        prompt = f"{focus_line}=== BEFORE ===\n{before}\n\n=== AFTER ===\n{after}"
        return generate(prompt=prompt, system=DIFF_SYSTEM)

    return cache.get_or_compute("diff", inputs, compute)


@mcp.tool()
def local_diff_files(path_a: str, path_b: str, focus: str = "") -> str:
    """Summarize meaningful changes between two files — neither file loaded into context.
    Optional focus: topic to prioritize (e.g. 'security', 'breaking changes')."""
    if not health_check():
        return _UNAVAILABLE
    content_a, err_a = _read_file(path_a)
    if err_a:
        return err_a
    content_b, err_b = _read_file(path_b)
    if err_b:
        return err_b
    try:
        mt_a = round(os.path.getmtime(path_a), 3)
        mt_b = round(os.path.getmtime(path_b), 3)
    except OSError:
        mt_a = mt_b = 0.0
    inputs = {"fp_a": path_a, "mt_a": mt_a, "fp_b": path_b, "mt_b": mt_b, "focus": focus}

    def compute():
        focus_line = f"Focus on changes related to: {focus}\n\n" if focus else ""
        prompt = f"{focus_line}=== {path_a} ===\n{content_a}\n\n=== {path_b} ===\n{content_b}"
        return generate(prompt=prompt, system=DIFF_SYSTEM)

    return cache.get_or_compute("diff_files", inputs, compute)


@mcp.tool()
def local_batch_answer(file_paths: list[str], question: str) -> str:
    """Answer the same question across multiple files concurrently without loading any
    into Claude's context. Files are processed in parallel (LOCALTHINK_MAX_CONCURRENCY=4).

    Ideal for: 'Does this file have hardcoded credentials?', 'What does this export?'"""
    if not health_check():
        return _UNAVAILABLE

    def answer_one(path: str) -> str:
        content, err = _read_file(path)
        if err:
            return f"### {path}\n{err}"
        inputs = cache.file_inputs(path, q=question)

        def compute():
            prompt = f"Question: {question}\n\nDocument:\n{content}"
            return generate(prompt=prompt, system=ANSWER_SYSTEM)

        return f"### {path}\n{cache.get_or_compute('answer', inputs, compute)}"

    results = run_batch([lambda p=path: answer_one(p) for path in file_paths])
    return "\n\n".join(results)


# ── Multi-step tools ───────────────────────────────────────────────────────────


@mcp.tool()
def local_pipeline(text: str, steps: list[dict]) -> str:
    """Chain operations in a single MCP call. Each step's output feeds the next.

    Supported step ops:
      {"op": "summarize", "focus": "<optional topic>"}
      {"op": "extract",   "query": "<what to find>"}
      {"op": "answer",    "question": "<what to ask>"}

    Maximum 5 steps. Example:
      [{"op": "extract", "query": "authentication"}, {"op": "summarize"}]
    """
    if not health_check():
        return _UNAVAILABLE
    current = text
    for i, step in enumerate(steps[:_MAX_PIPELINE_STEPS]):
        op = step.get("op", "")
        if op == "summarize":
            focus = step.get("focus", "")
            prompt = f"Focus on: {focus}\n\n{current}" if focus else current
            current = generate(prompt=prompt, system=SUMMARIZE_SYSTEM)
        elif op == "extract":
            query = step.get("query", "")
            if not query:
                return f"[localthink] pipeline step {i}: 'extract' requires a 'query' key"
            prompt = f"Query: {query}\n\nDocument:\n{current}"
            current = generate(prompt=prompt, system=EXTRACT_SYSTEM)
        elif op == "answer":
            question = step.get("question", "")
            if not question:
                return f"[localthink] pipeline step {i}: 'answer' requires a 'question' key"
            prompt = f"Question: {question}\n\nDocument:\n{current}"
            current = generate(prompt=prompt, system=ANSWER_SYSTEM)
        else:
            return f"[localthink] pipeline step {i}: unknown op '{op}'. Supported: summarize, extract, answer"
    return current


@mcp.tool()
def local_auto(input: str, question: str = "") -> str:
    """Meta-tool: automatically selects the right operation.

    - If input looks like a file path and the file exists: reads it first.
    - question + large doc: extract relevant sections, then answer.
    - question + small doc: answer directly.
    - No question: smart summarize with auto-detected focus."""
    if not health_check():
        return _UNAVAILABLE

    content = input
    if len(input) < 500 and os.path.exists(input):
        content, err = _read_file(input)
        if err:
            return err

    if question:
        if len(content) > 4_000:
            extract_prompt = f"Query: {question}\n\nDocument:\n{content}"
            relevant = generate(prompt=extract_prompt, system=EXTRACT_SYSTEM)
            answer_prompt = f"Question: {question}\n\nRelevant sections:\n{relevant}"
        else:
            answer_prompt = f"Question: {question}\n\nDocument:\n{content}"
        return generate(prompt=answer_prompt, system=ANSWER_SYSTEM)
    return generate(prompt=content, system=AUTO_SYSTEM)


@mcp.tool()
def local_chat(document: str, message: str, history: str = "") -> str:
    """Multi-turn Q&A against a document — document never enters Claude's context.

    On first call (history=""), large documents are compressed automatically.
    Pass result['doc'] back in subsequent turns instead of the original document.

    Returns JSON: {"answer": "...", "history": "...", "doc": "..."}"""
    if not health_check():
        return _UNAVAILABLE

    compressed_doc = document
    note = ""
    if not history and len(document) > 8_000:
        compressed_doc = generate(prompt=document, system=SUMMARIZE_SYSTEM)
        note = "Document was compressed for efficiency. Use result['doc'] in future turns."

    history_block = f"\n\nConversation so far:\n{history}" if history else ""
    prompt = f"Document:\n{compressed_doc}{history_block}\n\nUser: {message}"
    answer = generate(prompt=prompt, system=CHAT_SYSTEM)
    new_history = (f"{history}\nUser: {message}\nAssistant: {answer}").strip()

    result: dict = {"answer": answer, "history": new_history, "doc": compressed_doc}
    if note:
        result["note"] = note
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Code intelligence ─────────────────────────────────────────────────────────


@mcp.tool()
def local_code_surface(file_path: str) -> str:
    """Extract the public API skeleton from a source file.

    Python — pure AST (instant, no Ollama): function/method signatures, class definitions,
    public constants. Other languages — local LLM via fast/tiny model."""
    content, err = _read_file(file_path)
    if err:
        return err

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".py":
        return extract_python_surface(content)

    if not health_check():
        return _UNAVAILABLE

    inputs = cache.file_inputs(file_path)
    lang_map = {
        ".js": "JavaScript", ".jsx": "JavaScript (React)",
        ".ts": "TypeScript", ".tsx": "TypeScript (React)",
        ".go": "Go", ".rs": "Rust", ".java": "Java",
        ".cs": "C#", ".cpp": "C++", ".c": "C",
        ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
        ".kt": "Kotlin", ".scala": "Scala",
    }
    lang = lang_map.get(ext, f"unknown ({ext})")

    _cs_timeout = float(os.environ.get("LOCALTHINK_CODE_SURFACE_TIMEOUT", "600"))

    def compute():
        model = router.pick_model("code_surface", len(content))
        prompt = f"Language: {lang}\n\n{content}"
        return generate(prompt=prompt, system=CODE_SURFACE_SYSTEM, model=model, timeout=_cs_timeout)

    return cache.get_or_compute("code_surface", inputs, compute)


@mcp.tool()
def local_symbols(file_path: str) -> str:
    """Extract a complete symbol table from a source file: every named definition with
    its line number and a one-line description.

    Returns: one line per symbol — type, name, (line N), description."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    inputs = cache.file_inputs(file_path)

    def compute():
        numbered = _number_lines(content)
        model = router.pick_model("symbols", len(numbered))
        return generate(prompt=numbered, system=SYMBOLS_SYSTEM, model=model)

    return cache.get_or_compute("symbols", inputs, compute)


@mcp.tool()
def local_find_impl(file_path: str, spec: str, passes: int = 1) -> str:
    """Find the code that implements a natural-language specification — returns the
    complete logical unit with line numbers, without loading the file into context.

    passes=2/3 improve accuracy on ambiguous or large files.

    Examples:
      'the function that validates email addresses'
      'JWT token verification logic'
      'database connection pool initialization'"""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    inputs = cache.file_inputs(file_path, spec=spec, p=passes)

    def compute():
        numbered = _number_lines(content)
        prompt = f"Spec: {spec}\n\nSource:\n{numbered}"
        return run_passes(prompt=prompt, system=FIND_IMPL_SYSTEM, passes=passes)

    return cache.get_or_compute("find_impl", inputs, compute)


@mcp.tool()
def local_strip_to_skeleton(file_path: str) -> str:
    """Return a source file with ALL function/method bodies replaced by '...' while
    keeping the full structure: signatures, decorators, type annotations, class hierarchy.
    Typically 30-50% of original size."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    inputs = cache.file_inputs(file_path)

    def compute():
        return generate(prompt=content, system=SKELETON_SYSTEM)

    return cache.get_or_compute("strip_to_skeleton", inputs, compute)


@mcp.tool()
def local_grep_semantic(file_path: str, meaning: str, max_results: int = 5) -> str:
    """Semantic line search: find passages that match a *meaning*, not a keyword.

    'find where authentication is handled' finds auth middleware even if the word
    'auth' isn't present. Returns top N most relevant excerpts with line ranges."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    inputs = cache.file_inputs(file_path, meaning=meaning, n=max_results)

    def compute():
        numbered = _number_lines(content)
        prompt = (
            f"Search meaning: {meaning}\n"
            f"Return up to {max_results} most relevant excerpts.\n\n"
            f"Document:\n{numbered}"
        )
        return generate(prompt=prompt, system=SEMANTIC_GREP_SYSTEM)

    return cache.get_or_compute("grep_semantic", inputs, compute)


# ── Document analysis ─────────────────────────────────────────────────────────


@mcp.tool()
def local_classify(text: str) -> str:
    """Classify content type and recommend the best localthink tool to use on it.

    Returns JSON: content_type, language, estimated_tokens, recommended_tool,
    compression_estimate (high/medium/low), key_topics.

    Uses Ollama format=json for reliable structured output."""
    if not health_check():
        return _UNAVAILABLE
    sample = text[:_CLASSIFY_SAMPLE]
    inputs = cache.text_inputs(sample)

    def compute():
        model = router.pick_model("classify", len(sample))
        data = structured.generate_structured(
            prompt=sample, system=CLASSIFY_SYSTEM, model=model
        )
        return structured.render_as_text(data)

    return cache.get_or_compute("classify", inputs, compute)


@mcp.tool()
def local_outline(text: str) -> str:
    """Generate a structural outline (table of contents with line ranges) from a document.
    Structure only — no content. Pairs naturally with local_extract."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text)

    def compute():
        model = router.pick_model("outline", len(text))
        return generate(prompt=text, system=OUTLINE_SYSTEM, model=model)

    return cache.get_or_compute("outline", inputs, compute)


@mcp.tool()
def local_audit(file_path: str, checklist: list[str], passes: int = 1) -> str:
    """Check a file against a list of criteria. Returns PASS / FAIL / PARTIAL / N/A per item.

    passes=2/3 improves accuracy for ambiguous security or quality checks.

    Examples:
      ['no hardcoded secrets', 'uses parameterized queries', 'input validated']
      ['error handling present', 'no TODO comments', 'types annotated']"""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    checklist_key = "|".join(checklist)
    inputs = cache.file_inputs(file_path, ck=checklist_key, p=passes)

    def compute():
        checklist_block = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(checklist))
        prompt = f"Checklist:\n{checklist_block}\n\nDocument:\n{content}"
        return run_passes(prompt=prompt, system=AUDIT_SYSTEM, passes=passes)

    return cache.get_or_compute("audit", inputs, compute)


@mcp.tool()
def local_timeline(text: str) -> str:
    """Extract a chronological event sequence from any document: logs, changelogs,
    commit messages, incident reports. Deduplicates repeated events."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text)

    def compute():
        model = router.pick_model("timeline", len(text))
        return generate(prompt=text, system=TIMELINE_SYSTEM, model=model)

    return cache.get_or_compute("timeline", inputs, compute)


@mcp.tool()
def local_schema_infer(data: str) -> str:
    """Infer a compact JSON Schema (draft-07 subset) from sample data: JSON, CSV, YAML,
    or API response samples. Uses Ollama format=json for reliable structured output."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(data)

    def compute():
        model = router.pick_model("schema_infer", len(data))
        result = structured.generate_structured(
            prompt=data, system=SCHEMA_INFER_SYSTEM, model=model
        )
        return structured.render_as_text(result)

    return cache.get_or_compute("schema_infer", inputs, compute)


@mcp.tool()
def local_translate(text: str, target_format: str) -> str:
    """Convert content between technical formats without loading it into context.

    Supported: json↔yaml↔toml, csv↔markdown_table, code→pseudocode,
    sql→english, env→json, typescript_types→json_schema."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text, fmt=target_format)

    def compute():
        model = router.pick_model("translate", len(text))
        prompt = f"Convert to: {target_format}\n\n{text}"
        return generate(prompt=prompt, system=TRANSLATE_SYSTEM, model=model)

    return cache.get_or_compute("translate", inputs, compute)


@mcp.tool()
def local_scan_dir(dir_path: str, pattern: str = "*", question: str = "", max_files: int = 20) -> str:
    """Walk a directory and summarize or query every matching file concurrently.
    Files are processed in parallel (LOCALTHINK_MAX_CONCURRENCY=4).

    pattern:  glob relative to dir_path (e.g. '*.py', '**/*.ts')
    question: if provided, answers this per file; if empty, generates a one-line summary"""
    if not health_check():
        return _UNAVAILABLE

    search_path = os.path.join(dir_path, pattern)
    all_matches = _glob.glob(search_path, recursive=True)
    files = [f for f in all_matches if os.path.isfile(f)][:max_files]

    if not files:
        return f"[localthink] No files matched: {search_path}"

    header = f"# Directory scan: {dir_path}\nPattern: {pattern}  |  Files: {len(files)}\n"

    def scan_one(path: str) -> str:
        content, err = _read_file(path)
        rel = os.path.relpath(path, dir_path)
        if err:
            return f"## {rel}\n{err}\n"
        if not content.strip():
            return f"## {rel}\n[empty]\n"

        inputs = cache.file_inputs(path, q=question)

        def compute():
            if question:
                prompt = f"Question: {question}\n\nDocument:\n{content}"
                return generate(prompt=prompt, system=ANSWER_SYSTEM)
            return generate(prompt=content, system=SCAN_DIR_SYSTEM)

        output = cache.get_or_compute("scan_dir", inputs, compute)
        return f"## {rel}\n{output}\n"

    results = run_batch([lambda p=path: scan_one(p) for path in files])
    return header + "\n".join(results)


# ── Compression tools ─────────────────────────────────────────────────────────


@mcp.tool()
def local_compress_log(file_path: str, level: str = "", since: str = "") -> str:
    """Compress a log file to its essential signal: grouped errors, key events, anomalies.

    level: filter by log level (e.g. 'ERROR', 'WARN'). Empty = all levels.
    since: filter to lines containing this timestamp prefix (e.g. '2026-04-13')."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err

    filter_lines = [
        line for line in content.splitlines()
        if (not level or level.upper() in line.upper())
        and (not since or since in line)
    ]
    if not filter_lines:
        return f"[localthink] No lines matched filters (level={level!r}, since={since!r})"

    inputs = cache.file_inputs(file_path, level=level, since=since)
    filtered = "\n".join(filter_lines)

    def compute():
        return generate(prompt=filtered, system=LOG_COMPRESS_SYSTEM)

    return cache.get_or_compute("compress_log", inputs, compute)


@mcp.tool()
def local_compress_stack_trace(text: str) -> str:
    """Compress a stack trace to its essential signal: root cause, failure point,
    3-5 key frames, fix hint. Works with Python, JS, Java, Go, Rust, and others."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text)

    def compute():
        return generate(prompt=text, system=STACK_TRACE_SYSTEM)

    return cache.get_or_compute("compress_stack_trace", inputs, compute)


@mcp.tool()
def local_compress_data(data: str, keep_fields: list[str] = [], question: str = "") -> str:
    """Compress structured data payloads: JSON, CSV, API responses.

    keep_fields: strip all other fields from the output.
    question:    answer it in 1-3 sentences before the compressed data."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(data, kf="|".join(keep_fields), q=question)

    def compute():
        fields_line = f"Keep only these fields: {', '.join(keep_fields)}\n\n" if keep_fields else ""
        question_line = f"Question to answer first: {question}\n\n" if question else ""
        prompt = f"{fields_line}{question_line}{data}"
        return generate(prompt=prompt, system=DATA_COMPRESS_SYSTEM)

    return cache.get_or_compute("compress_data", inputs, compute)


@mcp.tool()
def local_session_compress(file_path: str) -> str:
    """Compress a saved conversation transcript to a compact re-entry briefing.
    Returns: context, decisions made, current state, open items, key constraints."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    inputs = cache.file_inputs(file_path)

    def compute():
        return generate(prompt=content, system=SESSION_COMPRESS_SYSTEM)

    return cache.get_or_compute("session_compress", inputs, compute)


@mcp.tool()
def local_prompt_compress(text: str) -> str:
    """Compress a long CLAUDE.md or system prompt to its minimal directive set.
    Preserves every unique rule. Target: 20-40% of original length."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text)

    def compute():
        return generate(prompt=text, system=PROMPT_COMPRESS_SYSTEM)

    return cache.get_or_compute("prompt_compress", inputs, compute)


# ── Pre-injection tools ───────────────────────────────────────────────────────


@mcp.tool()
def local_improve_prompt(prompt: str, context: str = "", passes: int = 1) -> str:
    """Sharpen a rough user prompt using a local LLM before Claude processes it.

    Rewrites the prompt to be clear, specific, and unambiguous without changing intent.
    passes=2/3 produces increasingly polished output via draft→refine→verify.

    Usage: write rough prompt → improve → feed the result to Claude."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(prompt, ctx=context[:200] if context else "", p=passes)

    def compute():
        user_input = (
            f"Context: {context}\n\nPrompt to improve:\n{prompt}"
            if context else f"Prompt to improve:\n{prompt}"
        )
        return run_passes(prompt=user_input, system=IMPROVE_PROMPT_SYSTEM, passes=passes)

    return cache.get_or_compute("improve_prompt", inputs, compute)


@mcp.tool()
def local_preplan(task: str, context: str = "", depth: str = "standard", passes: int = 1) -> str:
    """Generate a structured implementation plan locally before Claude spends tokens planning.

    Returns: goal, assumptions, ordered steps (with file/function refs), risks, open questions.
    depth: 'quick' (3-5 steps) | 'standard' (full plan) | 'detailed' (sub-bullets + rationale)
    passes=2/3 produces a more accurate and complete plan via draft→refine→verify.

    Usage: describe task → preplan → hand the plan to Claude to execute."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(task, ctx=context[:200] if context else "", depth=depth, p=passes)

    def compute():
        depth_line = f"depth={depth}\n\n"
        context_block = f"Context:\n{context}\n\n" if context else ""
        prompt = f"{depth_line}{context_block}Task:\n{task}"
        return run_passes(prompt=prompt, system=PREPLAN_SYSTEM, passes=passes)

    return cache.get_or_compute("preplan", inputs, compute)


@mcp.tool()
def local_refine(text: str, goal: str, passes: int = 2) -> str:
    """Iteratively refine any text toward a stated goal using the multi-pass stack.

    Applies the draft→refine→verify loop to arbitrary input. Use to improve
    Claude's intermediate outputs, compress and sharpen any prose, or polish
    a draft before committing it.

    passes=2 (default): fast draft → main-model refine.
    passes=3: + fast verify, re-refine if gaps found."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(text, goal=goal, p=passes)

    def compute():
        prompt = f"Goal: {goal}\n\nText to refine:\n{text}"
        return run_passes(prompt=prompt, system=REFINE_SYSTEM, passes=passes)

    return cache.get_or_compute("refine", inputs, compute)


# ── Cache management + info ───────────────────────────────────────────────────


@mcp.tool()
def local_models() -> str:
    """List all Ollama models available locally, annotating which are configured as
    MAIN, FAST, and TINY for this server."""
    models = list_models()
    if not models:
        return _UNAVAILABLE

    tiers = router.all_models()
    lines = ["Available Ollama models:"]
    for m in models:
        tags: list[str] = []
        if m == tiers["main"]:
            tags.append("MAIN")
        if m == tiers["fast"] and tiers["fast"] != tiers["main"]:
            tags.append("FAST")
        if m == tiers["tiny"] and tiers["tiny"] not in (tiers["main"], tiers["fast"]):
            tags.append("TINY")
        tag_str = f"  [{', '.join(tags)}]" if tags else ""
        lines.append(f"  {m}{tag_str}")
    lines += [
        "",
        f"OLLAMA_MODEL       = {tiers['main']}",
        f"OLLAMA_FAST_MODEL  = {tiers['fast']}",
        f"OLLAMA_TINY_MODEL  = {tiers['tiny']}",
        f"OLLAMA_BASE_URL    = {os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')}",
    ]
    return "\n".join(lines)


@mcp.tool()
def local_cache_stats() -> str:
    """Show cache statistics: number of entries, total disk usage, cache directory.

    Use to verify caching is working after a session, or before local_cache_clear."""
    s = cache.stats()
    size_mb = s["size_bytes"] / (1024 * 1024)
    return (
        f"Cache entries : {s['entries']}\n"
        f"Disk usage    : {size_mb:.2f} MB\n"
        f"Location      : {s['cache_dir']}\n"
        f"TTL           : {cache.CACHE_TTL_DAYS} days\n"
        f"Concurrency   : {os.environ.get('LOCALTHINK_MAX_CONCURRENCY', '4')} workers"
    )


@mcp.tool()
def local_cache_clear(older_than_days: int = 0) -> str:
    """Remove cached results.

    older_than_days=0  (default): clear all entries.
    older_than_days=N: clear only entries older than N days."""
    removed = cache.clear(older_than_days=older_than_days)
    scope = f"older than {older_than_days} days" if older_than_days else "all"
    return f"[localthink] Removed {removed} cache entries ({scope})."


# ── v2.1 Smart Buffer ────────────────────────────────────────────────────────


@mcp.tool()
def local_gate(raw_output: str, budget_tokens: int = 400) -> str:
    """Phase 1 smart buffer: summarise any raw output to pattern + anomalies.

    Never dumps raw content. Call local_slice() to retrieve windows on demand.
    budget_tokens: approximate token budget for the summary."""
    _file_pat = r"[\w./\\-]+\.\w{1,5}"

    if not health_check():
        # Regex fallback — count lines, find ERROR/WARN/FAIL
        lines = raw_output.splitlines()
        errors = [l for l in lines if re.search(r"\b(ERROR|WARN|FAIL)\b", l, re.I)]
        summary = (
            f"Pattern: {len(lines)} lines total\n"
            f"Anomalies:\n"
            + ("\n".join(f"- {e[:80]}" for e in errors[:5]) if errors else "- none")
            + f"\nSignal: {len(errors)} error/warn/fail lines found."
        )
    else:
        inputs = cache.text_inputs(raw_output, b=budget_tokens)
        summary = cache.get_or_compute(
            "gate",
            inputs,
            lambda: generate(raw_output[:8000], system=GATE_SUMMARY_SYSTEM),
        )

    # Append file pointer if paths found in raw output
    paths = re.findall(_file_pat, raw_output)
    if paths:
        # Extract first anomaly line for context_hint
        anomaly_lines = [l for l in summary.splitlines() if l.startswith("- ")]
        hint = anomaly_lines[0].lstrip("- ")[:60] if anomaly_lines else "see anomalies"
        summary += f'\nPointer: {{"file": "{paths[0]}", "context_hint": "{hint}"}}'

    return summary


@mcp.tool()
def local_slice(
    file_path: str,
    offset_lines: int = 0,
    window: int = 30,
    query: str = "",
    symbol: str = "",
) -> str:
    """Raw narrow window into a file. Only call explicitly — never auto-inject.

    symbol: find definition line and use as offset base.
    query: score lines by relevance, surface best window."""
    content, err = _read_file(file_path)
    if err:
        return err

    lines = content.splitlines()
    offset = offset_lines

    if symbol:
        pat = re.compile(
            r"(def|class|function|const|func)\s+" + re.escape(symbol) + r"[\s:(]"
        )
        for i, line in enumerate(lines):
            if pat.search(line):
                offset = i
                break

    window = min(window, 50)

    if query and health_check():
        # Score lines by relevance
        numbered = _number_lines(content)
        result = generate(
            f"File excerpt:\n{numbered}\n\nQuery: {query}",
            system=SEMANTIC_GREP_SYSTEM,
        )
        start = offset
        end = min(offset + window, len(lines))
        return f"[local_slice: {file_path} lines {start + 1}–{end} | semantic]\n{result}"

    start = max(0, offset)
    end = min(start + window, len(lines))
    snippet = "\n".join(lines[start:end])
    return f"[local_slice: {file_path} lines {start + 1}–{end}]\n{snippet}"


@mcp.tool()
def local_diff_semantic(before: str, after: str) -> str:
    """Semantic diff: meaning changes only. Suppresses whitespace/comment/import noise.

    Flags: signature changes, removed exports, new side-effects."""
    if not health_check():
        return _UNAVAILABLE
    inputs = cache.text_inputs(before + after)

    def compute():
        prompt = f"=== BEFORE ===\n{before}\n\n=== AFTER ===\n{after}"
        return generate(prompt, system=DIFF_SEMANTIC_SYSTEM)

    return cache.get_or_compute("diff_semantic", inputs, compute)


# ── v2.1 Execution Filters ────────────────────────────────────────────────────


@mcp.tool()
def local_run_tests(target: str = "", focus: str = "") -> str:
    """Run test suite. Returns failures only + delta vs last run. Never passing tests.

    delta: change in failure count since last run (persisted in ~/.localthink-mcp/last_run.json)
    target: path or test name to pass to runner.
    focus: keyword filter on failure names."""
    cwd = os.getcwd()

    # Detect runner
    def exists(name: str) -> bool:
        return os.path.exists(os.path.join(cwd, name))

    def pyproject_has(section: str) -> bool:
        pp = os.path.join(cwd, "pyproject.toml")
        if not os.path.exists(pp):
            return False
        try:
            return section in open(pp).read()
        except Exception:
            return False

    if exists("pytest.ini") or pyproject_has("[tool.pytest.ini_options]"):
        runner = "pytest"
        cmd = ["python", "-m", "pytest", "-x", "--tb=short", "-q"]
        fail_pat = re.compile(r"FAILED\s+(\S+)")
    elif exists("jest.config.js") or exists("jest.config.ts") or exists("jest.config.mjs"):
        runner = "jest"
        cmd = ["npx", "jest", "--no-coverage"]
        fail_pat = re.compile(r"✕\s+(.+)")
    elif exists("vitest.config.js") or exists("vitest.config.ts") or exists("vitest.config.mjs"):
        runner = "vitest"
        cmd = ["npx", "vitest", "run"]
        fail_pat = re.compile(r"✕\s+(.+)")
    elif exists("go.mod"):
        runner = "go"
        cmd = ["go", "test", "./..."]
        fail_pat = re.compile(r"--- FAIL:\s+(\S+)")
    elif exists("Cargo.toml"):
        runner = "cargo"
        cmd = ["cargo", "test"]
        fail_pat = re.compile(r"FAILED\s+(\S+)")
    else:
        runner = "pytest"
        cmd = ["python", "-m", "pytest", "-x", "--tb=short", "-q"]
        fail_pat = re.compile(r"FAILED\s+(\S+)")

    if target:
        cmd.append(target)

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=cwd
        )
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "test runner timed out after 120s"})
    except FileNotFoundError as e:
        return json.dumps({"error": f"runner not found: {e}"})

    # Count total run (pytest: "N passed" or "N failed")
    total_match = re.search(r"(\d+) (?:passed|failed|error)", output)
    total_run = int(total_match.group(1)) if total_match else 0

    # Parse failures
    failed: list[dict] = []
    output_lines = output.splitlines()
    for i, line in enumerate(output_lines):
        m = fail_pat.search(line)
        if m:
            name = m.group(1).strip()
            if focus and focus.lower() not in name.lower():
                continue
            surface_lines = output_lines[max(0, i - 2): i + 3]
            error_surface = "\n".join(surface_lines)
            repro = f"{runner} {name}" if runner == "pytest" else f"{runner} run -- {name}"
            failed.append({"name": name, "error_surface": error_surface, "repro_hint": repro})

    # Delta vs last run
    last_run_file = memo_store.LAST_RUN_FILE
    prev_names: set[str] = set()
    if last_run_file.exists():
        try:
            prev = json.loads(last_run_file.read_text(encoding="utf-8"))
            prev_names = set(prev.get("failed_names", []))
        except Exception:
            pass

    cur_names = {f["name"] for f in failed}
    added = len(cur_names - prev_names)
    removed = len(prev_names - cur_names)
    delta = f"+{added}/-{removed}"

    # Persist
    try:
        last_run_file.parent.mkdir(parents=True, exist_ok=True)
        last_run_file.write_text(
            json.dumps({"failed_names": list(cur_names)}, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    if not failed:
        return json.dumps({"passed": True, "total_run": total_run, "delta": delta})

    pointer = {"file": failed[0]["name"].split("::")[0], "context_hint": failed[0]["name"]}
    return json.dumps(
        {"failed": failed, "delta": delta, "total_run": total_run, "pointer": pointer},
        indent=2,
    )


@mcp.tool()
def local_run_lint(target: str = "") -> str:
    """Run linter. Returns violations grouped by rule type, never by file.

    Suppresses passing rules and verbose paths."""
    cwd = os.getcwd()

    def exists(name: str) -> bool:
        return os.path.exists(os.path.join(cwd, name))

    def cfg_has(section: str) -> bool:
        for f in ("pyproject.toml", "setup.cfg"):
            p = os.path.join(cwd, f)
            if os.path.exists(p):
                try:
                    if section in open(p).read():
                        return True
                except Exception:
                    pass
        return False

    # Detect linter
    if exists(".ruff.toml") or cfg_has("[tool.ruff]"):
        cmd = ["python", "-m", "ruff", "check", "--output-format=text"]
        linter = "ruff"
    elif exists(".flake8") or cfg_has("[flake8]"):
        cmd = ["python", "-m", "flake8", "--max-line-length=120"]
        linter = "flake8"
    elif any(
        exists(f)
        for f in ("eslint.config.js", "eslint.config.mjs", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml")
    ):
        cmd = ["npx", "eslint", "--format=compact"]
        linter = "eslint"
    elif exists("golangci.yml"):
        cmd = ["golangci-lint", "run"]
        linter = "golangci-lint"
    elif exists("Cargo.toml"):
        cmd = ["cargo", "clippy", "--", "-D", "warnings"]
        linter = "clippy"
    else:
        # Fallback: try ruff then flake8
        cmd = ["python", "-m", "ruff", "check", "--output-format=text"]
        linter = "ruff"

    if target:
        cmd.append(target)

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=cwd
        )
        output = (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return "[localthink] lint timed out after 60s"
    except FileNotFoundError:
        if linter == "ruff":
            try:
                proc = subprocess.run(
                    ["python", "-m", "flake8", "--max-line-length=120"],
                    capture_output=True, text=True, timeout=60, cwd=cwd,
                )
                output = (proc.stdout + proc.stderr).strip()
                linter = "flake8"
            except Exception as e:
                return f"[localthink] no linter found: {e}"
        else:
            return f"[localthink] linter not found: {linter}"

    if not output:
        return "✓ No lint violations found."

    # Group violations by rule code
    rule_pat = re.compile(r"([A-Z]\d+|[A-Z][A-Z]+\d*)")
    groups: dict[str, list[str]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or re.match(r"^(Found \d+|All checks|warning\[|error\[)", line):
            continue
        m = rule_pat.search(line)
        rule = m.group(1) if m else "OTHER"
        groups.setdefault(rule, []).append(line)

    if not groups:
        return "✓ No lint violations found."

    out_lines: list[str] = []
    for rule, violations in sorted(groups.items()):
        short = violations[0][:120]
        # Shorten path
        path_m = re.match(r"(.+?\.(?:py|ts|js|go|rs))(?::(\d+))?", short)
        if path_m:
            rel = os.path.relpath(path_m.group(1), cwd)
            ln = path_m.group(2) or ""
            msg = short[path_m.end():]
            short = f"{rel}:{ln}{msg}"
        out_lines.append(f"[rule {rule}] — {len(violations)} violation(s)\n  {short}")

    return "\n".join(out_lines)


@mcp.tool()
def local_run_build() -> str:
    """Run project build. Returns root cause error only.

    Root cause: first error in dep-order, not log-order.
    Suppresses warnings, linking steps, progress output."""
    cwd = os.getcwd()

    def exists(name: str) -> bool:
        return os.path.exists(os.path.join(cwd, name))

    # Detect build system
    if exists("tsconfig.json"):
        cmd = ["npx", "tsc", "--noEmit"]
    elif exists("Cargo.toml"):
        cmd = ["cargo", "build"]
    elif exists("go.mod"):
        cmd = ["go", "build", "./..."]
    elif exists("Makefile"):
        cmd = ["make"]
    elif exists("pyproject.toml") or exists("setup.py"):
        # Syntax-check all .py files under src/
        src_dir = os.path.join(cwd, "src")
        py_files = _glob.glob(os.path.join(src_dir, "**", "*.py"), recursive=True)
        if not py_files:
            py_files = _glob.glob(os.path.join(cwd, "**", "*.py"), recursive=True)
        errors: list[dict] = []
        for f in py_files:
            r = subprocess.run(
                ["python", "-m", "py_compile", f],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                err_line = (r.stderr or r.stdout).strip().splitlines()
                errors.append({"file": f, "msg": err_line[0] if err_line else "syntax error"})
        if not errors:
            return json.dumps({"built": True, "warnings": 0})
        root = errors[0]
        symbols = re.findall(r"\b[A-Z][a-zA-Z_]+\b", root["msg"])
        return json.dumps(
            {
                "root_cause": f"{os.path.relpath(root['file'], cwd)} — {root['msg']}",
                "affected_symbols": symbols,
                "error_surface": root["msg"],
                "pointer": {
                    "file": os.path.relpath(root["file"], cwd),
                    "offset_lines": 0,
                    "context_hint": root["msg"][:80],
                },
            },
            indent=2,
        )
    else:
        return json.dumps({"error": "no recognised build system found in cwd"})

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=cwd
        )
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "build timed out after 120s"})
    except FileNotFoundError as e:
        return json.dumps({"error": f"build tool not found: {e}"})

    if proc.returncode == 0:
        warnings = len(re.findall(r"(?i)warning:", output))
        return json.dumps({"built": True, "warnings": warnings})

    # Find root cause — first error line
    err_lines = [l for l in output.splitlines() if re.search(r"(?i)error:", l)]
    root_line = err_lines[0] if err_lines else output.splitlines()[0] if output else "unknown error"
    symbols = re.findall(r"\b[A-Z][a-zA-Z_]+\b", root_line)
    surface_idx = output.splitlines().index(root_line) if root_line in output else 0
    surface_lines = output.splitlines()[max(0, surface_idx - 1): surface_idx + 4]
    # Extract file from error line
    file_m = re.search(r"([\w./\\-]+\.\w{2,5})", root_line)
    file_ref = file_m.group(1) if file_m else "unknown"
    line_m = re.search(r":(\d+)", root_line)
    line_no = int(line_m.group(1)) - 1 if line_m else 0

    return json.dumps(
        {
            "root_cause": root_line[:200],
            "affected_symbols": symbols[:10],
            "error_surface": "\n".join(surface_lines),
            "pointer": {
                "file": file_ref,
                "offset_lines": line_no,
                "context_hint": root_line[:80],
            },
        },
        indent=2,
    )


# ── v2.1 Scratchpad ───────────────────────────────────────────────────────────


@mcp.tool()
def local_memo_write(key: str, content: str, compress: bool = False) -> str:
    """Write to session scratchpad. key: decisions|assumptions|pitfalls|open_questions

    compress=True: Ollama compresses to bullets (~5x reduction) before writing.
    Auto-compacts section if it exceeds 3000 chars."""
    result = memo_store.memo_write(key, content, compress)
    if "error" in result:
        return result["error"]
    return json.dumps(result, indent=2)


@mcp.tool()
def local_memo_read(query: str = "", section: str = "") -> str:
    """Read from session scratchpad.

    query: keyword search across all sections.
    section: return one section verbatim.
    neither: distilled summary of all sections (≤200 tokens)."""
    return memo_store.memo_read(query, section)


@mcp.tool()
def local_memo_checkpoint() -> str:
    """Compress scratchpad to RESUME_PROMPT. Paste after /clear to restore context.

    Writes CHECKPOINT.md. Returns ≤200-token resume string."""
    return memo_store.memo_checkpoint()


# ── v2.1 Model Notes ──────────────────────────────────────────────────────────


@mcp.tool()
def local_note_write(category: str, content: str) -> str:
    """Write permanent model note. Persists across all sessions, never cleared.

    category: architecture|gotcha|pattern"""
    result = memo_store.note_write(category, content)
    if "error" in result:
        return result["error"]
    return json.dumps(result, indent=2)


@mcp.tool()
def local_note_search(query: str, limit: int = 5) -> str:
    """Search permanent model notes. Keyword overlap scoring (cosine if nomic-embed-text available).

    Returns top N notes across all categories."""
    return memo_store.note_search(query, limit)


# ── Settings GUI ──────────────────────────────────────────────────────────────


@mcp.tool()
def local_config() -> str:
    """Open the LocalThink settings GUI.

    Launches a graphical settings window where you can configure:
      - Ollama base URL and connection test
      - Default / Fast / Tiny model tiers
      - Cache directory and TTL
      - Memo/notes directory

    Settings are saved to ~/.localthink-mcp/config.json and applied
    to the current process immediately. A server restart is required
    for model/URL changes to take full effect in ollama_client."""
    gui_script = os.path.join(os.path.dirname(__file__), "gui", "config_gui.py")
    if not os.path.exists(gui_script):
        return "[localthink] GUI script not found — reinstall localthink-mcp."

    before = _current_cfg()

    try:
        result = subprocess.run(
            [sys.executable, gui_script],
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return "[localthink] Settings window timed out."
    except Exception as e:
        return f"[localthink] Could not open settings GUI: {e}"

    if result.returncode != 0:
        return "[localthink] Settings cancelled — no changes saved."

    after = _current_cfg()

    changed = {k: after[k] for k in after if after[k] != before.get(k)}
    if not changed:
        return "Settings saved (no values changed)."

    from core.config import SCHEMA
    lines = ["Settings saved. Changed:"]
    for k, v in changed.items():
        label = SCHEMA[k]["label"] if k in SCHEMA else k
        old   = before.get(k, "")
        lines.append(f"  {label}: {old!r} → {v!r}")

    lines.append("")
    lines.append("Restart the MCP server for model/URL changes to fully apply.")
    return "\n".join(lines)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
