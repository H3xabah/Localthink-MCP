#!/usr/bin/env python3
"""
localthink-mcp v1.1.0 — Local Ollama-backed MCP server for Claude Code.

v0.1.0 tools (unchanged):
  local_summarize      Compress a large text block (~30x token reduction)
  local_extract        Pull only relevant cited passages from a document
  local_answer         Q&A against a file without loading it into context

v1.1 tools:
  local_shrink_file        File → compressed dense text (for repeated reference)
  local_diff               Summarize meaningful changes between two text blobs
  local_batch_answer       Answer one question across many files in one call
  local_pipeline           Chain ops (extract→summarize etc.) in a single round-trip
  local_auto               Meta-tool: auto-selects the right operation
  local_chat               Multi-turn doc Q&A — doc never enters Claude's context
  local_grep_semantic      Semantic line search: find meaning, not just keywords
  local_scan_dir           Summarize or query every file in a directory at once
  local_code_surface       Public API skeleton (Python: pure AST; others: LLM)
  local_classify           Classify content type + recommend best tool
  local_outline            Structural TOC without content — see what's where
  local_audit              Checklist-based pass/fail audit of a file
  local_models             List available Ollama models and current config

v1.1 expansion — high-context compression + smart reading:
  local_compress_log       Log file → signal-only summary (errors grouped, noise stripped)
  local_compress_stack_trace  Stack trace + source → root cause + key frames
  local_compress_data      JSON / CSV / API response → stripped, sampled payload
  local_session_compress   Saved conversation → re-entry briefing (context/decisions/state)
  local_prompt_compress    Long CLAUDE.md / system prompt → minimal directive set
  local_symbols            File → full symbol table with line numbers
  local_find_impl          Natural-language spec → the code that implements it
  local_strip_to_skeleton  File → all bodies replaced with '...' structure preserved
  local_translate          Format conversion: JSON↔YAML↔TOML, CSV→Markdown, SQL→English
  local_schema_infer       Sample data → compact JSON Schema
  local_timeline           Document → chronological event sequence
  local_diff_files         Two file paths → diff summary (neither file loaded into context)

All inference is local via Ollama — no data leaves your machine.
"""
import sys
import os
import json
import glob as _glob

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from ollama_client import generate, generate_fast, health_check, list_models, DEFAULT_MODEL, FAST_MODEL
from prompts import (
    SUMMARIZE_SYSTEM,
    EXTRACT_SYSTEM,
    ANSWER_SYSTEM,
    DIFF_SYSTEM,
    CHAT_SYSTEM,
    AUTO_SYSTEM,
    SEMANTIC_GREP_SYSTEM,
    SCAN_DIR_SYSTEM,
    CODE_SURFACE_SYSTEM,
    OUTLINE_SYSTEM,
    AUDIT_SYSTEM,
    CLASSIFY_SYSTEM,
    # v1.1 expansion
    LOG_COMPRESS_SYSTEM,
    STACK_TRACE_SYSTEM,
    DATA_COMPRESS_SYSTEM,
    SESSION_COMPRESS_SYSTEM,
    PROMPT_COMPRESS_SYSTEM,
    SYMBOLS_SYSTEM,
    FIND_IMPL_SYSTEM,
    SKELETON_SYSTEM,
    TRANSLATE_SYSTEM,
    SCHEMA_INFER_SYSTEM,
    TIMELINE_SYSTEM,
)
from code_surface import extract_python_surface

mcp = FastMCP("localthink")

_UNAVAILABLE = "[localthink] Ollama is not running. Start it with: ollama serve"
_MAX_FILE_BYTES = 200_000
_MAX_PIPELINE_STEPS = 5
_MAX_SCAN_FILES = 20
_CLASSIFY_SAMPLE = 8_000  # only send a sample for classification


