#!/usr/bin/env python3
"""
LocalThink Settings GUI — standalone subprocess script.

Reads ~/.localthink-mcp/config.json, shows a settings window,
writes updated config on Save, then exits.

Run directly:  python -m localthink_mcp.gui.config_gui
"""
from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ── Allow running as __main__ from inside the package ────────────────────────
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.config import DEFAULTS, apply_config, current_as_dict  # noqa: E402

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#1e1e2e"
SURFACE   = "#27273a"
BORDER    = "#3a3a52"
ACCENT    = "#7c6af7"
ACCENT_HO = "#9d8fff"
FG        = "#cdd6f4"
FG_DIM    = "#7f849c"
FG_HEAD   = "#ffffff"
GREEN     = "#a6e3a1"
RED       = "#f38ba8"
ENTRY_BG  = "#313244"
FONT_UI   = ("Segoe UI", 10)
FONT_HEAD = ("Segoe UI Semibold", 11)
FONT_SEC  = ("Segoe UI Semibold", 9)
FONT_MONO = ("Consolas", 10)
PAD       = 16
INNER     = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_models(base_url: str) -> list[str]:
    try:
        import httpx
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=3.0)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def _ollama_alive(base_url: str) -> bool:
    try:
        import httpx
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


# ── Main window ───────────────────────────────────────────────────────────────

