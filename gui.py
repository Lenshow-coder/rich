"""
gui.py — tkinter GUI for the pipeline filter configuration.
Overwrites pipeline module globals and calls pipeline.main() in a thread.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
import json
import os
import sys
import platform
from datetime import datetime

import pipeline

# ─── Platform-aware fonts ──────────────────────────────────────
if platform.system() == "Darwin":
    UI_FONT = (".AppleSystemUIFont", 9)
    UI_FONT_BOLD = (".AppleSystemUIFont", 10, "bold")
    MONO_FONT = ("Menlo", 9)
elif platform.system() == "Windows":
    UI_FONT = ("Segoe UI", 9)
    UI_FONT_BOLD = ("Segoe UI", 10, "bold")
    MONO_FONT = ("Consolas", 9)
else:
    UI_FONT = ("sans-serif", 9)
    UI_FONT_BOLD = ("sans-serif", 10, "bold")
    MONO_FONT = ("monospace", 9)

IS_MAC = platform.system() == "Darwin"

PRESETS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets.json")

# ─── Config field definitions ────────────────────────────────────

FIELDS = [
    # (label, pipeline_var, parse_type, tooltip)
    ("Sport", "SPORT_FILTER", "string_list",
     'e.g. "Basketball, NFL, NHL" — empty = all sports'),
    ("Date Start", "DATE_START", "date",
     "Inclusive start date (YYYY-MM-DD)"),
    ("Date End", "DATE_END", "date",
     "Inclusive end date (YYYY-MM-DD)"),
    ("Book", "BOOK_FILTER", "string_list",
     'e.g. "MBmb, FDmb" — empty = all books'),
]

BAND_FIELDS = [
    ("Odds Bands", "ODDS_BANDS", "num_list",
     "Boundary values for weighted-stake odds buckets"),
    ("Flat Odds Bands", "FLAT_ODDS_BANDS", "num_list",
     "Boundary values for flat-stake odds buckets; bets outside min/max are excluded"),
    ("Edge Bands", "EDGE_BANDS", "num_list",
     "Edge % band boundaries (used in both summaries)"),
    ("Stake Bands", "STAKE_BANDS", "num_list",
     "Stake band boundaries (weighted summary only)"),
]


class _ToolTip:
    """Hover tooltip for any tkinter widget."""

    def __init__(self, widget, text):
        self._widget = widget
        self._text = text
        self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        x = self._widget.winfo_rootx() + self._widget.winfo_width() + 4
        y = self._widget.winfo_rooty()
        self._tip = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        # Outer frame acts as a rounded-look border
        border_color = "#b0b0b0" if IS_MAC else "#c8c8c8"
        tip_bg = "#fefed6" if IS_MAC else "#ffffff"
        outer = tk.Frame(tw, background=border_color, padx=1, pady=1)
        outer.pack()
        label = tk.Label(outer, text=self._text, background=tip_bg, foreground="#444",
                         font=UI_FONT, relief="flat", borderwidth=0,
                         padx=10, pady=6, wraplength=280, justify="left")
        label.pack()

    def _hide(self, _event=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None


def _format_value(val, parse_type):
    """Convert a pipeline variable value to a display string."""
    if parse_type in ("string_list", "num_list"):
        return ", ".join(str(v) for v in val)
    return str(val)


def _parse_value(text, parse_type):
    """Parse a GUI text field into the appropriate Python type.
    Returns (value, error_message).
    """
    text = text.strip()
    if parse_type == "string_list":
        if not text:
            return [], None
        return [s.strip() for s in text.split(",") if s.strip()], None
    if parse_type == "num_list":
        if not text:
            return [], None
        parts = [s.strip() for s in text.split(",") if s.strip()]
        nums = []
        for p in parts:
            try:
                nums.append(float(p) if "." in p else int(p))
            except ValueError:
                return None, f"'{p}' is not a valid number"
        return nums, None
    if parse_type == "date":
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None, f"'{text}' is not a valid date (YYYY-MM-DD)"
        return text, None
    return text, None


# ─── Logging handler that writes to a tk Text widget ─────────────

class TextWidgetHandler(logging.Handler):
    """Push log records into a tk.Text widget via after()."""

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        if getattr(self, "closed", False):
            return
        msg = self.format(record) + "\n"
        try:
            self.text_widget.after(0, self._append, msg)
        except RuntimeError:
            pass  # widget already destroyed

    def _append(self, msg):
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg)
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        except tk.TclError:
            pass  # widget destroyed between after() scheduling and execution


# ─── Preset helpers ──────────────────────────────────────────────

def _load_presets():
    if os.path.exists(PRESETS_PATH):
        try:
            with open(PRESETS_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_presets(presets):
    try:
        with open(PRESETS_PATH, "w") as f:
            json.dump(presets, f, indent=2)
    except OSError as e:
        messagebox.showerror("Save Error", f"Could not write presets.json:\n{e}")


# ─── Main application ───────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pipeline Settings")
        self.resizable(True, True)
        self.minsize(520, 480)

        # Use a platform-appropriate ttk theme
        style = ttk.Style(self)
        if IS_MAC:
            style.theme_use("aqua")
        else:
            style.theme_use("clam")

        # Derive background color from the theme rather than hardcoding
        bg = style.lookup("TFrame", "background") or "#f0f0f0"
        self.configure(bg=bg)

        # Custom styles
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, font=UI_FONT)
        style.configure("TEntry", padding=4)
        style.configure("Heading.TLabel", background=bg,
                         font=UI_FONT_BOLD, foreground="#333")
        style.configure("TButton", font=UI_FONT, padding=(10, 4))
        style.configure("Run.TButton", font=UI_FONT_BOLD, padding=(16, 6))
        style.map("Run.TButton",
                  background=[("active", "#1a6bb5"), ("!disabled", "#1a7fd4")],
                  foreground=[("!disabled", "#fff")])
        # Visible focus ring on entry fields
        style.map("TEntry",
                  lightcolor=[("focus", "#66afe9")],
                  bordercolor=[("focus", "#66afe9")])

        self.entries = {}  # field_name -> tk.StringVar
        self._running = False

        self._build_ui()
        self._load_last_used()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}
        main = ttk.Frame(self, padding=14)
        main.pack(fill="both", expand=True)

        # ── Preset bar ───────────────────────────────────────────
        preset_frame = ttk.Frame(main)
        preset_frame.pack(fill="x", **pad)

        ttk.Label(preset_frame, text="Preset:").pack(side="left")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(
            preset_frame, textvariable=self.preset_var, state="readonly", width=25
        )
        self.preset_combo.pack(side="left", padx=(4, 8))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        ttk.Button(preset_frame, text="Save", command=self._save_preset).pack(side="left", padx=2)
        ttk.Button(preset_frame, text="Delete", command=self._delete_preset).pack(side="left", padx=2)

        self._refresh_preset_list()

        # ── Main filters ─────────────────────────────────────────
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=6)
        ttk.Label(main, text="Main Filters", style="Heading.TLabel").pack(anchor="w", **pad)

        filter_frame = ttk.Frame(main)
        filter_frame.pack(fill="x", **pad)

        for i, (label, var_name, ptype, tip) in enumerate(FIELDS):
            lbl = ttk.Label(filter_frame, text=f"{label}:")
            lbl.grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)
            sv = tk.StringVar(value=_format_value(getattr(pipeline, var_name), ptype))
            entry = ttk.Entry(filter_frame, textvariable=sv, width=40)
            entry.grid(row=i, column=1, sticky="ew", pady=2)
            _ToolTip(lbl, tip)
            _ToolTip(entry, tip)
            self.entries[var_name] = sv
        filter_frame.columnconfigure(1, weight=1)

        # ── Collapsible bands section ────────────────────────────
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=6)

        self._bands_visible = False
        self._toggle_btn = ttk.Button(
            main, text="\u25b6 Summary Bands (Advanced)", command=self._toggle_bands
        )
        self._toggle_btn.pack(anchor="w", **pad)

        self._bands_frame = ttk.Frame(main)
        # Initially hidden — not packed

        for i, (label, var_name, ptype, tip) in enumerate(BAND_FIELDS):
            lbl = ttk.Label(self._bands_frame, text=f"{label}:")
            lbl.grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)
            sv = tk.StringVar(value=_format_value(getattr(pipeline, var_name), ptype))
            entry = ttk.Entry(self._bands_frame, textvariable=sv, width=40)
            entry.grid(row=i, column=1, sticky="ew", pady=2)
            _ToolTip(lbl, tip)
            _ToolTip(entry, tip)
            self.entries[var_name] = sv
        self._bands_frame.columnconfigure(1, weight=1)

        # ── Run button ───────────────────────────────────────────
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=6)
        self.run_btn = ttk.Button(main, text="Run Pipeline", command=self._run_pipeline,
                                   style="Run.TButton")
        self.run_btn.pack(pady=8)

        # ── Output log ───────────────────────────────────────────
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=6)
        ttk.Label(main, text="Output", style="Heading.TLabel").pack(anchor="w", **pad)

        log_frame = ttk.Frame(main)
        log_frame.pack(fill="both", expand=True, **pad)

        self.log_text = tk.Text(log_frame, height=12, state="disabled", wrap="word",
                                font=MONO_FONT, bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="#d4d4d4", selectbackground="#264f78",
                                relief="flat", borderwidth=0, padx=6, pady=6)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Attach log handler
        self._log_handler = TextWidgetHandler(self.log_text)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        pipeline.log.addHandler(self._log_handler)

        # Clean up on window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _toggle_bands(self):
        if self._bands_visible:
            self._bands_frame.pack_forget()
            self._toggle_btn.configure(text="\u25b6 Summary Bands (Advanced)")
            self._bands_visible = False
        else:
            # Pack right after the toggle button
            self._bands_frame.pack(after=self._toggle_btn, fill="x", padx=8, pady=3)
            self._toggle_btn.configure(text="\u25bc Summary Bands (Advanced)")
            self._bands_visible = True

    # ── Field I/O ────────────────────────────────────────────────

    def _get_all_field_defs(self):
        return FIELDS + BAND_FIELDS

    def _get_field_values(self):
        """Return dict of {var_name: display_string}."""
        return {var_name: self.entries[var_name].get() for _, var_name, _p, _t in self._get_all_field_defs()}

    def _set_field_values(self, values):
        """Populate entries from a dict of {var_name: display_string}."""
        for _, var_name, _p, _t in self._get_all_field_defs():
            if var_name in values:
                self.entries[var_name].set(values[var_name])

    def _validate_and_parse(self):
        """Parse all fields, return dict of {var_name: parsed_value} or None on error."""
        result = {}
        for _, var_name, ptype, _tip in self._get_all_field_defs():
            val, err = _parse_value(self.entries[var_name].get(), ptype)
            if err:
                messagebox.showerror("Validation Error", f"{var_name}: {err}")
                return None
            result[var_name] = val
        return result

    # ── Preset management ────────────────────────────────────────

    def _refresh_preset_list(self):
        presets = _load_presets()
        names = [n for n in presets if n != "__last_used__"]
        self.preset_combo["values"] = names
        if self.preset_var.get() not in names:
            self.preset_var.set("")

    def _on_preset_selected(self, _event=None):
        name = self.preset_var.get()
        presets = _load_presets()
        if name in presets:
            self._set_field_values(presets[name])

    def _save_preset(self):
        current = self.preset_var.get()
        dialog = _PromptDialog(self, "Save Preset", "Preset name:", default=current)
        name = dialog.result
        if not name:
            return
        presets = _load_presets()
        presets[name] = self._get_field_values()
        _save_presets(presets)
        self._refresh_preset_list()
        self.preset_var.set(name)

    def _delete_preset(self):
        name = self.preset_var.get()
        if not name:
            return
        presets = _load_presets()
        if name in presets:
            del presets[name]
            _save_presets(presets)
        self._refresh_preset_list()

    def _save_last_used(self):
        presets = _load_presets()
        presets["__last_used__"] = self._get_field_values()
        _save_presets(presets)

    def _load_last_used(self):
        presets = _load_presets()
        if "__last_used__" in presets:
            self._set_field_values(presets["__last_used__"])

    # ── Run pipeline ─────────────────────────────────────────────

    def _run_pipeline(self):
        if self._running:
            return

        parsed = self._validate_and_parse()
        if parsed is None:
            return

        # Inject settings into pipeline module
        for var_name, val in parsed.items():
            setattr(pipeline, var_name, val)

        self._save_last_used()

        # Clear log
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.run_btn.configure(state="disabled")
        self._running = True

        def worker():
            try:
                pipeline.main()
            except SystemExit:
                pipeline.log.error("Pipeline exited with an error")
            except Exception as e:
                pipeline.log.error(f"Pipeline failed: {e}")
            finally:
                self.after(0, self._on_pipeline_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_pipeline_done(self):
        self._running = False
        self.run_btn.configure(state="normal")

    def _on_close(self):
        pipeline.log.removeHandler(self._log_handler)
        self._log_handler.closed = True
        self.destroy()


# ─── Simple prompt dialog ────────────────────────────────────────

class _PromptDialog(tk.Toplevel):
    """A simple modal dialog that asks for a string."""

    def __init__(self, parent, title, prompt, default=""):
        super().__init__(parent)
        self.title(title)
        bg = ttk.Style(self).lookup("TFrame", "background") or "#f0f0f0"
        self.configure(bg=bg)
        self.result = None
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=prompt).pack(anchor="w", pady=(0, 4))
        self._var = tk.StringVar(value=default)
        entry = ttk.Entry(frame, textvariable=self._var, width=30)
        entry.pack(fill="x")
        entry.select_range(0, "end")
        entry.focus_set()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=4)

        entry.bind("<Return>", lambda e: self._ok())
        entry.bind("<Escape>", lambda e: self.destroy())

        self.wait_window()

    def _ok(self):
        self.result = self._var.get().strip()
        self.destroy()


# ─── Entry point ─────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