def _read_file(path: str) -> tuple[str, str]:
    """Return (content, error). content is capped at _MAX_FILE_BYTES. error is '' on success."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(_MAX_FILE_BYTES), ""
    except Exception as e:
        return "", f"[localthink] Cannot read {path}: {e}"


def _number_lines(text: str) -> str:
    """Prefix each line with its 1-based line number."""
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(text.splitlines()))


# ── v0.1.0 tools ──────────────────────────────────────────────────────────


@mcp.tool()
def local_summarize(text: str, focus: str = "") -> str:
    """Compress a large text block using a local LLM. Preserves API names, signatures, error strings, config keys.
    Use when you have a large document and want to reduce how much context it occupies.
    Optional focus: a phrase describing what to prioritize in the summary."""
    if not health_check():
        return _UNAVAILABLE
    prompt = f"Focus on: {focus}\n\n{text}" if focus else text
    return generate(prompt=prompt, system=SUMMARIZE_SYSTEM)


@mcp.tool()
def local_extract(text: str, query: str) -> str:
    """Extract only the passages relevant to a specific query from a large document.
    Returns cited sections, not a paraphrase. Use when you know what you're looking for
    in a large blob and don't need the rest."""
    if not health_check():
        return _UNAVAILABLE
    prompt = f"Query: {query}\n\nDocument:\n{text}"
    return generate(prompt=prompt, system=EXTRACT_SYSTEM)


@mcp.tool()
def local_answer(file_path: str, question: str) -> str:
    """Answer a question from a file's contents without loading the whole file into Claude's context.
    Designed for querying raw archived outputs in cache/raw-mcp/ after auto-compression discarded detail you need."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    prompt = f"Question: {question}\n\nDocument:\n{content}"
    return generate(prompt=prompt, system=ANSWER_SYSTEM)


# ── v1.1 tools ────────────────────────────────────────────────────────────


@mcp.tool()
def local_shrink_file(file_path: str, focus: str = "") -> str:
    """Compress a file to dense text and return it — unlike local_answer this returns the
    compressed content itself, not a specific answer. Use when you want to hold a compact
    version of a large file in Claude's context for repeated reference (multiple questions,
    editing decisions, etc.). Typically ~20-30% of the original size."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    prompt = f"Focus on: {focus}\n\n{content}" if focus else content
    return generate(prompt=prompt, system=SUMMARIZE_SYSTEM)


@mcp.tool()
def local_diff(before: str, after: str, focus: str = "") -> str:
    """Summarize the meaningful changes between two text blobs (before → after).
    Highlights additions, removals, and modifications with an impact assessment.
    Optional focus: a topic to prioritize (e.g. 'auth', 'breaking changes', 'security').
    Use for changelogs, PR diffs, config evolution, API version comparisons."""
    if not health_check():
        return _UNAVAILABLE
    focus_line = f"Focus on changes related to: {focus}\n\n" if focus else ""
    prompt = f"{focus_line}=== BEFORE ===\n{before}\n\n=== AFTER ===\n{after}"
    return generate(prompt=prompt, system=DIFF_SYSTEM)


@mcp.tool()
def local_batch_answer(file_paths: list[str], question: str) -> str:
    """Answer the same question across multiple files without loading any of them into
    Claude's context. Returns one answer per file.

    Ideal use cases:
    - 'Does this file have hardcoded credentials?'
    - 'What does this file export?'
    - 'Does this config use the legacy API format?'

    Files that cannot be read are reported as errors in the output."""
    if not health_check():
        return _UNAVAILABLE
    results: list[str] = []
    for path in file_paths:
        content, err = _read_file(path)
        if err:
            results.append(f"### {path}\n{err}")
            continue
        prompt = f"Question: {question}\n\nDocument:\n{content}"
        answer = generate(prompt=prompt, system=ANSWER_SYSTEM)
        results.append(f"### {path}\n{answer}")
    return "\n\n".join(results)


@mcp.tool()
def local_pipeline(text: str, steps: list[dict]) -> str:
    """Chain multiple operations in a single MCP call. Each step's output feeds the next.
    Saves round-trips when you know in advance you'll need multiple operations.

    Supported step ops:
      {"op": "summarize", "focus": "<optional topic>"}
      {"op": "extract",   "query": "<what to find>"}
      {"op": "answer",    "question": "<what to ask>"}

    Maximum 5 steps. Example:
      [{"op": "extract", "query": "authentication"}, {"op": "summarize", "focus": "security risks"}]
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
    """Meta-tool: automatically selects the right operation so you don't have to choose.

    Behavior:
    - If input looks like a file path (short string, file exists): reads the file first
    - If question is given AND document is large: extract relevant sections, then answer
    - If question is given AND document is small: answer directly
    - If no question: smart summarize with auto-detected focus

    Use when you're unsure which tool to pick, or want a single-call answer."""
    if not health_check():
        return _UNAVAILABLE

    # Auto-detect file path vs raw text
    content = input
    if len(input) < 500 and os.path.exists(input):
        content, err = _read_file(input)
        if err:
            return err

    if question:
        if len(content) > 4_000:
            # Two-stage: extract relevant sections first, then answer
            extract_prompt = f"Query: {question}\n\nDocument:\n{content}"
            relevant = generate(prompt=extract_prompt, system=EXTRACT_SYSTEM)
            answer_prompt = f"Question: {question}\n\nRelevant sections:\n{relevant}"
        else:
            answer_prompt = f"Question: {question}\n\nDocument:\n{content}"
        return generate(prompt=answer_prompt, system=ANSWER_SYSTEM)
    else:
        return generate(prompt=content, system=AUTO_SYSTEM)


