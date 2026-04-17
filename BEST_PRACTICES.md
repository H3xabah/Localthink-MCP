# localthink-mcp Best Practices
> v2.1 — 45 tools · caching · parallel batch · multi-pass · 3-tier models · smart buffer · scratchpad · settings GUI

---

## 1. Locking Tool Usage in CLAUDE.md

Paste the block from `CLAUDE_MD_TEMPLATE.md` into `~/.claude/CLAUDE.md` (global) or a project `CLAUDE.md`.
This makes Claude route through localthink automatically without being asked.

---

## 2. Configuration

**Quickest path:** call `local_config` from Claude Code — a GUI opens with all 18 settings organised into tabs. Changes are saved to `~/.localthink-mcp/config.json` and take effect immediately (Ollama URL/model changes require a server restart).

**Manual env vars** (for CI or when the GUI isn't available):

#### Ollama

| Variable | Default | What to set |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Remote Ollama: `http://192.168.1.x:11434` |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct-q4_K_M` | Match your VRAM tier — see SETUP.md |
| `OLLAMA_FAST_MODEL` | *(same as MODEL)* | One tier smaller than MODEL — used for classify, outline, translate |
| `OLLAMA_TINY_MODEL` | *(same as FAST)* | Smallest fast model, e.g. `qwen2.5:3b` — used for trivial ops |

#### Timeouts (seconds)

| Variable | Default | When to change |
|---|---|---|
| `LOCALTHINK_TIMEOUT` | `360` | Raise to `600` for 32b+ models; lower to `120` for 7b on fast GPU |
| `LOCALTHINK_FAST_TIMEOUT` | `180` | `60`–`180` is right for fast model calls |
| `LOCALTHINK_TINY_TIMEOUT` | `60` | Rarely needs changing |
| `LOCALTHINK_HEALTH_TIMEOUT` | `2` | Leave as-is — just an Ollama ping |
| `LOCALTHINK_CODE_SURFACE_TIMEOUT` | `600` | Raise to `900` for large TS/Go/Rust on slow hardware |

#### Limits

| Variable | Default | When to change |
|---|---|---|
| `LOCALTHINK_MAX_FILE_BYTES` | `200000` | Raise to `500000` for monorepos with giant files |
| `LOCALTHINK_MAX_PIPELINE_STEPS` | `5` | Leave unless you build custom multi-step pipelines |
| `LOCALTHINK_MAX_SCAN_FILES` | `20` | Raise to `50`–`100` for large directory scans |
| `LOCALTHINK_CLASSIFY_SAMPLE` | `8000` | Rarely needs changing |
| `LOCALTHINK_MAX_CONCURRENCY` | `4` | `1`–`2` on low VRAM · `6`–`8` if Ollama handles parallel slots |

#### Cache

| Variable | Default | When to change |
|---|---|---|
| `LOCALTHINK_CACHE_DIR` | `~/.cache/localthink-mcp` | Point to a different drive if default is low on space |
| `LOCALTHINK_CACHE_TTL_DAYS` | `30` | `7` if tight on disk · `90` for long-running projects |

#### Memo / Notes

| Variable | Default | When to change |
|---|---|---|
| `LOCALTHINK_MEMO_DIR` | `~/.localthink-mcp` | Synced folder (Dropbox, OneDrive) to share notes across machines |
| `LOCALTHINK_COMPACT_THRESHOLD` | `3000` | `1500` for faster reads · `5000` to keep more raw notes before compact |

**3-tier setup:**
```bash
export OLLAMA_MODEL="qwen2.5:14b-instruct-q4_K_M"
export OLLAMA_FAST_MODEL="qwen2.5:7b-instruct-q4_K_M"
export OLLAMA_TINY_MODEL="qwen2.5:3b"
```

---

## 3. Tool Selection Quick Reference

| Goal | Tool | Notes |
|---|---|---|
| Read large file without loading it | `local_answer(file, question)` | Cached by file mtime |
| Compress file for repeated use | `local_shrink_file(file)` | Hold result in context |
| List all definitions in a file | `local_symbols(file)` | Line numbers included |
| Find a specific function | `local_find_impl(file, "spec")` | Plain English spec |
| Get public API only | `local_code_surface(file)` | Python: instant via AST |
| Scan a whole directory | `local_scan_dir(dir, "*.py")` | Parallel, cached per-file |
| Same question across many files | `local_batch_answer([files], q)` | Parallel |
| Summarize anything | `local_summarize(text)` | 20-30% of input |
| Extract relevant passages | `local_extract(text, query)` | Verbatim citations |
| Full structure, no bodies | `local_strip_to_skeleton(file)` | Signatures + docstrings |
| Semantic search within a file | `local_grep_semantic(file, meaning)` | Natural language |
| Compare two versions | `local_diff_files(a, b)` | Neither enters context |
| Audit against a checklist | `local_audit(file, checklist)` | PASS/FAIL/PARTIAL |
| Classify unknown content | `local_classify(text)` | JSON output |
| Get document structure | `local_outline(text)` | TOC with line ranges |
| Find events in a log | `local_timeline(text)` | Chronological, deduped |
| Infer data schema | `local_schema_infer(data)` | JSON Schema output |
| Convert JSON↔YAML↔TOML | `local_translate(text, format)` | Lossless |
| Compress a log file | `local_compress_log(file)` | < 5% of input lines |
| Compress a stack trace | `local_compress_stack_trace(text)` | Root cause + 3-5 frames |
| Compress API response data | `local_compress_data(data)` | Sampled + stripped |
| Compress a saved session | `local_session_compress(file)` | Re-entry briefing |
| Compress a system prompt | `local_prompt_compress(text)` | 20-40% of original |
| Sharpen a vague prompt | `local_improve_prompt(prompt)` | Claude sees clean version only |
| Pre-generate a task plan | `local_preplan(task, context)` | Claude executes, doesn't plan |
| Refine any output | `local_refine(text, goal)` | Multi-pass polishing |
| Multi-turn doc Q&A | `local_chat(doc, message, history)` | Doc compressed once |
| Chain multiple ops | `local_pipeline(text, steps)` | No round-trips |
| Not sure which tool | `local_auto(input, question)` | Auto-selects + routes |
| Compress raw tool output | `local_gate(raw_output)` | Phase 1, always fits budget |
| Raw file window on demand | `local_slice(file, offset, window)` | Call only when needed |
| Meaning-only code diff | `local_diff_semantic(before, after)` | Suppresses whitespace/import noise |
| Run tests, failures only | `local_run_tests(target?, focus?)` | + delta vs last run |
| Run linter, violations only | `local_run_lint(target?)` | Grouped by rule |
| Run build, root cause only | `local_run_build()` | Dep-order, not log-order |
| Write to session scratchpad | `local_memo_write(key, content)` | Survives /clear via checkpoint |
| Read session scratchpad | `local_memo_read(query?, section?)` | ≤ 200 tokens |
| Checkpoint before /clear | `local_memo_checkpoint()` | Returns RESUME_PROMPT |
| Write permanent model note | `local_note_write(category, text)` | Cross-session, never cleared |
| Search past model notes | `local_note_search(query)` | Keyword or semantic scoring |
| Check cache usage | `local_cache_stats()` | Size, TTL, location |
| Clear cache | `local_cache_clear(older_than_days?)` | Full or selective |
| List available models | `local_models()` | Verify server health |
| Open settings GUI | `local_config()` | All 18 settings — Ollama, Timeouts, Limits, Cache, Memo |

---

## 4. The Multi-Pass System

| passes | Behaviour | Good for |
|---|---|---|
| `1` | Single call — default | Most tasks, cached results |
| `2` | Fast draft → main-model refine | Complex Q&A, planning |
| `3` | + fast verify; re-refine if gaps | Security audits, detailed plans |

**Supported tools:** `local_answer`, `local_preplan`, `local_improve_prompt`, `local_audit`, `local_find_impl`, `local_refine`

**Do NOT use passes > 1 for:** cached results · `compress_log/data/summarize` · `local_translate` (deterministic)

```
local_answer("src/auth.py", "how is the JWT validated?", passes=2)
local_preplan("Add rate limiting to API", context="FastAPI, Redis", depth="detailed", passes=2)
```

---

## 5. Caching

Results cached automatically. File-based tools key on mtime; text-based tools key on input hash. TTL: 30 days.

```
local_cache_stats()                    # check usage
local_cache_clear()                    # clear all
local_cache_clear(older_than_days=7)   # selective
```

Clear when: model changed · prompts changed · disk space needed.

---

## 6. Parallel Batch and Scan

`local_batch_answer` and `local_scan_dir` run files concurrently. Total time ≈ slowest file, not sum.

```bash
export LOCALTHINK_MAX_CONCURRENCY=1   # low VRAM / single-slot Ollama
export LOCALTHINK_MAX_CONCURRENCY=8   # if you have headroom
```

---

## 7. Common Recipes

**Onboard a codebase:**
```
local_scan_dir("src", "**/*.py", "what does this file do?")
local_symbols("src/main.py")
local_find_impl("src/main.py", "startup logic")
```

**Debug a failing test:**
```
local_compress_stack_trace(paste_traceback)
local_find_impl("src/module.py", "failing function")
local_answer("tests/test_module.py", "what is this test checking?")
```

**Review a PR diff:**
```
local_diff_files("old.py", "new.py", focus="security")
local_audit("new.py", ["no hardcoded secrets", "input validated", "error handling present"])
```

**Understand a large config:**
```
local_classify(first_500_chars)
local_outline(full_config_text)
local_extract(full_config_text, "database settings")
```

**Compress a bloated session:**
```
# 1. Save/export transcript to session.txt
local_session_compress("session.txt")
# 2. Start new session, paste the briefing at top
```

**Pre-inject a complex task:**
```
local_preplan("Refactor auth middleware to use JWT RS256",
              context="src/middleware/auth.py", passes=2)
# Review plan, then: "Execute this plan: <paste>"
```

**Sharpen a vague prompt:**
```
local_improve_prompt("make the login faster",
                     context="FastAPI app, PostgreSQL, bcrypt hashing")
# Use the sharpened version as your actual task
```

---

## 8. Model Recommendations by Hardware

| VRAM | OLLAMA_MODEL | OLLAMA_FAST_MODEL |
|---|---|---|
| CPU / < 4 GB | `qwen2.5:3b-instruct-q4_K_M` | same |
| 4–6 GB | `qwen2.5:7b-instruct-q4_K_M` | same |
| 8–10 GB | `qwen2.5:14b-instruct-q4_K_M` | `qwen2.5:7b-instruct-q4_K_M` |
| 12–16 GB | `qwen2.5:14b-instruct-q6_K` | `qwen2.5:7b-instruct-q4_K_M` |
| 24 GB+ | `qwen2.5:32b-instruct-q4_K_M` | `qwen2.5:14b-instruct-q4_K_M` |
| Apple M-series | `qwen2.5:14b-instruct-q6_K` | `qwen2.5:7b-instruct-q4_K_M` |

```bash
ollama pull qwen2.5:14b-instruct-q4_K_M
local_models()   # verify
```

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| "Ollama is not running" | `ollama serve` or set `OLLAMA_BASE_URL="http://host:11434"` |
| Stale result after editing file | mtime didn't update — run `local_cache_clear()` |
| Parallel batch slow / errors | `export LOCALTHINK_MAX_CONCURRENCY=1` |
| passes=2/3 too slow | Expected — use passes=1 for cached/routine queries |
| JSON parse errors from classify/schema_infer | Model doesn't support JSON mode — try Qwen 2.5 / Llama 3.1+ / Mistral Nemo+ |
| MCP not connecting | Check `~/.claude/settings.json` · `pip show localthink-mcp` · run `local_models()` |

---

## 10. Settings GUI (`local_config`)

Call `local_config()` from Claude Code to open a tabbed settings window.

```
local_config()
```

**What opens:**

| Tab | Settings |
|-----|----------|
| **Ollama** | Base URL + Test button · Default model · Fast model · Tiny model (all with live dropdown from running Ollama) |
| **Timeouts** | Main (360 s) · Fast (180 s) · Tiny (60 s) · Health check (2 s) · code_surface (600 s) |
| **Limits** | Max file size · Pipeline steps · Scan files · Classify sample · Batch concurrency |
| **Cache** | Cache directory (Browse) · TTL days |
| **Memo** | Memo directory (Browse) · Compact threshold |

**How it works:**
- Live Ollama probe on open — green dot if connected, red if not, shows model count
- Model fields auto-populate from your running Ollama instance
- **Save** → writes `~/.localthink-mcp/config.json` → hot-reloads all module globals immediately
- **Reset Tab** → restores defaults for the active tab only
- **Cancel** → no changes saved
- Limits, Cache, Memo, and Timeout changes take effect immediately — no restart needed
- Ollama URL and model changes require a server restart (Claude Code: `/restart` or re-open)

---

## 11. Full Tool List (v2.1 — 45 tools)

**Core Q&A / Compression:** `local_answer` · `local_summarize` · `local_extract` · `local_shrink_file` · `local_diff` · `local_diff_files` · `local_batch_answer`
**Multi-step:** `local_pipeline` · `local_auto` · `local_chat`
**Code Intelligence:** `local_code_surface` · `local_symbols` · `local_find_impl` · `local_strip_to_skeleton` · `local_grep_semantic`
**Document Analysis:** `local_classify` · `local_outline` · `local_audit` · `local_timeline` · `local_schema_infer` · `local_translate` · `local_scan_dir`
**Compression:** `local_compress_log` · `local_compress_stack_trace` · `local_compress_data` · `local_session_compress` · `local_prompt_compress`
**Pre-injection:** `local_improve_prompt` · `local_preplan` · `local_refine`
**Smart Buffer:** `local_gate` · `local_slice` · `local_diff_semantic`
**Execution Filters:** `local_run_tests` · `local_run_lint` · `local_run_build`
**Scratchpad:** `local_memo_write` · `local_memo_read` · `local_memo_checkpoint`
**Model Notes:** `local_note_write` · `local_note_search`
**Cache / Info:** `local_models` · `local_cache_stats` · `local_cache_clear`
**Settings:** `local_config`

---

## 12. v2.1 Smart Buffer & Scratchpad

### Smart buffer (two-phase output)

Raw test output, build logs, lint dumps must never enter context directly.
1. `local_gate(raw_output)` → Pattern + Anomalies + Signal (always fits in budget)
2. Need the raw window? `local_slice(file, offset_lines, window)` on demand
3. Meaning-only diff: `local_diff_semantic(before, after)` instead of `local_diff`

### Execution filters

- `local_run_tests()` — failures + delta only. `delta: "+0/-2"` = 2 tests newly fixed.
- `local_run_lint()` — violations by rule, relative paths only.
- `local_run_build()` — root cause + affected symbols. Never full build log.

### Session scratchpad

```
local_memo_write("decisions", "Use ruff not flake8 — faster, fewer false positives")
local_memo_write("pitfalls", "cache.py line 44: get() returns None not '' on miss")
local_memo_checkpoint()   # before /clear → copy RESUME_PROMPT → paste after /clear
```

Sections: `decisions` · `assumptions` · `pitfalls` · `open_questions`

### Model notes (permanent)

```
local_note_write("pattern", "Use passes=2 for local_audit on security-critical files")
local_note_write("gotcha", "health_check() returns False if port 11434 is firewalled locally")
local_note_search("ollama connection issues")
```

Categories: `architecture` · `gotcha` · `pattern`

### Extended code_surface timeout

`local_code_surface` on non-Python files uses `LOCALTHINK_CODE_SURFACE_TIMEOUT` (default 600s).
```bash
export LOCALTHINK_CODE_SURFACE_TIMEOUT=900   # if your model is slow on large TS/Go/Rust files
```
