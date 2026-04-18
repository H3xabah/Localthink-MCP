#!/usr/bin/env python3
"""
LocalThink Settings GUI — standalone subprocess script.

Reads ~/.localthink-mcp/config.json, presents a tabbed settings window,
writes updated config on Save, exits with code 0 (saved) or 1 (cancelled).

Run directly:  python -m localthink_mcp.gui.config_gui
"""
from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Allow running as __main__ from inside the package tree
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.config import SCHEMA, SECTIONS, apply_config, current_as_dict  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_models(base_url: str) -> tuple[bool, list[str]]:
    """Return (alive, model_names)."""
    try:
        import httpx
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=3.0)
        r.raise_for_status()
        return True, [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return False, []


# ── Main window ───────────────────────────────────────────────────────────────

class ConfigApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root   = root
        self.cfg    = current_as_dict()
        self.saved  = False
        self.models: list[str] = []

        self._vars:   dict[str, tk.Variable] = {}
        self._combos: dict[str, ttk.Combobox] = {}

        self._setup_window()
        self._build()
        self._probe_ollama()

    # ── Window ────────────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        r = self.root
        r.title("LocalThink — Settings")
        r.resizable(True, True)
        r.minsize(560, 460)
        r.geometry("620x560")
        r.update_idletasks()
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"620x560+{(sw-620)//2}+{(sh-560)//2}")
        r.protocol("WM_DELETE_WINDOW", self._cancel)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Status bar at top
        sf = tk.Frame(self.root, bd=1, relief="sunken")
        sf.pack(fill="x", padx=8, pady=(8, 0))
        self._status_var = tk.StringVar(value="Checking Ollama…")
        self._status_dot = tk.Label(sf, text="●", fg="gray", font=("TkDefaultFont", 12))
        self._status_dot.pack(side="left", padx=(6, 2))
        tk.Label(sf, textvariable=self._status_var).pack(side="left", pady=4)

        # Notebook
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        for section in SECTIONS:
            frame = ttk.Frame(nb, padding=12)
            nb.add(frame, text=f"  {section}  ")
            self._build_section(frame, section)

        # Footer
        footer = tk.Frame(self.root)
        footer.pack(fill="x", padx=8, pady=(0, 8))
        tk.Label(
            footer,
            text="Timeouts · Limits · Cache · Memo: instant.  Ollama URL and models: restart MCP server.",
            fg="gray",
            font=("TkDefaultFont", 8),
        ).pack(side="left")
        tk.Button(footer, text="Cancel", command=self._cancel, width=10).pack(side="right", padx=(4, 0))
        tk.Button(footer, text="Reset Tab", command=self._reset_tab, width=10).pack(side="right", padx=(4, 0))
        tk.Button(footer, text="Save", command=self._save,
                  bg="#4a7eff", fg="white", activebackground="#3a6eee",
                  width=10).pack(side="right")

    def _build_section(self, parent: ttk.Frame, section: str) -> None:
        keys = [k for k, v in SCHEMA.items() if v["section"] == section]

        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize_canvas(e):
            canvas.itemconfig(win, width=e.width)
        canvas.bind("<Configure>", _resize_canvas)

        def _update_scroll(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _update_scroll)

        canvas.bind("<Enter>", lambda e, c=canvas: c.bind_all(
            "<MouseWheel>",
            lambda ev, cv=c: cv.yview_scroll(-1 if ev.delta > 0 else 1, "units"),
        ))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        for row_idx, key in enumerate(keys):
            meta = SCHEMA[key]
            self._build_row(inner, row_idx, key, meta)

    def _build_row(self, parent: ttk.Frame, row: int, key: str, meta: dict) -> None:
        val = self.cfg.get(key, meta["default"])

        # Label column
        lf = ttk.Frame(parent)
        lf.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Label(lf, text=meta["label"], width=22, anchor="w").pack(anchor="w")
        if meta.get("hint"):
            ttk.Label(lf, text=meta["hint"], foreground="gray",
                      font=("TkDefaultFont", 8), wraplength=160).pack(anchor="w")

        # Widget column
        wf = ttk.Frame(parent)
        wf.grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)

        if meta["type"] == "int":
            var = tk.StringVar(value=str(val))
            self._vars[key] = var
            lo, hi = _int_range(key)
            ttk.Spinbox(wf, from_=lo, to=hi, textvariable=var,
                        width=10).pack(side="left")

        elif key in ("ollama_model", "ollama_fast_model", "ollama_tiny_model"):
            var = tk.StringVar(value=str(val))
            self._vars[key] = var
            cb = ttk.Combobox(wf, textvariable=var, width=42)
            cb.pack(side="left", fill="x", expand=True)
            self._combos[key] = cb

        elif meta["type"] == "dir":
            var = tk.StringVar(value=str(val))
            self._vars[key] = var
            ttk.Entry(wf, textvariable=var, width=36).pack(side="left", fill="x", expand=True)
            k = key  # capture for lambda
            ttk.Button(wf, text="Browse…",
                       command=lambda k=k: self._browse(k)).pack(side="left", padx=(4, 0))

        else:  # str
            var = tk.StringVar(value=str(val))
            self._vars[key] = var
            if key == "ollama_base_url":
                ttk.Entry(wf, textvariable=var, width=36).pack(side="left", fill="x", expand=True)
                ttk.Button(wf, text="Test",
                           command=self._test_connection).pack(side="left", padx=(4, 0))
            else:
                ttk.Entry(wf, textvariable=var, width=42).pack(side="left", fill="x", expand=True)

    # ── Ollama probe ──────────────────────────────────────────────────────────

    def _probe_ollama(self) -> None:
        url = self._vars.get("ollama_base_url", tk.StringVar()).get().strip() \
              or "http://localhost:11434"
        self._status_var.set("Checking Ollama…")
        self._status_dot.configure(fg="gray")

        def worker():
            alive, models = _fetch_models(url)
            self.models = models
            self.root.after(0, self._apply_probe, alive, models)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_probe(self, alive: bool, models: list[str]) -> None:
        if alive:
            self._status_dot.configure(fg="green")
            self._status_var.set(f"Ollama connected — {len(models)} model(s) available")
        else:
            self._status_dot.configure(fg="red")
            self._status_var.set("Ollama not reachable  —  start with: ollama serve")

        blank = [""]
        for key in ("ollama_model", "ollama_fast_model", "ollama_tiny_model"):
            cb = self._combos.get(key)
            if cb:
                opts = models if key == "ollama_model" else blank + models
                cb.configure(values=opts)

    def _test_connection(self) -> None:
        self._probe_ollama()

    # ── Browse ────────────────────────────────────────────────────────────────

    def _browse(self, key: str) -> None:
        d = filedialog.askdirectory(parent=self.root, title="Select directory")
        if d:
            self._vars[key].set(d)

    # ── Reset tab ─────────────────────────────────────────────────────────────

    def _reset_tab(self) -> None:
        nb = None
        for w in self.root.winfo_children():
            if isinstance(w, ttk.Notebook):
                nb = w
                break
        if nb is None:
            return
        tab_text = nb.tab(nb.select(), "text").strip()
        keys = [k for k, v in SCHEMA.items() if v["section"] == tab_text]
        for key in keys:
            var = self._vars.get(key)
            if var:
                var.set(str(SCHEMA[key]["default"]))

    # ── Save / Cancel ─────────────────────────────────────────────────────────

    def _collect(self) -> dict:
        out: dict = {}
        for key, meta in SCHEMA.items():
            var = self._vars.get(key)
            if var is None:
                out[key] = meta["default"]
                continue
            raw = var.get().strip()
            if meta["type"] == "int":
                try:
                    out[key] = int(raw)
                except (ValueError, TypeError):
                    out[key] = meta["default"]
            else:
                out[key] = raw
        return out

    def _save(self) -> None:
        settings = self._collect()
        try:
            apply_config(settings)
            self.saved = True
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self.root)

    def _cancel(self) -> None:
        self.root.destroy()


# ── Int spinbox ranges ─────────────────────────────────────────────────────────

def _int_range(key: str) -> tuple[int, int]:
    ranges: dict[str, tuple[int, int]] = {
        "timeout_generate":       (10,  3600),
        "timeout_fast":           (5,   1800),
        "timeout_tiny":           (5,   600),
        "timeout_health":         (1,   30),
        "timeout_code_surface":   (10,  3600),
        "git_diff_timeout":       (5,   300),
        "max_file_bytes":         (1000, 10_000_000),
        "max_pipeline_steps":     (1,   20),
        "max_scan_files":         (1,   500),
        "classify_sample":        (500, 50_000),
        "max_concurrency":        (1,   32),
        "chat_history_chars":     (500, 50_000),
        "cache_ttl_days":         (1,   365),
        "memo_compact_threshold": (500, 50_000),
        "max_notes":              (50, 10_000),
    }
    return ranges.get(key, (0, 99999))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    root = tk.Tk()
    app  = ConfigApp(root)
    root.mainloop()
    sys.exit(0 if app.saved else 1)


if __name__ == "__main__":
    main()
