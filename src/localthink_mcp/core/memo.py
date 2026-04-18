"""
Stateful scratchpad + persistent model notes.

Scratchpad: ~/.localthink-mcp/CONTEXT.md
  Sections: decisions | assumptions | pitfalls | open_questions
  Auto-compacts any section > COMPACT_THRESHOLD_CHARS

Model notes: ~/.localthink-mcp/notes/
  Permanent, cross-session, never compacted.
  Categories: architecture | gotcha | pattern
  Index: notes/index.json — [{id, ts, category, text}]
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# ── Paths (override via LOCALTHINK_MEMO_DIR) ──────────────────────────────
MEMO_DIR          = Path(os.environ.get("LOCALTHINK_MEMO_DIR", "") or Path.home() / ".localthink-mcp")
CONTEXT_FILE      = MEMO_DIR / "CONTEXT.md"
CHECKPOINT_FILE   = MEMO_DIR / "CHECKPOINT.md"
NOTES_DIR         = MEMO_DIR / "notes"
NOTES_INDEX       = NOTES_DIR / "index.json"
LAST_RUN_FILE     = MEMO_DIR / "last_run.json"
COMPACT_THRESHOLD = int(os.environ.get("LOCALTHINK_COMPACT_THRESHOLD", "3000"))
MAX_NOTES         = int(os.environ.get("LOCALTHINK_MAX_NOTES", "500"))
VALID_SECTIONS    = {"decisions", "assumptions", "pitfalls", "open_questions"}
VALID_CATEGORIES  = {"architecture", "gotcha", "pattern"}


def reload_env() -> None:
    """Re-read memo env vars into module globals. Called by config.apply_config()."""
    global MEMO_DIR, CONTEXT_FILE, CHECKPOINT_FILE, NOTES_DIR, NOTES_INDEX
    global LAST_RUN_FILE, COMPACT_THRESHOLD, MAX_NOTES
    MEMO_DIR          = Path(os.environ.get("LOCALTHINK_MEMO_DIR", "") or Path.home() / ".localthink-mcp")
    CONTEXT_FILE      = MEMO_DIR / "CONTEXT.md"
    CHECKPOINT_FILE   = MEMO_DIR / "CHECKPOINT.md"
    NOTES_DIR         = MEMO_DIR / "notes"
    NOTES_INDEX       = NOTES_DIR / "index.json"
    LAST_RUN_FILE     = MEMO_DIR / "last_run.json"
    COMPACT_THRESHOLD = int(os.environ.get("LOCALTHINK_COMPACT_THRESHOLD", "3000"))
    MAX_NOTES         = int(os.environ.get("LOCALTHINK_MAX_NOTES", "500"))


def _ensure_dirs() -> None:
    """Create MEMO_DIR and NOTES_DIR if missing. Call at start of every write function."""
    MEMO_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_context() -> dict[str, str]:
    """Parse CONTEXT.md into {section: content}. Returns empty dict if file missing."""
    if not CONTEXT_FILE.exists():
        return {}
    text = CONTEXT_FILE.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^## (\w+)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "".join(buf).strip()
            current = m.group(1)
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "".join(buf).strip()
    return sections


def _write_context(sections: dict[str, str]) -> None:
    """Write CONTEXT.md from dict. Format: ## {key}\n{content}\n\n per section."""
    lines: list[str] = []
    for key, content in sections.items():
        lines.append(f"## {key}\n{content}\n\n")
    CONTEXT_FILE.write_text("".join(lines), encoding="utf-8")


def _try_compact(text: str, system: str) -> str | None:
    """Attempt Ollama compression. Returns result or None if Ollama unavailable."""
    try:
        import sys
        # Resolve ollama_client from the parent package path
        _pkg = Path(__file__).parent.parent
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        from ollama_client import generate, health_check  # type: ignore
        if not health_check():
            return None
        return generate(text, system=system)
    except Exception:
        return None