@mcp.tool()
def local_chat(document: str, message: str, history: str = "") -> str:
    """Multi-turn Q&A against a document — the document never enters Claude's context.

    On the first call (history=""), if the document is large it is compressed automatically.
    The returned JSON includes a 'doc' field: pass it back on subsequent turns instead of
    the original document. Only the conversation history grows in Claude's context.

    Returns JSON: {"answer": "...", "history": "...", "doc": "..."}

    Usage pattern:
      Turn 1: r = local_chat(full_document, "What is this about?", "")
              # r["doc"] is now compressed — hold it
      Turn 2: r = local_chat(r["doc"], "Tell me more about X", r["history"])
      Turn 3: r = local_chat(r["doc"], "How does Y work?",     r["history"])
    """
    if not health_check():
        return _UNAVAILABLE

    compressed_doc = document
    note = ""

    # Compress on first turn only if document is large
    if not history and len(document) > 8_000:
        compressed_doc = generate(prompt=document, system=SUMMARIZE_SYSTEM)
        note = "Document was compressed for efficiency. Use result['doc'] in future turns."

    history_block = f"\n\nConversation so far:\n{history}" if history else ""
    prompt = f"Document:\n{compressed_doc}{history_block}\n\nUser: {message}"
    answer = generate(prompt=prompt, system=CHAT_SYSTEM)

    new_history = (f"{history}\nUser: {message}\nAssistant: {answer}").strip()

    result: dict = {
        "answer": answer,
        "history": new_history,
        "doc": compressed_doc,
    }
    if note:
        result["note"] = note

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def local_grep_semantic(file_path: str, meaning: str, max_results: int = 5) -> str:
    """Semantic line search: find passages in a file that match a *meaning*, not just a keyword.

    Unlike grep (which matches exact strings), this understands concepts:
    - 'find where authentication is handled' finds auth middleware even if 'auth' isn't spelled out
    - 'error handling for database timeouts' finds the relevant try/except even with different wording

    Returns the top N most relevant excerpts with line ranges.
    The file is read locally — its content never enters Claude's context."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    numbered = _number_lines(content)
    prompt = (
        f"Search meaning: {meaning}\n"
        f"Return up to {max_results} most relevant excerpts.\n\n"
        f"Document:\n{numbered}"
    )
    return generate(prompt=prompt, system=SEMANTIC_GREP_SYSTEM)


@mcp.tool()
def local_scan_dir(dir_path: str, pattern: str = "*", question: str = "", max_files: int = 20) -> str:
    """Walk a directory and summarize or query every matching file — none loaded into Claude's context.

    pattern:   glob pattern relative to dir_path (e.g. '*.py', '**/*.ts', 'config/*.yaml')
    question:  if provided, answers this question per file; if empty, generates a one-line summary
    max_files: safety cap (default 20)

    Use to get a complete picture of a directory without reading every file individually."""
    if not health_check():
        return _UNAVAILABLE

    search_path = os.path.join(dir_path, pattern)
    all_matches = _glob.glob(search_path, recursive=True)
    files = [f for f in all_matches if os.path.isfile(f)][:max_files]

    if not files:
        return f"[localthink] No files matched: {search_path}"

    results: list[str] = [f"# Directory scan: {dir_path}\nPattern: {pattern}  |  Files: {len(files)}\n"]

    for path in files:
        content, err = _read_file(path)
        rel = os.path.relpath(path, dir_path)

        if err:
            results.append(f"## {rel}\n{err}\n")
            continue
        if not content.strip():
            results.append(f"## {rel}\n[empty]\n")
            continue

        if question:
            prompt = f"Question: {question}\n\nDocument:\n{content}"
            output = generate(prompt=prompt, system=ANSWER_SYSTEM)
        else:
            output = generate(prompt=content, system=SCAN_DIR_SYSTEM)

        results.append(f"## {rel}\n{output}\n")

    return "\n".join(results)


@mcp.tool()
def local_code_surface(file_path: str) -> str:
    """Extract the public API skeleton from a source file.

    Python files — pure AST (no Ollama, no network, instant, deterministic):
      Extracts function/method signatures, class definitions, public constants,
      and annotated module-level variables. Typically 5-10% of original size.

    All other languages — local LLM via the fast model:
      Extracts function signatures, class definitions, exports, and key constants.

    Use to understand a large file's structure and contract without reading the
    full implementation."""
    content, err = _read_file(file_path)
    if err:
        return err

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".py":
        return extract_python_surface(content)

    if not health_check():
        return _UNAVAILABLE

    lang_map = {
        ".js": "JavaScript", ".jsx": "JavaScript (React)",
        ".ts": "TypeScript", ".tsx": "TypeScript (React)",
        ".go": "Go", ".rs": "Rust", ".java": "Java",
        ".cs": "C#", ".cpp": "C++", ".c": "C",
        ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
        ".kt": "Kotlin", ".scala": "Scala",
    }
    lang = lang_map.get(ext, f"unknown ({ext})")
    prompt = f"Language: {lang}\n\n{content}"
    return generate_fast(prompt=prompt, system=CODE_SURFACE_SYSTEM)


@mcp.tool()
def local_classify(text: str) -> str:
    """Classify content type and recommend the best localthink tool to use on it.

    Returns JSON with: content_type, language, estimated_tokens, recommended_tool,
    compression_estimate ('high'/'medium'/'low'), key_topics.

    Use this before processing a large document to choose the right tool, or in hooks
    and scripts to route content programmatically. Only a sample of the text is sent
    to keep the classification itself cheap."""
    if not health_check():
        return _UNAVAILABLE
    sample = text[:_CLASSIFY_SAMPLE]
    return generate_fast(prompt=sample, system=CLASSIFY_SYSTEM)


@mcp.tool()
def local_outline(text: str) -> str:
    """Generate a structural outline (table of contents with line ranges) from a document.
    Returns structure only — no content.

    Use to understand what's in a large document before deciding which section to extract.
    Pairs naturally with local_extract: outline first → extract the section you need.

    For files: pipe through local_shrink_file first if the file is very large."""
    if not health_check():
        return _UNAVAILABLE
    return generate_fast(prompt=text, system=OUTLINE_SYSTEM)


@mcp.tool()
def local_audit(file_path: str, checklist: list[str]) -> str:
    """Check a file against a list of criteria. Returns PASS / FAIL / PARTIAL / N/A per item.

    The file is read locally — it never enters Claude's context. Ideal for:
    - Security checks: ['no hardcoded secrets', 'uses parameterized queries', 'input validated']
    - Code quality: ['error handling present', 'no TODO comments', 'types annotated']
    - Convention compliance: ['uses project logger', 'follows naming convention', 'has docstring']
    - Config validation: ['DEBUG=False in production', 'TLS version >= 1.2']

    Results are ordered to match the input checklist."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    checklist_block = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(checklist))
    prompt = f"Checklist:\n{checklist_block}\n\nDocument:\n{content}"
    return generate(prompt=prompt, system=AUDIT_SYSTEM)


