# localthink-mcp

**Local LLM context compression for Claude Code.**
Offloads large file queries and document processing to Ollama so they never burn Claude's context window.

> v0.1.0 benchmarked at **~30× token savings** on 16 KB file queries.
> v1.1 adds 13 new tools covering every major token-waste pattern.

---

## Quick start

```bash
# 1. Pull a model (once)
ollama pull qwen2.5:14b-instruct-q4_K_M

# 2. Register with Claude Code
claude mcp add localthink -- uvx localthink-mcp

# 3. Verify
claude mcp list   # localthink → Connected
```

---

## Requirements

- [Ollama](https://ollama.ai) installed and running (`ollama serve`)
- [Claude Code](https://claude.ai/code) CLI
- Python 3.10+

---

## All 16 tools

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

| Env var | Default | Description |
|---------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5:14b-instruct-q4_K_M` | Model for all quality operations |
| `OLLAMA_FAST_MODEL` | (same as OLLAMA_MODEL) | Lighter model for classify, outline, code_surface on non-Python |

Smaller fast model example (`qwen2.5:3b` for lightweight ops):

```json
{
  "mcpServers": {
    "localthink": {
      "env": {
        "OLLAMA_MODEL":       "qwen2.5:14b-instruct-q4_K_M",
        "OLLAMA_FAST_MODEL":  "qwen2.5:3b-instruct"
      }
    }
  }
}
```

---

## Install options

### uvx (recommended — zero setup)

```bash
claude mcp add localthink -- uvx localthink-mcp
```

### pip

```bash
pip install localthink-mcp
claude mcp add localthink -- localthink-mcp
```

### Windows — if `uvx` isn't on Claude's PATH

```bash
claude mcp add --transport stdio localthink -- cmd /c uvx localthink-mcp
```

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
