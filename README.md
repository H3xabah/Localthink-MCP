# localthink-mcp

**Local LLM context compression for Claude Code.**
Offloads large file queries and document processing to Ollama so they never burn Claude's context window.

> v0.1.0 benchmarked at **~30× token savings** on 16 KB file queries.
> v1.1 adds 13 new tools covering every major token-waste pattern.
> v1.2 adds **pre-injection**: `local_improve_prompt` and `local_preplan` run locally *before* Claude sees the task — sharpening prompts and scaffolding plans so Claude executes rather than guesses.
> v2.1 adds **smart buffer**, **execution filters**, **session scratchpad**, **persistent notes**, **response refinement**, and a **disk-backed result cache** — 14 new tools, 45 total.
> v2.2 adds the **tiered CLAUDE.md system** — switch between Full/Half/Quarter instruction sets with one command, replacing the old 102-line monolith with 12–55 lines depending on tier.

---

## Quick start

```bash
# 1. Pull models for your hardware (example: 10-12 GB VRAM)
ollama pull qwen2.5:14b-instruct-q4_K_M   # MAIN — deep ops
ollama pull qwen2.5:3b                     # FAST + TINY — lightweight/instant ops

# 2. Register with Claude Code — models set inline, no config editing
claude mcp add localthink \
  --env OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M" \
  --env OLLAMA_FAST_MODEL="qwen2.5:3b" \
  --env OLLAMA_TINY_MODEL="qwen2.5:3b" \
  -- uvx localthink-mcp

# Windows:
# claude mcp add --transport stdio localthink ^
#   --env OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M" ^
#   --env OLLAMA_FAST_MODEL="qwen2.5:3b" ^
#   --env OLLAMA_TINY_MODEL="qwen2.5:3b" ^
#   -- cmd /c uvx localthink-mcp

# 3. Set your CLAUDE.md instruction tier
cp -r claude-md/ ~/.claude/localthink/
python ~/.claude/localthink/set-tier.py full

# 4. Verify
claude mcp list   # localthink → Connected
```

See [SETUP.md](SETUP.md) for per-hardware pull commands across all tiers (CPU to 48 GB+ GPU). Fine-tune any setting live with `local_config` — no file editing.

---

## Tiered CLAUDE.md Instructions

Instead of pasting a 102-line monolith into `CLAUDE.md`, pick a tier:

| Tier | Lines in CLAUDE.md | Tools | Best for |
|------|--------------------|-------|----------|
| `full` | ~55 | All 45 | Complex projects, new codebases, research-heavy sessions |
| `half` | ~30 | ~18 | Day-to-day dev: file nav + CI filters |
| `quarter` | ~12 | ~6 | Minimal — just stop Claude loading big files |

```bash
python ~/.claude/localthink/set-tier.py full     # switch to full
python ~/.claude/localthink/set-tier.py half     # switch to half
python ~/.claude/localthink/set-tier.py          # show current tier
```

See [`claude-md/`](claude-md/) and [`CLAUDE_MD_TEMPLATE.md`](CLAUDE_MD_TEMPLATE.md) for full documentation.

---

## Requirements

