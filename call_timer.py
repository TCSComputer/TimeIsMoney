#!/usr/bin/env python3
"""
Phone Support Timer — portable, Discord-style & robust config path

- New Call / Pause / End Call
- Live elapsed time + live cost preview
- Reads/writes hourly rate from JSON; prefers EXE folder, falls back to %APPDATA%
- Shows the exact config path (click to open folder)
- One-file packager friendly (PyInstaller / Nuitka)

Build (Nuitka, Python 3.12 recommended):
  python -m nuitka call_timer.py --onefile --standalone --mingw64 --assume-yes-for-downloads --enable-plugin=tk-inter --windows-console-mode=disable --windows-icon-from-ico=support.ico --product-name="Phone Support Timer" --file-version=1.0.0 --product-version=1.0.0 --output-filename="Phone Support Timer.exe" --remove-output
"""

import json
import math
import os
import sys
import time
import tkinter as tk
from tkinter import messagebox

# ---------------- Portable paths ----------------
APP_NAME   = "Phone Support Timer"
CONFIG_NAME = "phone_timer_config.json"
DEFAULT_RATE = 120.00  # $/hour default

def app_dir() -> str:
    # Directory of the executable when frozen, else script directory.
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _can_write(folder: str) -> bool:
    try:
        test_path = os.path.join(folder, ".writetest.tmp")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_path)
        return True
    except Exception:
        return False

def resolve_config_path() -> str:
    exe_dir = app_dir()
    exe_cfg = os.path.join(exe_dir, CONFIG_NAME)

    # 1) If a JSON already exists next to the EXE, always use it (read-only is fine).
    if os.path.exists(exe_cfg):
        return exe_cfg

    # 2) If EXE folder is writable, use/create JSON there (portable mode).
    if _can_write(exe_dir):
        return exe_cfg

    # 3) Fallback to %APPDATA%\Phone Support Timer\phone_timer_config.json
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    cfg_dir = os.path.join(appdata, APP_NAME)
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, CONFIG_NAME)

APP_DIR     = app_dir()
CONFIG_PATH = resolve_config_path()
ICON_PATH   = os.path.join(APP_DIR, "support.ico")

# ---------------- Theme (Discord-inspired) ----------------
C_BG       = "#1e1f22"
C_SURFACE  = "#2b2d31"
C_TEXT     = "#ffffff"
C_SUBTEXT  = "#b5bac1"
C_ACCENT   = "#57f287"
C_GREEN    = "#3ba55d"
C_GREEN_H  = "#43b06a"
C_YELLOW   = "#f0b232"
C_YELLOW_H = "#f5be49"
C_RED      = "#ed4245"
C_RED_H    = "#f04747"
C_BORDER   = "#202225"
C_SHADOW   = "#191a1d"
C_BLURPLE  = "#5865F2"

FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_LABEL = ("Segoe UI", 11)
FONT_VALUE = ("Consolas", 34, "bold")
FONT_COST  = ("Consolas", 28, "bold")

