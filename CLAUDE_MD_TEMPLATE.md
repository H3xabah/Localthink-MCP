# Localthink CLAUDE.md Template

Copy the section below into your project's `CLAUDE.md` (or `~/.claude/CLAUDE.md` for global rules).
It tells Claude to automatically route all high-token operations through localthink tools.

---

<!-- COPY FROM HERE -------------------------------------------------------->

## Localthink — Automatic Token Minimisation

The `localthink` MCP server is installed. It runs a local LLM (Ollama) to process files and text without loading them into this context. Apply the rules below automatically — no prompting is needed from the user.

### Always Use localthink Instead of Direct Loading

| Content | Tool to use instead |
|---------|---------------------|
| Any file > 5 KB you would `Read` for information | `local_answer(file, question)` |
| Log files (`*.log`, large `*.txt`) | `local_compress_log(file)` |
| Stack traces / tracebacks > 10 lines | `local_compress_stack_trace(text)` |
| JSON / CSV / API response payloads > 2 KB | `local_compress_data(data)` |
| Saved conversation transcripts | `local_session_compress(file)` |
| CLAUDE.md or system prompts that have grown large | `local_prompt_compress(text)` |
| Vague or rough user prompt | `local_improve_prompt(prompt, context?)` |
| Large or complex task before planning | `local_preplan(task, context?, depth?)` |

### Before Reading Code Files

1. Get symbol map: `local_symbols(file)` — all definitions + line numbers
2. Find specific function: `local_find_impl(file, "what it does in plain English")`
3. Full structure without bodies: `local_strip_to_skeleton(file)`
4. Public API only: `local_code_surface(file)` — Python uses pure AST (instant, no Ollama)
5. **Only use `Read` directly when:** about to call `Edit` (need exact line content), or file is < 5 KB

### Before Reading Docs / Config Files

1. One question → `local_answer(file, question)`
2. Multiple questions / repeated reference → `local_shrink_file(file)`, hold in context
3. Find section covering X → `local_outline(text)` then `local_extract(text, query)`
4. Unknown content type → `local_classify(text)` for tool recommendation

### Multi-file Operations

- Same question across N files → `local_batch_answer([file1, file2, ...], question)` — never loop `Read`
- Understand a directory → `local_scan_dir(dir, "*.py")` or `local_scan_dir(dir, "**/*.ts", question)`

### Diffing

- Two files on disk → `local_diff_files(path_a, path_b)` — neither file enters context
- Two text blobs in context → `local_diff(before, after)`

### Multi-step Processing

Use pipeline for extract→summarise or extract→answer in one call:
```
local_pipeline(text, [{"op": "extract", "query": "..."}, {"op": "summarize", "focus": "..."}])
```

### Format Conversion and Schema

- Config format conversion → `local_translate(text, "yaml")`
- Unknown data structure → `local_schema_infer(data)`
- Chronological analysis → `local_timeline(text)`

### Stateful Document Q&A

Use `local_chat` for repeated questions about the same large document:
```
result = local_chat(full_doc, question_1, "")
result = local_chat(result["doc"], question_2, result["history"])
```

### Before Sending to Claude

- Rough prompt → `local_improve_prompt(prompt, context)` — feed only the clean result to Claude
- Big task → `local_preplan(task, context, depth)` — Claude executes the plan, doesn't re-plan

### When Unsure Which Tool

`local_auto(input, question)` — auto-selects the right operation. `local_classify(text)` for JSON recommendation.

### Changing Settings

Call `local_config()` to open the settings GUI. Covers all 18 settings across Ollama, Timeouts, Limits, Cache, and Memo. Saves to `~/.localthink-mcp/config.json`.

Key settings worth tuning:
- Model tiers (`OLLAMA_MODEL` / `OLLAMA_FAST_MODEL` / `OLLAMA_TINY_MODEL`) — match your hardware
- `LOCALTHINK_TIMEOUT` — raise to `600` for 32b+ models, lower to `120` for fast 7b setups
- `LOCALTHINK_MAX_CONCURRENCY` — `1`–`2` on low VRAM, `6`–`8` with headroom
- `LOCALTHINK_CACHE_TTL_DAYS` — `7` if disk space is tight, `90` for long-running projects

### What NOT to Offload

- Files < 5 KB · Files you are about to `Edit` · Current CLAUDE.md / task spec · Binary files / images

### Smart Buffer — Before Injecting Any Raw Output

Raw test output, build logs, or lint dumps must never enter context directly.
1. `local_gate(raw_output)` → Pattern + Anomalies + Signal (always fits in budget)
2. Need the raw window? `local_slice(file, offset_lines)` — only on demand
3. Meaning-only diff: `local_diff_semantic(before, after)` — noise suppressed

### Execution Filters — Run Project Tools Through localthink

- `local_run_tests()` — returns `{failed, delta, pointer}`. Nothing else.
- `local_run_lint()` — violations grouped by rule. Passing rules suppressed.
- `local_run_build()` — root cause + affected symbols only.

### Session Scratchpad — Write Decisions As You Go

Use throughout every session. Before `/clear`, always checkpoint.
- `local_memo_write("decisions"|"assumptions"|"pitfalls"|"open_questions", content)`
- `local_memo_read()` — distilled summary when you need context
- `local_memo_checkpoint()` — generates RESUME_PROMPT to paste after /clear

### Model Notes — Record What You Learn Permanently

Persist across all sessions. Write when you encounter a pattern or gotcha.
- `local_note_write("architecture"|"gotcha"|"pattern", content)`
- `local_note_search(query)` — search at session start for relevant prior knowledge

<!-- COPY TO HERE --------------------------------------------------------->

---

## Notes on this template

- **Threshold 5 KB:** Roughly 1,250 tokens. Below this, `Read` is cheaper than the MCP round-trip.
- **Python AST note:** `local_code_surface` on `.py` files uses no Ollama — it is instant and deterministic.
- **`local_auto` as escape hatch:** When the decision is unclear, `local_auto` picks the right path.
- **Compress this template:** Once pasted into CLAUDE.md and grown with other rules, run `local_prompt_compress` on the whole file to keep it lean.