class ConfigGUI:
    def __init__(self, root: tk.Tk, cfg: dict) -> None:
        self.root    = root
        self.cfg     = cfg
        self.saved   = False
        self.models: list[str] = []

        self._build_style()
        self._build_window()
        self._build_ui()
        self._async_probe()

    # ── Style ─────────────────────────────────────────────────────────────────

    def _build_style(self) -> None:
        s = ttk.Style(self.root)
        s.theme_use("clam")

        s.configure(".",
            background=BG, foreground=FG, font=FONT_UI,
            borderwidth=0, relief="flat",
            troughcolor=SURFACE, selectbackground=ACCENT,
        )
        s.configure("TFrame",  background=BG)
        s.configure("Card.TFrame", background=SURFACE, relief="flat")
        s.configure("TLabel",  background=BG, foreground=FG, font=FONT_UI)
        s.configure("Head.TLabel", background=BG, foreground=FG_HEAD, font=FONT_HEAD)
        s.configure("Dim.TLabel",  background=BG, foreground=FG_DIM,  font=FONT_UI)
        s.configure("Sec.TLabel",  background=SURFACE, foreground=FG_DIM,
                    font=FONT_SEC)
        s.configure("Card.TLabel", background=SURFACE, foreground=FG, font=FONT_UI)

        s.configure("TEntry",
            fieldbackground=ENTRY_BG, foreground=FG,
            insertcolor=FG, borderwidth=1, relief="flat",
        )
        s.map("TEntry",
            fieldbackground=[("focus", "#3c3c58")],
            bordercolor=[("focus", ACCENT), ("!focus", BORDER)],
        )
        s.configure("TCombobox",
            fieldbackground=ENTRY_BG, foreground=FG,
            selectbackground=ACCENT, selectforeground=FG_HEAD,
            arrowcolor=FG_DIM, borderwidth=1,
        )
        s.map("TCombobox",
            fieldbackground=[("readonly", ENTRY_BG)],
            bordercolor=[("focus", ACCENT), ("!focus", BORDER)],
        )
        s.configure("TSpinbox",
            fieldbackground=ENTRY_BG, foreground=FG,
            insertcolor=FG, borderwidth=1,
        )
        s.configure("Accent.TButton",
            background=ACCENT, foreground=FG_HEAD,
            font=("Segoe UI Semibold", 10), padding=(16, 7),
        )
        s.map("Accent.TButton",
            background=[("active", ACCENT_HO), ("pressed", "#6a5ae0")],
        )
        s.configure("Ghost.TButton",
            background=SURFACE, foreground=FG_DIM,
            font=FONT_UI, padding=(16, 7),
            relief="flat",
        )
        s.map("Ghost.TButton",
            background=[("active", BORDER)],
            foreground=[("active", FG)],
        )
        s.configure("Small.TButton",
            background=BORDER, foreground=FG_DIM,
            font=("Segoe UI", 9), padding=(8, 4),
        )
        s.map("Small.TButton",
            background=[("active", ACCENT)],
            foreground=[("active", FG_HEAD)],
        )

    # ── Window chrome ─────────────────────────────────────────────────────────

    def _build_window(self) -> None:
        r = self.root
        r.title("LocalThink — Settings")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.geometry("620x640")
        r.update_idletasks()
        sw = r.winfo_screenwidth()
        sh = r.winfo_screenheight()
        x  = (sw - 620) // 2
        y  = (sh - 640) // 2
        r.geometry(f"620x640+{x}+{y}")
        r.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=PAD)
        outer.pack(fill="both", expand=True)

        # Header
        hdr = ttk.Frame(outer)
        hdr.pack(fill="x", pady=(0, PAD))
        ttk.Label(hdr, text="LocalThink Settings", style="Head.TLabel").pack(side="left")
        ttk.Label(hdr, text="v2.1", style="Dim.TLabel").pack(side="left", padx=(8, 0))

        # Status bar
        self._status_frame = sf = ttk.Frame(outer, style="Card.TFrame", padding=(INNER, 8))
        sf.pack(fill="x", pady=(0, PAD))
        self._status_dot   = tk.Canvas(sf, width=10, height=10, bg=SURFACE,
                                       highlightthickness=0)
        self._status_dot.pack(side="left", padx=(0, 8))
        self._status_label = ttk.Label(sf, text="Checking Ollama…", style="Card.TLabel")
        self._status_label.pack(side="left")

        # Scrollable content
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb     = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._content = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=self._content, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)

        def _on_content_resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        self._content.bind("<Configure>", _on_content_resize)

        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        self._vars: dict[str, tk.Variable] = {}
        self._combos: dict[str, ttk.Combobox] = {}

        self._section("OLLAMA CONNECTION")
        self._row_entry("Base URL",  "ollama_base_url",
                        hint="http://localhost:11434", mono=True,
                        action=("Test", self._test_connection))

        self._section("MODELS")
        self._row_combo("Default model", "ollama_model",
                        hint="Main model — quality ops")
        self._row_combo("Fast model",    "ollama_fast_model",
                        hint="Lightweight ops (classify, outline). Leave blank = same as default.")
        self._row_combo("Tiny model",    "ollama_tiny_model",
                        hint="Ultra-fast tier. Leave blank = same as fast.")

        self._section("CACHE")
        self._row_entry("Cache directory", "cache_dir",
                        hint="Leave blank for default (~/.cache/localthink-mcp)",
                        action=("Browse", lambda: self._browse_dir("cache_dir")))
        self._row_spin("TTL (days)", "cache_ttl_days", lo=1, hi=365)

        self._section("MEMO / NOTES")
        self._row_entry("Memo directory", "memo_dir",
                        hint="Leave blank for default (~/.localthink-mcp)",
                        action=("Browse", lambda: self._browse_dir("memo_dir")))

        # Footer
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(PAD, 0))
        ttk.Label(footer, text="Changes apply after restart.", style="Dim.TLabel").pack(side="left")
        ttk.Button(footer, text="Cancel", style="Ghost.TButton",
                   command=self._on_cancel).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Save", style="Accent.TButton",
                   command=self._on_save).pack(side="right")

    def _section(self, title: str) -> None:
        f = ttk.Frame(self._content, style="Card.TFrame", padding=(INNER, 8))
        f.pack(fill="x", pady=(0, 2))
        ttk.Label(f, text=title, style="Sec.TLabel").pack(anchor="w")

    def _row_entry(self, label: str, key: str, hint: str = "",
                   mono: bool = False, action: tuple | None = None) -> None:
        row = ttk.Frame(self._content, style="Card.TFrame", padding=(INNER, 6))
        row.pack(fill="x", pady=(0, 1))

        ttk.Label(row, text=label, style="Card.TLabel", width=18, anchor="w").pack(side="left")

        var = tk.StringVar(value=str(self.cfg.get(key, "")))
        self._vars[key] = var

        ef = ttk.Frame(row, style="Card.TFrame")
        ef.pack(side="left", fill="x", expand=True, padx=(0, 4))

        font = FONT_MONO if mono else FONT_UI
        e = ttk.Entry(ef, textvariable=var, font=font)
        e.pack(fill="x")
        if hint and not var.get():
            self._add_placeholder(e, var, hint)

        if action:
            btn_text, btn_cmd = action
            ttk.Button(row, text=btn_text, style="Small.TButton",
                       command=btn_cmd).pack(side="right")

    def _row_combo(self, label: str, key: str, hint: str = "") -> None:
        row = ttk.Frame(self._content, style="Card.TFrame", padding=(INNER, 6))
        row.pack(fill="x", pady=(0, 1))

        ttk.Label(row, text=label, style="Card.TLabel", width=18, anchor="w").pack(side="left")

        var = tk.StringVar(value=str(self.cfg.get(key, "")))
        self._vars[key] = var

        cb = ttk.Combobox(row, textvariable=var, state="normal", font=FONT_MONO)
        cb.pack(side="left", fill="x", expand=True)
        self._combos[key] = cb

        if hint:
            ttk.Label(row, text="  " + hint, style="Dim.TLabel",
                      wraplength=0).pack(side="left", padx=(6, 0))

    def _row_spin(self, label: str, key: str, lo: int, hi: int) -> None:
        row = ttk.Frame(self._content, style="Card.TFrame", padding=(INNER, 6))
        row.pack(fill="x", pady=(0, 1))

        ttk.Label(row, text=label, style="Card.TLabel", width=18, anchor="w").pack(side="left")

        var = tk.StringVar(value=str(self.cfg.get(key, DEFAULTS.get(key, lo))))
        self._vars[key] = var

        ttk.Spinbox(row, from_=lo, to=hi, textvariable=var,
                    width=8, font=FONT_UI).pack(side="left")

    def _add_placeholder(self, entry: ttk.Entry, var: tk.StringVar, hint: str) -> None:
        entry.configure(foreground=FG_DIM)
        entry.insert(0, hint)
        var.set(hint)

        def _focus_in(e):
            if var.get() == hint:
                entry.configure(foreground=FG)
                var.set("")

        def _focus_out(e):
            if not var.get():
                entry.configure(foreground=FG_DIM)
                var.set(hint)

        entry.bind("<FocusIn>",  _focus_in)
        entry.bind("<FocusOut>", _focus_out)

    # ── Ollama probe ──────────────────────────────────────────────────────────

    def _async_probe(self) -> None:
        def probe():
            url    = self._vars.get("ollama_base_url", tk.StringVar()).get()
            alive  = _ollama_alive(url)
            models = _fetch_models(url) if alive else []
            self.root.after(0, self._apply_probe_result, alive, models)

        threading.Thread(target=probe, daemon=True).start()

    def _apply_probe_result(self, alive: bool, models: list[str]) -> None:
        self.models = models
        color = GREEN if alive else RED
        text  = f"Ollama connected — {len(models)} model(s)" if alive \
                else "Ollama not reachable — start with: ollama serve"

        c = self._status_dot
        c.delete("all")
        c.create_oval(1, 1, 9, 9, fill=color, outline=color)
        self._status_label.configure(text=text)

        if models:
            empty_opt = [""]
            for key in ("ollama_model", "ollama_fast_model", "ollama_tiny_model"):
                cb = self._combos.get(key)
                if cb:
                    opts = models if key == "ollama_model" else empty_opt + models
                    cb.configure(values=opts)

    def _test_connection(self) -> None:
        url = self._vars["ollama_base_url"].get().strip()
        self._status_label.configure(text="Testing…")
        self._async_probe()

    # ── Browse ────────────────────────────────────────────────────────────────

    def _browse_dir(self, key: str) -> None:
        d = filedialog.askdirectory(parent=self.root, title="Select directory")
        if d:
            self._vars[key].set(d)

    # ── Save / Cancel ─────────────────────────────────────────────────────────

    def _collect(self) -> dict:
        out = {}
        for key, var in self._vars.items():
            raw = var.get().strip()
            # strip placeholder values
            if key == "ollama_base_url" and raw == "http://localhost:11434":
                out[key] = raw
            elif raw in ("", "Leave blank for default (~/.cache/localthink-mcp)",
                             "Leave blank for default (~/.localthink-mcp)"):
                out[key] = ""
            else:
                out[key] = int(raw) if key == "cache_ttl_days" else raw
        return out

    def _on_save(self) -> None:
        settings = self._collect()
        try:
            apply_config(settings)
            self.saved = True
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self.root)

    def _on_cancel(self) -> None:
        self.root.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    cfg  = current_as_dict()
    root = tk.Tk()
    app  = ConfigGUI(root, cfg)
    root.mainloop()
    sys.exit(0 if app.saved else 1)


if __name__ == "__main__":
    main()