# ---------------- App ----------------
class CallTimerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=C_BG)
        self.geometry("680x380")
        self.minsize(680, 380)
        self.resizable(False, False)

        if os.path.exists(ICON_PATH):
            try: self.iconbitmap(ICON_PATH)
            except Exception: pass

        # State
        self.rate_per_hour = self._load_rate()
        self.running = False
        self.paused = False
        self.start_time = None
        self.paused_accum = 0.0
        self.pause_started = None

        # UI
        self._build_ui()
        self._center_on_screen()
        self._update_labels()

    # -------- Config I/O --------
    def _load_rate(self) -> float:
        # Create default file if missing
        if not os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump({"rate_per_hour": DEFAULT_RATE}, f, indent=2)
            except Exception as e:
                messagebox.showerror(
                    "Config Error",
                    f"Couldn't create config at:\n{CONFIG_PATH}\n\n{e}\n\n"
                    f"Using default rate ${DEFAULT_RATE:.2f} for this session."
                )
                return float(DEFAULT_RATE)

        # Read JSON
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return float(data.get("rate_per_hour", DEFAULT_RATE))
        except Exception as e:
            messagebox.showerror(
                "Config Error",
                f"Couldn't read config at:\n{CONFIG_PATH}\n\n{e}\n\n"
                f"Using default rate ${DEFAULT_RATE:.2f} for this session."
            )
            return float(DEFAULT_RATE)

    def _save_rate(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"rate_per_hour": self.rate_per_hour}, f, indent=2)
        except Exception as e:
            messagebox.showerror("Config Error", f"Couldn't save config at:\n{CONFIG_PATH}\n\n{e}")

    # -------- UI --------
    def _build_ui(self):
        tk.Frame(self, bg=C_BG, height=8).pack(fill="x")

        title = tk.Label(self, text=APP_NAME, fg=C_TEXT, bg=C_BG, font=FONT_TITLE)
        title.pack(pady=(6, 2))

        self.rate_lbl = tk.Label(self, text="", fg=C_SUBTEXT, bg=C_BG, font=FONT_LABEL)
        self.rate_lbl.pack(pady=(0, 10))

        shadow = tk.Frame(self, bg=C_SHADOW)
        shadow.pack(pady=6)
        card = tk.Frame(shadow, bg=C_SURFACE, bd=1, relief="solid", highlightthickness=0)
        card.pack(padx=2, pady=2)
        card.configure(highlightbackground=C_BORDER)

        row1 = tk.Frame(card, bg=C_SURFACE); row1.pack(padx=24, pady=(16, 6))
        tk.Label(row1, text="Elapsed:", fg=C_SUBTEXT, bg=C_SURFACE, font=FONT_LABEL)\
            .grid(row=0, column=0, padx=(0, 10), sticky="e")
        self.elapsed_lbl = tk.Label(row1, text="00:00:00", fg=C_TEXT, bg=C_SURFACE, font=FONT_VALUE)
        self.elapsed_lbl.grid(row=0, column=1, sticky="w")

        row2 = tk.Frame(card, bg=C_SURFACE); row2.pack(padx=24, pady=(6, 18))
        tk.Label(row2, text="Live Cost:", fg=C_SUBTEXT, bg=C_SURFACE, font=FONT_LABEL)\
            .grid(row=0, column=0, padx=(0, 10), sticky="e")
        self.cost_lbl = tk.Label(row2, text="$0.00", fg=C_ACCENT, bg=C_SURFACE, font=FONT_COST)
        self.cost_lbl.grid(row=0, column=1, sticky="w")

        controls = tk.Frame(self, bg=C_BG); controls.pack(pady=12)
        self.new_btn   = self._make_btn(controls, "New Call", self.on_new,   C_GREEN,  C_GREEN_H)
        self.pause_btn = self._make_btn(controls, "Pause",    self.on_pause, C_YELLOW, C_YELLOW_H, state="disabled")
        self.end_btn   = self._make_btn(controls, "End Call", self.on_end,   C_RED,    C_RED_H,    state="disabled")
        self.new_btn.grid(row=0, column=0, padx=12)
        self.pause_btn.grid(row=0, column=1, padx=12)
        self.end_btn.grid(row=0, column=2, padx=12)

        # Footer: show actual config path (click to open folder)
        footer = tk.Frame(self, bg=C_BG); footer.pack(pady=(6, 10))
        path_label = tk.Label(footer, text="Rate config:", fg=C_SUBTEXT, bg=C_BG, font=("Segoe UI", 9))
        path_label.pack(side="left")
        self.path_link = tk.Label(
            footer, text=f" {CONFIG_PATH}", fg=C_BLURPLE, bg=C_BG, font=("Segoe UI", 9, "underline"),
            cursor="hand2", wraplength=620, justify="left"
        )
        self.path_link.pack(side="left")
        self.path_link.bind("<Button-1>", self._open_config_folder)

    def _make_btn(self, parent, text, cmd, color, hover, state="normal"):
        btn = tk.Label(
            parent, text=text, bg=color, fg=C_TEXT, font=("Segoe UI", 11, "bold"),
            padx=22, pady=10, cursor=("arrow" if state=="disabled" else "hand2")
        )
        btn._base_color = color; btn._hover_color = hover; btn._command = cmd; btn._state = state
        btn.configure(borderwidth=0, relief="flat")
        if state != "disabled":
            btn.bind("<Enter>", lambda e: btn.configure(bg=btn._hover_color))
            btn.bind("<Leave>", lambda e: btn.configure(bg=btn._base_color))
            btn.bind("<Button-1>", lambda e: btn._command())
        else:
            btn.configure(bg="#5a5d62", fg="#e6e6e6")
        return btn

    def _open_config_folder(self, _evt=None):
        try:
            folder = os.path.dirname(CONFIG_PATH) or "."
            os.startfile(folder)  # Windows
        except Exception:
            pass

    def _center_on_screen(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w)//2, (sh - h)//3
        self.geometry(f"{w}x{h}+{x}+{y}")

    # -------- Helpers --------
    def _now(self) -> float: return time.perf_counter()

    def _elapsed_seconds(self) -> float:
        if not self.running or self.start_time is None: return 0.0
        base = self._now() - self.start_time - self.paused_accum
        if self.paused and self.pause_started is not None:
            base -= (self._now() - self.pause_started)
        return max(0.0, base)

    def _format_hms(self, secs: float) -> str:
        secs = int(round(secs)); h, r = divmod(secs, 3600); m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _cost(self, secs: float) -> float:
        return (self.rate_per_hour / 3600.0) * secs

    def _update_labels(self):
        self.rate_lbl.config(text=f"Rate: ${self.rate_per_hour:,.2f} / hour")
        secs = self._elapsed_seconds()
        self.elapsed_lbl.config(text=self._format_hms(secs))
        self.cost_lbl.config(text=f"${self._cost(secs):,.2f}")
        self.after(200 if (self.running and not self.paused) else 700, self._update_labels)

    # -------- Actions --------
    def on_new(self):
        if self.running:
            if not messagebox.askyesno("Start New Call?", "A call is already in progress. Reset the timer?"):
                return
        self.running = True; self.paused = False
        self.start_time = self._now(); self.paused_accum = 0.0; self.pause_started = None
        self._enable(self.pause_btn); self._enable(self.end_btn)

    def on_pause(self):
        if not self.running: return
        if not self.paused:
            self.paused = True; self.pause_started = self._now()
            self.pause_btn.config(text="Resume")
        else:
            self.paused = False
            if self.pause_started is not None:
                self.paused_accum += self._now() - self.pause_started
            self.pause_started = None
            self.pause_btn.config(text="Pause")

    def _show_summary(self, duration_str: str, rate: float, raw_cost: float, final_cost: int):
        win = tk.Toplevel(self); win.withdraw()
        win.title("Call Summary"); win.configure(bg=C_BG); win.resizable(False, False)
        if os.path.exists(ICON_PATH):
            try: win.iconbitmap(ICON_PATH)
            except Exception: pass
        win.transient(self)

        shadow = tk.Frame(win, bg=C_SHADOW); shadow.pack(padx=12, pady=12)
        card = tk.Frame(shadow, bg=C_SURFACE, bd=1, relief="solid", highlightthickness=0)
        card.pack(padx=2, pady=2); card.configure(highlightbackground=C_BORDER)

        header = tk.Frame(card, bg=C_SURFACE); header.pack(fill="x", padx=16, pady=(12, 6))
        ico = tk.Canvas(header, width=26, height=26, bg=C_SURFACE, highlightthickness=0); ico.pack(side="left")
        ico.create_oval(2, 2, 24, 24, fill=C_BLURPLE, outline=""); ico.create_text(13, 13, text="i", fill="white", font=("Segoe UI", 14, "bold"))
        tk.Label(header, text="Call Summary", fg=C_TEXT, bg=C_SURFACE, font=("Segoe UI", 14, "bold")).pack(side="left", padx=8)

        body = tk.Frame(card, bg=C_SURFACE); body.pack(padx=16, pady=(4, 10), anchor="w")

        def row(label, value, value_fg=C_TEXT, mono=True):
            r = tk.Frame(body, bg=C_SURFACE); r.pack(anchor="w", pady=3)
            tk.Label(r, text=label, fg=C_SUBTEXT, bg=C_SURFACE, font=FONT_LABEL).pack(side="left")
            tk.Label(r, text=value, fg=value_fg, bg=C_SURFACE, font=("Consolas", 14, "bold") if mono else ("Segoe UI", 12, "bold")).pack(side="left", padx=8)

        row("Call Duration:",      duration_str)
        row("Rate:",               f"${rate:,.2f} / hr")
        row("Calculated Cost:",    f"${raw_cost:,.2f}")
        row("Final (rounded up):", f"${final_cost:,d}", value_fg=C_ACCENT)

        btnbar = tk.Frame(card, bg=C_SURFACE); btnbar.pack(fill="x", padx=16, pady=(6, 14))

        def make_btn(text, command, bg="#4e5058", hover="#5a5d62"):
            b = tk.Label(btnbar, text=text, bg=bg, fg=C_TEXT, font=("Segoe UI", 10, "bold"), padx=14, pady=6, cursor="hand2", borderwidth=0, relief="flat")
            b.pack(side="right", padx=6)
            b.bind("<Enter>", lambda e: b.config(bg=hover)); b.bind("<Leave>", lambda e: b.config(bg=bg)); b.bind("<Button-1>", lambda e: command())
            return b

        def close():
            win.grab_release(); win.destroy()

        def copy_to_clip():
            txt = (f"Call Duration: {duration_str}\n"
                   f"Rate: ${rate:,.2f} / hr\n"
                   f"Calculated Cost: ${raw_cost:,.2f}\n"
                   f"Final (rounded up): ${final_cost:,d}")
            try: self.clipboard_clear(); self.clipboard_append(txt)
            except Exception: pass

        make_btn("OK",   close, bg=C_GREEN, hover=C_GREEN_H)
        make_btn("Copy", copy_to_clip)

        win.update_idletasks()
        w, h = 420, 260
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.deiconify(); win.grab_set()
        win.bind("<Return>", lambda _e: close()); win.bind("<Escape>", lambda _e: close())
        self.wait_window(win)

    def on_end(self):
        if not self.running:
            messagebox.showinfo("No Active Call", "Start a call with 'New Call'."); return

        if self.paused and self.pause_started is not None:
            self.paused_accum += self._now() - self.pause_started; self.pause_started = None

        secs = self._elapsed_seconds(); raw_cost = self._cost(secs); final_cost = math.ceil(raw_cost)
        self._show_summary(self._format_hms(secs), self.rate_per_hour, raw_cost, final_cost)

        # Reset AFTER the popup closes
        self.running = False; self.paused = False
        self.start_time = None; self.paused_accum = 0.0; self.pause_started = None
        self._disable(self.pause_btn); self._disable(self.end_btn); self.pause_btn.config(text="Pause")

    # -------- Enable/disable fancy labels as buttons --------
    def _enable(self, lbl: tk.Label):
        lbl._state = "normal"; lbl.configure(cursor="hand2", bg=lbl._base_color, fg=C_TEXT)
        lbl.bind("<Enter>", lambda e, w=lbl: w.configure(bg=w._hover_color))
        lbl.bind("<Leave>", lambda e, w=lbl: w.configure(bg=w._base_color))
        lbl.bind("<Button-1>", lambda e, w=lbl: w._command())

    def _disable(self, lbl: tk.Label):
        lbl._state = "disabled"
        lbl.configure(cursor="arrow", bg="#5a5d62", fg="#e6e6e6")
        lbl.unbind("<Enter>"); lbl.unbind("<Leave>"); lbl.unbind("<Button-1>")

# ---------------- Main ----------------
if __name__ == "__main__":
    CallTimerApp().mainloop()