- [Ollama](https://ollama.ai) installed and running (`ollama serve`)
- [Claude Code](https://claude.ai/code) CLI
- Python 3.10+

---

## All 45 tools

### v0.1.0 — Core compression

| Tool | When to use |
|------|-------------|
| `local_answer(file_path, question)` | Query a large file without loading it into context |
| `local_summarize(text, focus?)` | Compress a large text blob already in context |
| `local_extract(text, query)` | Pull only the cited passages you need from a document |

### v1.1 — New routes

#### File operations
| Tool | What it does |
|------|--------------|
| `local_shrink_file(file_path, focus?)` | Read a file → return compressed *content* (not an answer). Hold the compressed version in context for repeated reference. |
| `local_batch_answer(file_paths, question)` | Answer one question across many files in a single call. No files enter Claude's context. |
| `local_scan_dir(dir_path, pattern, question?, max_files?)` | Walk a directory, summarize or query every matching file. Glob pattern support (`**/*.ts`, `config/*.yaml`). |

#### Composition (fewer round-trips)
| Tool | What it does |
|------|--------------|
| `local_pipeline(text, steps)` | Chain `summarize` → `extract` → `answer` in one call. Up to 5 steps. Eliminates back-and-forth for predictable multi-stage workflows. |
| `local_auto(input, question?)` | Meta-tool: detects file path vs text, picks the right op, handles large docs with auto extract-then-answer. Zero decision overhead. |

#### Stateful document chat
| Tool | What it does |
|------|--------------|
| `local_chat(document, message, history?)` | Multi-turn Q&A. Document is compressed on first call and stays with Ollama. Claude holds only conversation history — the original doc never enters Claude's window. |

#### Semantic & structural
| Tool | What it does |
|------|--------------|
| `local_grep_semantic(file_path, meaning, max_results?)` | Find passages matching a *concept*, not a literal string. "Find where rate limiting is enforced" works even if the word "rate" isn't there. |
| `local_outline(text)` | Structural table of contents with line ranges — no content returned. Use before `local_extract` to find the right section. |
| `local_code_surface(file_path)` | Public API skeleton. **Python: pure AST (no Ollama, instant).** Other languages: fast LLM. Typically 5-10% of original size. |

#### Analysis / meta
| Tool | What it does |
|------|--------------|
| `local_classify(text)` | Classify content type + recommend the best tool. Returns JSON. Use for programmatic routing in hooks/scripts. |
| `local_audit(file_path, checklist)` | Checklist-based file audit: PASS / FAIL / PARTIAL / N/A per item. File never enters Claude's context. |
| `local_models()` | List local Ollama models and show current DEFAULT / FAST model config. |

### v1.2 — Pre-injection (run before Claude thinks)

These tools run a local model pass *before* Claude engages with a task. Claude never sees the raw input — only the pre-processed output. Eliminates waste at the source rather than compressing after the fact.

| Tool | What it does |
|------|--------------|
| `local_improve_prompt(prompt, context?)` | Rewrite a vague or rough prompt into a clear, specific, unambiguous version. Claude receives only the sharpened result. Uses the fast model — minimal overhead. |
| `local_preplan(task, context?, depth?)` | Generate a structured implementation plan (goal / assumptions / ordered steps / risks / open questions) via local model. Claude executes the scaffold rather than planning from scratch. `depth`: `"quick"` (3-5 steps), `"standard"` (default), `"detailed"` (sub-bullets + rationale). |

**`local_improve_prompt` example:**
```
"make the auth faster"
→ local_improve_prompt(prompt, context="Next.js, JWT, DB bottleneck suspected")
→ "Optimise JWT validation latency in src/auth/middleware.ts — profile the verify()
   hot path, remove redundant DB round-trips, target p95 < 5 ms."
→ Feed that to Claude as the actual task
```

**`local_preplan` example:**
```python
plan = local_preplan(
  task="add rate limiting to the API",
  context="Express.js, Redis available, routes in src/routes/",
  depth="standard"
)
# Returns: Goal / Assumptions / Steps with file paths / Risks / Open questions
# Then: "Execute this plan: <plan>"
```

### v1.1 expansion — high-context compression + smart reading

#### High-context compression
| Tool | What it does |
|------|--------------|
| `local_compress_log(file_path, level?, since?)` | Compress a log file to its essential signal. Groups repeated errors with counts, extracts key events, surfaces anomalies. Optional level (`ERROR`/`WARN`) and timestamp-prefix filters. Turns 5 MB logs into ~500-token summaries. |
| `local_compress_stack_trace(text)` | Distil a stack trace (+ source context) to: root cause, failure point, 3-5 key frames, fix hint. Eliminates framework boilerplate that inflates traces to thousands of tokens. |
| `local_compress_data(data, keep_fields?, question?)` | Compress JSON objects, CSV exports, and API responses. Strips nulls, samples large arrays, keeps IDs/status codes. REST responses commonly shrink 20:1. |
| `local_session_compress(file_path)` | **Recursive meta-tool.** Compress a saved Claude conversation transcript to a re-entry briefing: context, decisions, current state, open items, constraints. The transcript never enters Claude's context. |
| `local_prompt_compress(text)` | Compress a long CLAUDE.md or system prompt to its minimal directive set. Preserves every unique rule; removes duplicates and verbose prose. |

#### Smart reading (avoid loading files at all)
| Tool | What it does |
|------|--------------|
| `local_symbols(file_path)` | Full symbol table: every definition with type, line number, and one-line description. Replaces "read file to see what's in it." |
| `local_find_impl(file_path, spec)` | Natural-language code search inside a file. Returns the complete matching logical unit with line numbers. E.g. `spec="where JWT token is verified"`. |
| `local_strip_to_skeleton(file_path)` | All function bodies → `...`, everything else preserved (docstrings, decorators, type annotations, comments). Typically 30-50% of original. |

#### Format transformation
| Tool | What it does |
|------|--------------|
| `local_translate(text, target_format)` | Convert formats without loading source into context: `json↔yaml↔toml`, `csv→markdown_table`, `code→pseudocode`, `sql→english`, `env→json`. |
| `local_schema_infer(data)` | Sample data → compact JSON Schema (draft-07). API samples are often 100:1 data-to-schema ratio. |

#### Temporal & multi-file diff
| Tool | What it does |
|------|--------------|
| `local_timeline(text)` | Chronological event sequence from logs, changelogs, git log, or incident reports. Deduplicates repeated events. |
| `local_diff_files(path_a, path_b, focus?)` | Diff two files by path — neither file loaded into context. Counterpart to `local_diff` which takes in-context text. |

### v2.1 — Smart buffer, execution filters, scratchpad, notes, cache

#### Smart Buffer (raw output triage)
| Tool | What it does |
|------|--------------|
| `local_gate(raw_output)` | Triage any raw output (test results, build logs, lint dumps) into Pattern + Anomalies + Signal. Always fits in budget. Use before injecting any raw tool output into context. |
| `local_slice(file_path, offset_lines)` | Read a window of lines from a file at an offset. On-demand raw access when `local_gate` identifies a region worth inspecting. |
| `local_diff_semantic(before, after)` | Meaning-level diff — noise (whitespace, formatting, minor rewording) suppressed. Only semantic changes surface. |

#### Execution Filters (project tools → local LLM)
| Tool | What it does |
|------|--------------|
| `local_run_tests()` | Run the project test suite. Returns only `{failed, delta, pointer}`. Nothing else enters context. |
| `local_run_lint()` | Run the linter. Violations grouped by rule; passing rules suppressed. |
| `local_run_build()` | Run the build. Returns root cause + affected symbols only. |

#### Session Scratchpad (stateful decisions)
| Tool | What it does |
|------|--------------|
| `local_memo_write(section, content)` | Write to a named scratchpad section: `decisions`, `assumptions`, `pitfalls`, `open_questions`. Auto-compacts beyond threshold. |
| `local_memo_read()` | Read the full scratchpad as a distilled summary. Restore context mid-session without re-reading files. |
| `local_memo_checkpoint()` | Freeze scratchpad into a `RESUME_PROMPT` string. Paste after `/clear` to continue with full context. |

#### Persistent Notes (cross-session knowledge)
| Tool | What it does |
|------|--------------|
| `local_note_write(category, content)` | Write a permanent note to disk (`architecture`, `gotcha`, `pattern`). Survives `/clear` and new sessions. |
| `local_note_search(query)` | Full-text search across all persisted notes. Run at session start to surface relevant prior knowledge. |

#### Response Quality & Cache
| Tool | What it does |
|------|--------------|
| `local_refine(prompt, draft, instructions?)` | Post-process an LLM draft through a refinement pass. Optional instructions target tone, brevity, or accuracy. |
| `local_cache_stats()` | Show cache hit/miss counts, entry count, and total disk usage. |
| `local_cache_clear()` | Evict all cached results. |
| `local_config()` | Open the settings GUI — configure all 18 settings across Ollama, Timeouts, Limits, Cache, and Memo. Saves to `~/.localthink-mcp/config.json` and hot-reloads the running server. |

---

## Decision guide

| Situation | Tool |
|-----------|------|
| File > 5 KB, one specific question | `local_answer` |
| File > 5 KB, need to reference it multiple times | `local_shrink_file` |
| Text already in context, want to compress it | `local_summarize` |
| "Find me the part about X" | `local_extract` |
| Need to outline a doc before extracting | `local_outline` → `local_extract` |
| Want to know what's in a code file | `local_symbols` |
| Want to understand a code file's structure | `local_code_surface` |
| Want the full file but bodies stripped | `local_strip_to_skeleton` |
| "Find the function that does X" | `local_find_impl` |
| Multi-step process on the same document | `local_pipeline` |
| Unsure which tool to use | `local_auto` |
| Multiple questions about the same large doc | `local_chat` |
| Same question across 5+ files | `local_batch_answer` |
| Understand what's in a directory | `local_scan_dir` |
| "Find where X is handled" (concept search) | `local_grep_semantic` |
| Security or quality checklist | `local_audit` |
| Unsure of content type before processing | `local_classify` |
| Large log file | `local_compress_log` |
| Stack trace + source context | `local_compress_stack_trace` |
| JSON / CSV / API response payload | `local_compress_data` |
| Session too long, need to restart | `local_session_compress` |
| CLAUDE.md grown too large | `local_prompt_compress` |
| Need JSON as YAML (or any format swap) | `local_translate` |
| Need a schema for sample data | `local_schema_infer` |
| Need a timeline from a log or changelog | `local_timeline` |
| Compare two files without loading them | `local_diff_files` |
| Compare two in-context text blobs | `local_diff` |
| Prompt is vague — sharpen before sending to Claude | `local_improve_prompt` |
| Task is large — plan locally before Claude touches it | `local_preplan` |
| Raw test/build/lint output about to enter context | `local_gate` |
| `local_gate` flagged a specific region worth reading | `local_slice` |
| Two text blobs — want only the meaningful diff | `local_diff_semantic` |
| Run tests without dumping output into context | `local_run_tests` |
| Run lint without dumping output into context | `local_run_lint` |
| Run build without dumping output into context | `local_run_build` |
| Want to record a decision or assumption mid-session | `local_memo_write` |
| Resuming work, need to restore session context | `local_memo_read` |
| About to `/clear` — want to resume with full context | `local_memo_checkpoint` |
| Want to save a pattern or gotcha for future sessions | `local_note_write` |
| Starting a session — check for relevant prior notes | `local_note_search` |
| LLM draft needs a quality pass | `local_refine` |
| Check or clear the result cache | `local_cache_stats` / `local_cache_clear` |
| Change any setting via GUI | `local_config` |

---

## local_pipeline examples

```python
# Extract auth sections, then summarize for security review
local_pipeline(text=big_doc, steps=[
    {"op": "extract",   "query": "authentication and authorization"},
    {"op": "summarize", "focus": "security risks and gotchas"},
])

# Answer a question after narrowing to the relevant section
local_pipeline(text=api_docs, steps=[
    {"op": "extract",  "query": "rate limiting"},
    {"op": "answer",   "question": "what headers control retry behaviour?"},
])
```

## local_chat example

```python
# Turn 1 — document is compressed automatically
r = local_chat(full_doc, "What does this library do?", "")
# r["doc"]     = compressed version (hold this)
# r["history"] = conversation so far (hold this)
# r["answer"]  = the answer

# Turn 2 — pass compressed doc + history back
r = local_chat(r["doc"], "How do I configure auth?", r["history"])

# Turn 3
r = local_chat(r["doc"], "Show me the relevant config keys", r["history"])
```

---

## Configuration

### Using the Settings Editor

The fastest way to configure LocalThink is the built-in settings GUI. Type this in Claude Code:

```
local_config
```

A desktop window opens immediately — no terminal, no JSON editing.

**What you'll see:**

| Tab | Settings inside |
|-----|----------------|
| **Ollama** | Base URL · Default model · Fast model · Tiny model |
| **Timeouts** | Main timeout · Fast timeout · Tiny timeout · Health check · code_surface timeout |
| **Limits** | Max file bytes · Max pipeline steps · Max scan files · Classify sample size · Batch concurrency |
| **Cache** | Cache directory · Cache TTL (days) |
| **Memo** | Memo directory · Compact threshold |

**Status bar** — the bottom of the window shows a live Ollama probe: a green dot with your model count means Ollama is reachable. Red dot means it's not running (`ollama serve` to fix).

**Model dropdowns** — the Ollama tab auto-populates model fields with every model currently pulled on your machine. You can also type a model name directly.

**Directory fields** — Cache directory and Memo directory have a Browse button that opens a folder picker.

**Buttons:**

| Button | What it does |
|--------|-------------|
| **Save** | Writes `~/.localthink-mcp/config.json` and hot-reloads the server — most changes apply instantly |
| **Reset Tab** | Restores all fields in the current tab to their built-in defaults (does not save) |
| **Cancel** | Closes without saving any changes |

**What applies instantly vs what needs a restart:**

- Instant (no restart needed): timeouts, limits, cache settings, memo settings
- Requires restarting the MCP server: Ollama Base URL, Default model, Fast model, Tiny model

To restart after a model change: open the MCP panel in Claude Code (`/mcp`) and reconnect, or close and reopen Claude Code.

---

Settings are saved to `~/.localthink-mcp/config.json`. You can also set any value manually as an env var (env vars take priority over the config file).

### Ollama

| Env var | Default | Recommended |
|---------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Change only if Ollama runs on a remote machine or non-default port |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct-q4_K_M` | Match your VRAM tier — see SETUP.md for the full table |
| `OLLAMA_FAST_MODEL` | *(same as MODEL)* | One tier smaller than the default (e.g. `qwen2.5:7b` if default is `14b`). Used by classify, outline, translate, schema_infer |
| `OLLAMA_TINY_MODEL` | *(same as FAST)* | `qwen2.5:3b` or smaller. Used by trivial ops on small inputs |

### Timeouts

| Env var | Default | Recommended |
|---------|---------|-------------|
| `LOCALTHINK_TIMEOUT` | `360` | `360` for 14b models · `600` for 32b+ · `120` for 7b on fast GPU |
| `LOCALTHINK_FAST_TIMEOUT` | `180` | `60`–`180` — fast model calls should be quick |
| `LOCALTHINK_TINY_TIMEOUT` | `60` | Rarely needs changing |
| `LOCALTHINK_HEALTH_TIMEOUT` | `2` | Leave at `2` — this is just an Ollama ping |
| `LOCALTHINK_CODE_SURFACE_TIMEOUT` | `600` | Increase to `900` for large TS/Go/Rust files on slow hardware |

### Limits

| Env var | Default | Recommended |
|---------|---------|-------------|
| `LOCALTHINK_MAX_FILE_BYTES` | `200000` | `200000` (~200 KB) is right for most codebases · increase to `500000` for monorepos with giant files |
| `LOCALTHINK_MAX_PIPELINE_STEPS` | `5` | Leave at `5` unless you're building complex custom pipelines |
| `LOCALTHINK_MAX_SCAN_FILES` | `20` | Increase to `50`–`100` for large directory scans; watch memory |
| `LOCALTHINK_CLASSIFY_SAMPLE` | `8000` | `8000` chars is enough for most inputs — rarely needs changing |
| `LOCALTHINK_MAX_CONCURRENCY` | `4` | `1`–`2` on low VRAM · `4` default · `6`–`8` if Ollama handles parallel slots well |

### Cache

| Env var | Default | Recommended |
|---------|---------|-------------|
| `LOCALTHINK_CACHE_DIR` | `~/.cache/localthink-mcp` | Change if the default drive is low on space |
| `LOCALTHINK_CACHE_TTL_DAYS` | `30` | `7` if disk space is tight · `90` if you want long-lived results across projects |

### Memo / Notes

| Env var | Default | Recommended |
|---------|---------|-------------|
| `LOCALTHINK_MEMO_DIR` | `~/.localthink-mcp` | Point to a synced folder (Dropbox, OneDrive) to share notes across machines |
| `LOCALTHINK_COMPACT_THRESHOLD` | `3000` | `1500` for faster reads · `5000` to preserve more raw content before auto-compact |

### Example: 3-tier model setup

```bash
# Pass models inline at registration — no file editing needed
claude mcp add localthink \
  --env OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M" \
  --env OLLAMA_FAST_MODEL="qwen2.5:7b-instruct-q4_K_M" \
  --env OLLAMA_TINY_MODEL="qwen2.5:3b" \
  -- uvx localthink-mcp
```

Change models any time with `local_config` (Ollama tab → Save → reconnect MCP).

---

## Install options

### uvx (recommended — zero setup)

```bash
claude mcp add localthink \
  --env OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M" \
  --env OLLAMA_FAST_MODEL="qwen2.5:3b" \
  --env OLLAMA_TINY_MODEL="qwen2.5:3b" \
  -- uvx localthink-mcp
```

### pip

```bash
pip install localthink-mcp
claude mcp add localthink \
  --env OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M" \
  --env OLLAMA_FAST_MODEL="qwen2.5:3b" \
  --env OLLAMA_TINY_MODEL="qwen2.5:3b" \
  -- localthink-mcp
```

### Windows — if `uvx` isn't on Claude's PATH

```bash
claude mcp add --transport stdio localthink ^
  --env OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M" ^
  --env OLLAMA_FAST_MODEL="qwen2.5:3b" ^
  --env OLLAMA_TINY_MODEL="qwen2.5:3b" ^
  -- cmd /c uvx localthink-mcp
```

Substitute models for your hardware — see [SETUP.md](SETUP.md) for the full tier table.

---

## Security

- **Local only** — runs as a stdio child process, never exposed to the network.
- **`local_answer` / `local_shrink_file` / `local_audit` read any path your shell can access.** Same trust level as Claude's built-in `Read` tool.
- **Ollama has no auth by default.** Don't expose port `11434` to the internet.
- **No data leaves your machine.** All inference is local.

---

## Troubleshooting

**`[localthink] Ollama is not running`**
```bash
ollama serve
curl http://localhost:11434/api/tags
```

**Slow responses**
Switch to a smaller model or set a fast model:
```bash
OLLAMA_MODEL=qwen2.5:7b-instruct claude
```

**Windows: `uvx` not found**
Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then retry. Or use `cmd /c uvx` fallback.

---

## License

MIT © 2026 [H3xabah](https://github.com/H3xabah)