@mcp.tool()
def local_models() -> str:
    """List all Ollama models available locally, annotating which ones are configured as
    DEFAULT and FAST for this server. Use to verify your setup or choose a model to set
    via OLLAMA_MODEL / OLLAMA_FAST_MODEL env vars."""
    models = list_models()
    if not models:
        return _UNAVAILABLE

    lines = ["Available Ollama models:"]
    for m in models:
        tags: list[str] = []
        if m == DEFAULT_MODEL:
            tags.append("DEFAULT")
        if m == FAST_MODEL and FAST_MODEL != DEFAULT_MODEL:
            tags.append("FAST")
        tag_str = f"  [{', '.join(tags)}]" if tags else ""
        lines.append(f"  {m}{tag_str}")
    lines.append("")
    lines.append(f"OLLAMA_MODEL      = {DEFAULT_MODEL}")
    lines.append(f"OLLAMA_FAST_MODEL = {FAST_MODEL}")
    lines.append(f"OLLAMA_BASE_URL   = {os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')}")
    return "\n".join(lines)


# ── v1.1 expansion: high-context compression + smart reading ──────────────


@mcp.tool()
def local_compress_log(file_path: str, level: str = "", since: str = "") -> str:
    """Compress a log file to its essential signal: grouped errors, key events, anomalies.

    level: filter by log level, case-insensitive (e.g. 'ERROR', 'WARN', 'CRITICAL').
           Empty = include all levels.
    since: filter to lines containing this timestamp prefix (e.g. '2026-04-13', '14:30').
           Empty = include all lines.

    Log files are the single highest-token-waste input in most codebases.
    A 5 MB nginx or application log becomes a 500-token summary with all
    actionable information preserved."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err

    filter_lines: list[str] = []
    for line in content.splitlines():
        if level and level.upper() not in line.upper():
            continue
        if since and since not in line:
            continue
        filter_lines.append(line)

    if not filter_lines:
        return f"[localthink] No lines matched filters (level={level!r}, since={since!r})"

    filtered = "\n".join(filter_lines)
    return generate(prompt=filtered, system=LOG_COMPRESS_SYSTEM)


@mcp.tool()
def local_compress_stack_trace(text: str) -> str:
    """Compress a stack trace (plus any associated source context) to its essential signal.

    Returns: root cause, failure point (file/function/line), 3-5 key frames, fix hint.

    Stack traces with source context commonly run 2-5K tokens for ~50 tokens of signal.
    Paste the full trace as text — works with Python, JS, Java, Go, Rust, and others."""
    if not health_check():
        return _UNAVAILABLE
    return generate(prompt=text, system=STACK_TRACE_SYSTEM)


@mcp.tool()
def local_compress_data(data: str, keep_fields: list[str] = [], question: str = "") -> str:
    """Compress a structured data payload: JSON objects, CSV rows, API responses.

    keep_fields: if provided, all other fields are stripped from the output.
    question:    if provided, answers it in 1-3 sentences before the compressed data.

    Examples of what this saves:
    - A REST API response with 50 fields and nested arrays: 8KB → 400 tokens
    - A CSV export with 500 rows: sampled to 3 representative rows + row count
    - A deeply nested config object: flattened to used keys only"""
    if not health_check():
        return _UNAVAILABLE
    fields_line = f"Keep only these fields: {', '.join(keep_fields)}\n\n" if keep_fields else ""
    question_line = f"Question to answer first: {question}\n\n" if question else ""
    prompt = f"{fields_line}{question_line}{data}"
    return generate(prompt=prompt, system=DATA_COMPRESS_SYSTEM)


@mcp.tool()
def local_session_compress(file_path: str) -> str:
    """Compress a saved conversation transcript to a compact re-entry briefing.

    Reads the conversation from a file and returns a structured briefing with:
    context, decisions made, current state, open items, key constraints.

    This is the recursive meta-tool: use it to restart a long Claude Code session
    with a fresh context window while retaining everything that matters.

    Usage pattern:
      1. Export/save your current session transcript to a file.
      2. Call local_session_compress(file_path) — the transcript never enters Claude's context.
      3. Start a new session and seed it with the returned briefing."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    return generate(prompt=content, system=SESSION_COMPRESS_SYSTEM)


