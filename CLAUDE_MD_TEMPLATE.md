# Localthink CLAUDE.md Template

Copy the section below into your project's `CLAUDE.md` (or `~/.claude/CLAUDE.md` for global rules).
It tells Claude to automatically route all high-token operations through localthink tools.

---

<!-- COPY FROM HERE -------------------------------------------------------->

## Localthink — automatic token minimisation

The `localthink` MCP server is installed. It runs a local LLM (Ollama) to process files and
text without loading them into this context. Apply the rules below automatically — no prompting
is needed from the user.

### Never load these directly — always use localthink

| Content | Tool to use instead |
|---------|---------------------|
| Any file > 5 KB you would `Read` for information | `local_answer(file, question)` |
| Log files (`*.log`, large `*.txt`) | `local_compress_log(file)` |
| Stack traces / tracebacks > 10 lines | `local_compress_stack_trace(text)` |
| JSON / CSV / API response payloads > 2 KB | `local_compress_data(data)` |
| Saved conversation transcripts | `local_session_compress(file)` |
| CLAUDE.md or system prompts that have grown large | `local_prompt_compress(text)` |

### Before reading any code file

1. **Get the symbol map first:** `local_symbols(file)` — one line per definition with line numbers.
2. **Need a specific function?** `local_find_impl(file, "what it does in plain English")`.
3. **Need the full structure?** `local_strip_to_skeleton(file)` — bodies stripped, structure intact.
4. **Need the public API only?** `local_code_surface(file)` — Python uses pure AST (instant, no Ollama).
5. **Only use `Read` directly when:** you are about to call `Edit` (need exact line content), or the file is < 5 KB.

### Before reading any documentation / config file

1. **One question?** → `local_answer(file, question)`
2. **Multiple questions / repeated reference?** → `local_shrink_file(file)`, then hold the compressed text in context.
3. **Need to find which section covers X?** → `local_outline(text)` first, then `local_extract(text, query)`.
4. **Unknown content type?** → `local_classify(text)` to get a tool recommendation before processing.

### Multi-file and directory operations

- **Same question across N files** → `local_batch_answer([file1, file2, ...], question)` — never loop `Read`.
- **Understand a directory** → `local_scan_dir(dir, "*.py")` or `local_scan_dir(dir, "**/*.ts", question)`.
- **Never call `Read` in a loop across multiple large files.**

### Diffing and comparison

- **Two files on disk** → `local_diff_files(path_a, path_b)` — neither file enters context.
- **Two text blobs already in context** → `local_diff(before, after)`.
- **Never load two files just to compare them.**

### Multi-step processing — use pipeline

When you know you will need extract→summarise or extract→answer, use one call:
```
local_pipeline(text, [
  {"op": "extract", "query": "authentication"},
  {"op": "summarize", "focus": "security risks"}
])
```
This saves a full round-trip vs two separate tool calls.

### Format conversion and schema

- **Config in wrong format (JSON→YAML etc.)** → `local_translate(text, "yaml")`.
- **Unknown data structure** → `local_schema_infer(data)` before reasoning about it.
- **Chronological analysis (logs, changelogs, git log)** → `local_timeline(text)`.

### Stateful document Q&A

When the user asks multiple questions about the same large document across a conversation,
use `local_chat` so the document is compressed once and never re-enters context:

```
Turn 1: result = local_chat(full_doc, question_1, "")
Turn 2: result = local_chat(result["doc"], question_2, result["history"])
Turn 3: result = local_chat(result["doc"], question_3, result["history"])
```

### Before including raw content in your response

Compress before quoting:
- Log content → `local_compress_log(file)` then quote the summary.
- Stack traces → `local_compress_stack_trace(text)` then quote the compressed version.
- Large data dumps → `local_compress_data(data)` then quote the compressed version.
- Long file snippets → `local_summarize(text)` then quote.

### When unsure which tool to use

Use `local_auto(input, question)` — it detects file paths, picks the right operation, and
for large documents automatically does extract-then-answer. Zero decision overhead.

Use `local_classify(text)` to get a JSON recommendation: `content_type`, `recommended_tool`,
`compression_estimate`. Good before processing an unknown file.

### What NOT to offload to localthink

- Files < 5 KB (overhead outweighs savings).
- Files you are about to `Edit` (need byte-exact line content for the `Edit` tool).
- The current `CLAUDE.md` or task spec you are reading right now.
- Binary files, images, compiled artifacts.
- Test fixture data you need to reason about precisely (use `Read` with small fixtures).

<!-- COPY TO HERE --------------------------------------------------------->

---

## Notes on this template

- **Threshold 5 KB:** Roughly 1,250 tokens. Below this, `Read` is cheaper than the MCP round-trip.
- **Python AST note:** `local_code_surface` on `.py` files uses no Ollama — it is instant and deterministic. Call it freely.
- **`local_auto` as escape hatch:** When the decision is unclear, `local_auto` picks the right path. It is the lazy-correct option.
- **Compress this template:** Once you've pasted it into CLAUDE.md and it has grown with other rules, run `local_prompt_compress` on the whole CLAUDE.md to keep it lean.