def memo_write(key: str, content: str, compress: bool = False) -> dict:
    """Write an entry to a scratchpad section.

    key: decisions | assumptions | pitfalls | open_questions
    compress=True: Ollama compresses content to bullets before appending.
    Auto-compacts section if it exceeds COMPACT_THRESHOLD chars.
    """
    if key not in VALID_SECTIONS:
        return {"error": f"invalid section '{key}'. Valid: {sorted(VALID_SECTIONS)}"}

    _ensure_dirs()

    sections = _read_context()

    text = content
    compressed_flag = False

    if compress:
        try:
            from prompts import MEMO_COMPACT_SYSTEM  # type: ignore
        except ImportError:
            MEMO_COMPACT_SYSTEM = (
                "Compress these technical notes to bullet points. "
                "Keep: decisions, failure modes, file/function references, unresolved questions. "
                "Drop: rationale, repeated examples, boilerplate. "
                "Output: bullet points only, one per line, starting with -"
            )
        result = _try_compact(content, MEMO_COMPACT_SYSTEM)
        if result:
            text = result
            compressed_flag = True

    entry = f"\n- [{_iso()}] {text}"
    current = sections.get(key, "")
    current += entry
    sections[key] = current

    # Auto-compact if over threshold
    if len(current) > COMPACT_THRESHOLD:
        try:
            from prompts import MEMO_COMPACT_SYSTEM  # type: ignore
        except ImportError:
            MEMO_COMPACT_SYSTEM = (
                "Compress these technical notes to bullet points. "
                "Keep: decisions, failure modes, file/function references, unresolved questions. "
                "Drop: rationale, repeated examples, boilerplate. "
                "Output: bullet points only, one per line, starting with -"
            )
        compacted = _try_compact(current, MEMO_COMPACT_SYSTEM)
        if compacted:
            sections[key] = compacted

    _write_context(sections)
    return {
        "written": True,
        "section": key,
        "compressed": compressed_flag,
        "section_chars": len(sections[key]),
    }


def memo_read(query: str = "", section: str = "") -> str:
    """Read from the session scratchpad.

    section: return that section verbatim (≤800 chars).
    query: keyword search across all sections, top 10 lines.
    neither: distilled summary — each section heading + first 2 lines.
    Always prefixed with [~N tokens] where N = len(result)//4.
    """
    sections = _read_context()

    if section:
        content = sections.get(section, f"(section '{section}' is empty)")[:800]
        result = f"## {section}\n{content}"
        return f"[~{len(result)//4} tokens]\n{result}"

    if query:
        query_words = set(query.lower().split())
        scored: list[tuple[float, str]] = []
        for sec_name, sec_content in sections.items():
            for line in sec_content.splitlines():
                line = line.strip()
                if not line:
                    continue
                line_words = set(line.lower().split())
                score = (
                    len(query_words & line_words) / len(query_words)
                    if query_words else 0.0
                )
                scored.append((score, f"[{sec_name}] {line}"))
        scored.sort(key=lambda x: x[0], reverse=True)
        bullets = "\n".join(f"- {line}" for _, line in scored[:10])
        result = bullets or "(no matches)"
        return f"[~{len(result)//4} tokens]\n{result}"

    # Summary mode
    lines: list[str] = []
    for sec_name, sec_content in sections.items():
        first_two = "\n".join(sec_content.splitlines()[:2])
        lines.append(f"## {sec_name}\n{first_two}")
    result = "\n\n".join(lines) if lines else "(scratchpad is empty)"
    return f"[~{len(result)//4} tokens]\n{result}"


