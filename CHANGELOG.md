# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

## [1.1.0] — 2026-04-13

### Added

**File operations (new ways to read without loading into context):**
- `local_shrink_file(file_path, focus?)` — Read a file and return a compressed version of its *content* rather than an answer. Use this when you need to hold a dense reference in Claude's context for multiple subsequent questions or edits.
- `local_batch_answer(file_paths, question)` — Answer the same question across a list of files in a single call. Ideal for bulk scanning ("does this file have hardcoded credentials?").
- `local_scan_dir(dir_path, pattern, question?, max_files?)` — Walk a directory, match files by glob pattern, and summarize or query each one. None of the files enter Claude's context.

**Composition tools (fewer round-trips):**
- `local_pipeline(text, steps)` — Chain multiple ops in one call. Each step's output feeds the next. Steps: `summarize`, `extract`, `answer`. Up to 5 steps. Eliminates multiple back-and-forth round-trips for predictable multi-stage workflows.
- `local_auto(input, question?)` — Meta-tool: auto-detects whether input is a file path or raw text, auto-selects the right operation, and for large docs automatically extract-then-answers. Zero decision overhead.

**Stateful document chat:**
- `local_chat(document, message, history?)` — Multi-turn Q&A where the document is compressed on first call and stays with Ollama across turns. Claude holds only the conversation history (growing small) and the compressed doc. The original document never enters Claude's context window.

**Semantic / structural tools:**
- `local_grep_semantic(file_path, meaning, max_results?)` — Find passages in a file that match a *concept*, not a literal string. Like grep but concept-level. The file is never loaded into Claude's context.
- `local_outline(text)` — Generate a structural table of contents with line ranges from a document. Returns structure only (no content). Use before `local_extract` to know which section to pull.
- `local_code_surface(file_path)` — Extract the public API skeleton from a source file. Python files use the stdlib `ast` module (no Ollama, instant, deterministic). Other languages use the fast model. Typically 5-10% of original size.

**Analysis / meta tools:**
- `local_classify(text)` — Classify content type (code/docs/config/logs/etc.) and recommend the best tool. Returns JSON. Use before processing large docs or for programmatic routing in hooks/scripts.
- `local_audit(file_path, checklist)` — Check a file against a list of criteria. Returns PASS / FAIL / PARTIAL / N/A per item. File never enters Claude's context.
- `local_models()` — List all locally available Ollama models, annotated with which are configured as DEFAULT and FAST.

**Model routing:**
- New `OLLAMA_FAST_MODEL` env var for lightweight tools (`local_classify`, `local_outline`, `local_code_surface` on non-Python). Falls back to `OLLAMA_MODEL` if unset.
- Increased default timeout: 90s → 120s to handle larger documents reliably.

**High-context compression (the biggest token-burn scenarios):**
- `local_compress_log(file_path, level?, since?)` — Compress a log file to its essential signal: grouped errors (with occurrence counts), key events (startup/restart/deploy), and anomalies. Optional level and timestamp-prefix filters. Turns 5 MB logs into 500-token summaries.
- `local_compress_stack_trace(text)` — Distil a stack trace (plus any embedded source) to: root cause (one sentence), failure point (file/function/line), 3-5 key frames, fix hint. Eliminates the 2-5K tokens of framework boilerplate that stack traces typically carry.
- `local_compress_data(data, keep_fields?, question?)` — Compress JSON objects, CSV exports, and API responses. Strips null/empty fields, samples large arrays with item counts, keeps IDs and status codes. REST API responses commonly shrink 20:1. Optional `question` gets answered inline before the compressed data.
- `local_session_compress(file_path)` — **Recursive meta-tool**: compress a saved Claude conversation transcript to a re-entry briefing (context, decisions made, current state, open items, constraints). The transcript never enters Claude's context. Use to restart a long session with a fresh window while retaining everything that matters.
- `local_prompt_compress(text)` — Compress a long CLAUDE.md, system prompt, or instruction document to its minimal directive set. Preserves every unique rule; removes duplicates, verbose explanations, and redundant examples. Target: 20-40% of original length.

**Smart reading (avoid loading files at all):**
- `local_symbols(file_path)` — Extract a full symbol table: every named definition with type, line number, and a one-line description. One line per symbol. Use before reading a large file to know what's in it and which line to jump to.
- `local_find_impl(file_path, spec)` — Find the code that implements a natural-language spec inside a file, without reading the whole file. Returns the complete logical unit (full function or class) with line numbers. Example: `spec="where JWT token is verified"`.
- `local_strip_to_skeleton(file_path)` — Return a file with all function/method bodies replaced by `...` while keeping the full structure: signatures, decorators, type annotations, docstrings (first line), class hierarchy, inter-function comments. Distinct from `local_code_surface` (which drops docstrings/comments entirely). Typically 30-50% of original size.

**Format transformation:**
- `local_translate(text, target_format)` — Convert between technical formats without loading the source into Claude's context: `json↔yaml↔toml`, `csv→markdown_table`, `code→pseudocode`, `sql→english`, `env→json`. The entire source stays local.
- `local_schema_infer(data)` — Infer a compact JSON Schema (draft-07) from a sample data payload. API response samples commonly have a 100:1 data-to-schema ratio; this turns the sample into a ~50-line schema.

**Temporal analysis & multi-file diff:**
- `local_timeline(text)` — Extract a chronological event sequence from logs, changelogs, git log output, or incident reports. Returns a structured timeline with timestamps (or relative ordering) and deduplicates repeated events.
- `local_diff_files(path_a, path_b, focus?)` — Diff two files by path, with neither file loaded into Claude's context. Counterpart to `local_diff` (which takes in-context text). Produces the same structured diff: additions, removals, changes, impact.

### Changed
- `ollama_client.py` — added `generate_fast()`, `list_models()`, `FAST_MODEL` constant
- `prompts.py` — added 19 new system prompts for v1.1 tools (11 new in expansion batch); v0.1.0 prompts unchanged

## [0.1.0] — 2026-04-12

### Added
- `local_answer(file_path, question)` — Q&A against a file without loading it into Claude's context (~30× token savings on 16KB files)
- `local_summarize(text, focus?)` — compress large text blocks while preserving API names, signatures, error strings, and config keys
- `local_extract(text, query)` — return verbatim cited passages relevant to a query
- Ollama backend via `httpx` with configurable `OLLAMA_BASE_URL` and `OLLAMA_MODEL` env vars
- Graceful degradation when Ollama is not running
- PyPI packaging with `uvx` support — `claude mcp add localthink -- uvx localthink-mcp`