@mcp.tool()
def local_prompt_compress(text: str) -> str:
    """Compress a long CLAUDE.md, system prompt, or instruction document to its minimal form.

    Preserves every unique directive. Removes: duplicate rules, verbose explanations,
    illustrative examples that repeat (not illustrate) a point. Target: 20-40% of original.

    Use when a CLAUDE.md or project instruction file has grown unwieldy — the compressed
    version is functionally equivalent but costs a fraction of the tokens per session."""
    if not health_check():
        return _UNAVAILABLE
    return generate(prompt=text, system=PROMPT_COMPRESS_SYSTEM)


@mcp.tool()
def local_symbols(file_path: str) -> str:
    """Extract a complete symbol table from a source file: every named definition with
    its line number and a one-line description.

    Returns: one line per symbol — type, name, (line N), description.
    Covers: functions, classes, methods, constants, variables, type aliases, decorators.

    Use before reading a large file to know exactly what it contains and which line
    to jump to — without loading the full file into context."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    numbered = _number_lines(content)
    return generate_fast(prompt=numbered, system=SYMBOLS_SYSTEM)


@mcp.tool()
def local_find_impl(file_path: str, spec: str) -> str:
    """Find the code that implements a natural-language specification — returns the actual
    code with line numbers, without loading the entire file into Claude's context.

    spec: plain English description of what you're looking for.

    Examples:
      'the function that validates email addresses'
      'where the JWT token is verified'
      'the database connection pool initialization'
      'error handler for rate limit exceeded'

    Complements local_grep_semantic (which returns passages) by returning the
    *complete logical unit* (full function / full class) that implements the spec."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    numbered = _number_lines(content)
    prompt = f"Spec: {spec}\n\nSource:\n{numbered}"
    return generate(prompt=prompt, system=FIND_IMPL_SYSTEM)