def memo_checkpoint() -> str:
    """Compress scratchpad to a RESUME_PROMPT ≤200 tokens.

    Writes CHECKPOINT.md. Returns the resume string to paste after /clear.
    """
    _ensure_dirs()
    sections = _read_context()
    iso = _iso()

    # Compact each section to ≤3 bullets
    compacted: dict[str, list[str]] = {}
    for sec_name, content in sections.items():
        try:
            from prompts import MEMO_COMPACT_SYSTEM  # type: ignore
        except ImportError:
            MEMO_COMPACT_SYSTEM = (
                "Compress these technical notes to bullet points. "
                "Keep: decisions, failure modes, file/function references, unresolved questions. "
                "Drop: rationale, repeated examples, boilerplate. "
                "Output: bullet points only, one per line, starting with -"
            )
        result = _try_compact(content, MEMO_COMPACT_SYSTEM)
        if result:
            bullets = [line.strip() for line in result.splitlines() if line.strip().startswith("-")][:3]
        else:
            bullets = [line.strip() for line in content.splitlines() if line.strip()][:3]
        compacted[sec_name] = bullets

    # Extract file paths from all sections
    all_text = "\n".join(sections.values())
    file_paths = list(dict.fromkeys(re.findall(r"[\w./\\-]+\.\w{2,5}", all_text)))

    # First decision line as task
    decisions = compacted.get("decisions", [])
    task = decisions[0].lstrip("- ") if decisions else "unknown"

    def fmt(bullets: list[str]) -> str:
        return "\n".join(bullets) if bullets else "  (none)"

    resume = (
        f"## Resume — {iso}\n"
        f"Task: {task}\n"
        f"Decided:\n{fmt(compacted.get('decisions', []))}\n"
        f"Watch out:\n{fmt(compacted.get('pitfalls', []))}\n"
        f"Open:\n{fmt(compacted.get('open_questions', []))}\n"
        f"Files: {', '.join(file_paths[:10]) if file_paths else 'none'}\n"
        f"Paste after /clear to restore context."
    )

    CHECKPOINT_FILE.write_text(
        f"# Checkpoint — {iso}\n\n{resume}\n",
        encoding="utf-8",
    )
    return resume


def note_write(category: str, content: str) -> dict:
    """Write a permanent model note. Persists across all sessions, never cleared.

    category: architecture | gotcha | pattern
    """
    if category not in VALID_CATEGORIES:
        return {"error": f"invalid category '{category}'. Valid: {sorted(VALID_CATEGORIES)}"}

    _ensure_dirs()
    iso = _iso()
    note_id = uuid4().hex[:8]

    # Append to category file
    cat_file = NOTES_DIR / f"{category}.md"
    with cat_file.open("a", encoding="utf-8") as f:
        f.write(f"\n### {iso}\n{content}\n")

    # Update index
    index: list[dict] = []
    if NOTES_INDEX.exists():
        try:
            index = json.loads(NOTES_INDEX.read_text(encoding="utf-8"))
        except Exception:
            index = []
    index.append({"id": note_id, "ts": iso, "category": category, "text": content})
    if len(index) > MAX_NOTES:
        index = index[-MAX_NOTES:]  # keep newest
    NOTES_INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"written": True, "category": category, "note_id": note_id}


def note_search(query: str, limit: int = 5) -> str:
    """Search permanent model notes by keyword overlap (cosine if nomic-embed-text available).

    Returns top `limit` notes across all categories.
    """
    if not NOTES_INDEX.exists():
        return "No notes yet."

    try:
        index: list[dict] = json.loads(NOTES_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return "No notes yet."

    if not index:
        return "No notes yet."

    query_words = set(query.lower().split())

    # Try cosine similarity via nomic-embed-text
    use_cosine = False
    try:
        import sys
        _pkg = Path(__file__).parent.parent
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        from ollama_client import list_models  # type: ignore
        import httpx
        import os as _os
        BASE_URL = _os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        if "nomic-embed-text" in list_models():
            use_cosine = True

            def embed(text: str) -> list[float]:
                with httpx.Client(timeout=30.0) as client:
                    r = client.post(
                        f"{BASE_URL}/api/embeddings",
                        json={"model": "nomic-embed-text", "prompt": text},
                    )
                    r.raise_for_status()
                    return r.json()["embedding"]

            import math

            def cosine(a: list[float], b: list[float]) -> float:
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a))
                nb = math.sqrt(sum(x * x for x in b))
                return dot / (na * nb) if na and nb else 0.0

            q_emb = embed(query)
            scored = [(cosine(q_emb, embed(n["text"])), n) for n in index]
    except Exception:
        use_cosine = False

    if not use_cosine:
        def kw_score(note: dict) -> float:
            note_words = set(note["text"].lower().split())
            return len(query_words & note_words) / max(len(query_words), 1)

        scored = [(kw_score(n), n) for n in index]

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    parts: list[str] = []
    for _, note in top:
        parts.append(f"[{note['category']} | {note['ts']} | id:{note['id']}]\n{note['text']}\n---")
    return "\n".join(parts) if parts else "No matching notes found."