@mcp.tool()
def local_strip_to_skeleton(file_path: str) -> str:
    """Return a source file with ALL function/method bodies replaced by '...' while
    keeping the full structure: signatures, decorators, type annotations, docstrings
    (first line only), class hierarchy, imports, inter-function comments.

    Different from local_code_surface which extracts just signatures.
    This tool produces a *navigable skeleton* — all the structure, none of the implementation.
    Typically 30-50% of the original file size.

    Works for all languages via the local LLM."""
    if not health_check():
        return _UNAVAILABLE
    content, err = _read_file(file_path)
    if err:
        return err
    return generate(prompt=content, system=SKELETON_SYSTEM)


@mcp.tool()
def local_translate(text: str, target_format: str) -> str:
    """Convert content between technical formats without loading it into Claude's context.

    Supported conversions:
      json → yaml / yaml → json / toml → yaml / yaml → toml / json → toml
      csv → markdown_table / markdown_table → csv
      code → pseudocode
      sql → english (natural language description of a query)
      env → json (environment variable file → JSON object)
      typescript_types → json_schema

    The entire source document stays local. Only the converted output enters context.
    Use when you need to compare or edit configs in a different format."""
    if not health_check():
        return _UNAVAILABLE
    prompt = f"Convert to: {target_format}\n\n{text}"
    return generate_fast(prompt=prompt, system=TRANSLATE_SYSTEM)


@mcp.tool()
def local_schema_infer(data: str) -> str:
    """Infer a compact schema from sample data: JSON, CSV, YAML, or API response samples.

    Returns a JSON Schema (draft-07 subset) identifying types, required vs optional fields,
    format hints (uuid, date-time, uri), and array item structure.

    API response samples commonly have a 100:1 data-to-schema ratio. Use this to
    understand the shape of data without keeping large samples in context."""
    if not health_check():
        return _UNAVAILABLE
    return generate_fast(prompt=data, system=SCHEMA_INFER_SYSTEM)


@mcp.tool()
def local_timeline(text: str) -> str:
    """Extract a chronological event sequence from any document: logs, changelogs,
    commit messages, incident reports, git log output.

    Returns a structured timeline with timestamps (or relative ordering) and a source
    reference for each event. Deduplicates repeated events.

    Use for: debugging incident timelines, understanding changelog history,
    reconstructing what happened in a log without reading the whole file."""
    if not health_check():
        return _UNAVAILABLE
    return generate_fast(prompt=text, system=TIMELINE_SYSTEM)


@mcp.tool()
def local_diff_files(path_a: str, path_b: str, focus: str = "") -> str:
    """Summarize meaningful changes between two files — neither file is loaded into
    Claude's context.

    Reads both files locally, sends them to the local LLM, and returns a structured
    diff summary: additions, removals, changes, and impact.

    focus: optional topic to prioritize (e.g. 'auth', 'breaking changes', 'security').

    Differs from local_diff which takes text already in context — this tool is for
    when you have two files on disk you want to compare without loading either."""
    if not health_check():
        return _UNAVAILABLE
    content_a, err_a = _read_file(path_a)
    if err_a:
        return err_a
    content_b, err_b = _read_file(path_b)
    if err_b:
        return err_b

    focus_line = f"Focus on changes related to: {focus}\n\n" if focus else ""
    prompt = f"{focus_line}=== {path_a} ===\n{content_a}\n\n=== {path_b} ===\n{content_b}"
    return generate(prompt=prompt, system=DIFF_SYSTEM)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
