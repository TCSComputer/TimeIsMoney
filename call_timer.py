#!/usr/bin/env python3
"""
Phone Support Timer — portable, Discord-style, CSV logging

- New Call / Pause / End Call
- Live elapsed time + live cost preview
- Reads/writes hourly rate from JSON; prefers EXE folder, falls back to %APPDATA%
- Styled Call Summary collects customer info & tech notes and logs to CSV
- CSV fields: CUSTOMER_NAME, CUSTOMER_NUMBER, START_TIME, END_TIME, TOTAL_$, RATE_$, TECH_NOTES

Build (Nuitka, Python 3.12 recommended):
  python -m nuitka call_timer.py --onefile --standalone --mingw64 --assume-yes-for-downloads --enable-plugin=tk-inter --windows-console-mode=disable --windows-icon-from-ico=support.ico --product-name="Phone Support Timer" --file-version=1.0.0 --product-version=1.0.0 --output-filename="Phone Support Timer.exe" --remove-output
"""

import csv
import json
import math
import os
import sys
import time
import datetime as dt
import tkinter as tk
from tkinter import messagebox

# ---------------- Portable paths ----------------
APP_NAME    = "Phone Support Timer"
CONFIG_NAME = "phone_timer_config.json"
DEFAULT_RATE = 120.00  # $/hour default

def app_dir() -> str:
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
    if os.path.exists(exe_cfg):
        return exe_cfg
    if _can_write(exe_dir):
        return exe_cfg
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    cfg_dir = os.path.join(appdata, APP_NAME)
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, CONFIG_NAME)

APP_DIR     = app_dir()
CONFIG_PATH = resolve_config_path()
ICON_PATH   = os.path.join(APP_DIR, "support.ico")
LOG_PATH    = os.path.join(os.path.dirname(CONFIG_PATH), "call_log.csv")  # CSV lives with the config

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

CSV_HEADERS = ["CUSTOMER_NAME","CUSTOMER_NUMBER","START_TIME","END_TIME","TOTAL_$","RATE_$","TECH_NOTES"]

# ---------------- App ----------------
class CallTimerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=C_BG)
        self.geometry("680x400")
        self.minsize(680, 400)
        self.resizable(False, False)

        if os.path.exists(ICON_PATH):
            try: self.iconbitmap(ICON_PATH)
            except Exception: pass

        # State
        self.rate_per_hour = self._load_rate()
        self.running = False
        self.paused = False
        self.start_time = None            # perf_counter start
        self.call_started_at = None       # wall clock start (datetime)
        self.paused_accum = 0.0
        self.pause_started = None

        # UI
        self._build_ui()
        self._center_on_screen()
        self._update_labels()

    # -------- Config I/O --------
    def _load_rate(self) -> float:
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

        # Footer: show actual config & log paths
        footer = tk.Frame(self, bg=C_BG); footer.pack(pady=(6, 10))
        p1 = tk.Label(footer, text="Config:", fg=C_SUBTEXT, bg=C_BG, font=("Segoe UI", 9))
        p1.pack()
        self.path_cfg = tk.Label(footer, text=f"{CONFIG_PATH}", fg=C_BLURPLE, bg=C_BG, font=("Segoe UI", 9, "underline"),
                                 cursor="hand2", wraplength=640, justify="center")
        self.path_cfg.pack()
        self.path_cfg.bind("<Button-1>", lambda _e: self._open_path(CONFIG_PATH))

        p2 = tk.Label(footer, text="CSV Log:", fg=C_SUBTEXT, bg=C_BG, font=("Segoe UI", 9))
        p2.pack(pady=(4,0))
        self.path_log = tk.Label(footer, text=f"{LOG_PATH}", fg=C_BLURPLE, bg=C_BG, font=("Segoe UI", 9, "underline"),
                                 cursor="hand2", wraplength=640, justify="center")
        self.path_log.pack()
        self.path_log.bind("<Button-1>", lambda _e: self._open_path(LOG_PATH))

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

    def _open_path(self, path):
        try:
            folder = os.path.dirname(path) or "."
            os.startfile(folder)
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

    # -------- CSV Logging --------
    def _ensure_log_header(self):
        need_header = not os.path.exists(LOG_PATH) or os.path.getsize(LOG_PATH) == 0
        if need_header:
            try:
                with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(CSV_HEADERS)
            except Exception as e:
                messagebox.showerror("CSV Error", f"Couldn't create CSV at:\n{LOG_PATH}\n\n{e}")

    def _append_log_row(self, row: dict):
        self._ensure_log_header()
        try:
            with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([row.get(h, "") for h in CSV_HEADERS])
        except Exception as e:
            messagebox.showerror("CSV Error", f"Couldn't write to CSV at:\n{LOG_PATH}\n\n{e}")

    # -------- Actions --------
    def on_new(self):
        if self.running:
            if not messagebox.askyesno("Start New Call?", "A call is already in progress. Reset the timer?"):
                return
        self.running = True
        self.paused = False
        self.start_time = self._now()
        self.call_started_at = dt.datetime.now()
        self.paused_accum = 0.0
        self.pause_started = None
        self._enable(self.pause_btn)
        self._enable(self.end_btn)

    def on_pause(self):
        if not self.running: return
        if not self.paused:
            self.paused = True
            self.pause_started = self._now()
            self.pause_btn.config(text="Resume")
        else:
            self.paused = False
            if self.pause_started is not None:
                self.paused_accum += self._now() - self.pause_started
            self.pause_started = None
            self.pause_btn.config(text="Pause")

    def _show_summary_and_collect(self, duration_str: str, rate: float, raw_cost: float, final_cost: int,
                                  start_dt: dt.datetime, end_dt: dt.datetime):
        """Discord-like summary popup with fields and CSV logging."""
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

        body = tk.Frame(card, bg=C_SURFACE); body.pack(padx=16, pady=(4, 6), anchor="w")

        def row(label, value, value_fg=C_TEXT, mono=True):
            r = tk.Frame(body, bg=C_SURFACE); r.pack(anchor="w", pady=3)
            tk.Label(r, text=label, fg=C_SUBTEXT, bg=C_SURFACE, font=FONT_LABEL).pack(side="left")
            tk.Label(r, text=value, fg=value_fg, bg=C_SURFACE, font=("Consolas", 14, "bold") if mono else ("Segoe UI", 12, "bold")).pack(side="left", padx=8)

        row("Call Duration:",      duration_str)
        row("Rate:",               f"${rate:,.2f} / hr")
        row("Calculated Cost:",    f"${raw_cost:,.2f}")
        row("Final (rounded up):", f"${final_cost:,d}", value_fg=C_ACCENT)
        row("Start:",              start_dt.strftime("%Y-%m-%d %H:%M:%S"))
        row("End:",                end_dt.strftime("%Y-%m-%d %H:%M:%S"))

        # Inputs
        form = tk.Frame(card, bg=C_SURFACE); form.pack(padx=16, pady=(10, 0), fill="x")
        tk.Label(form, text="Customer Name", fg=C_SUBTEXT, bg=C_SURFACE, font=FONT_LABEL).grid(row=0, column=0, sticky="w")
        name_ent = tk.Entry(form, font=("Segoe UI", 11), width=36); name_ent.grid(row=0, column=1, padx=(8,0), pady=3, sticky="w")

        tk.Label(form, text="Customer Number", fg=C_SUBTEXT, bg=C_SURFACE, font=FONT_LABEL).grid(row=1, column=0, sticky="w")
        num_ent = tk.Entry(form, font=("Segoe UI", 11), width=36); num_ent.grid(row=1, column=1, padx=(8,0), pady=3, sticky="w")

        tk.Label(form, text="Tech Notes", fg=C_SUBTEXT, bg=C_SURFACE, font=FONT_LABEL).grid(row=2, column=0, sticky="nw")
        notes_txt = tk.Text(form, font=("Segoe UI", 10), width=48, height=5, wrap="word", bg="#232428", fg=C_TEXT, relief="flat")
        notes_txt.grid(row=2, column=1, padx=(8,0), pady=3, sticky="w")

        # Buttons
        btnbar = tk.Frame(card, bg=C_SURFACE); btnbar.pack(fill="x", padx=16, pady=(10, 14))

        def make_btn(text, command, bg="#4e5058", hover="#5a5d62"):
            b = tk.Label(btnbar, text=text, bg=bg, fg=C_TEXT, font=("Segoe UI", 10, "bold"),
                         padx=14, pady=6, cursor="hand2", borderwidth=0, relief="flat")
            b.pack(side="right", padx=6)
            b.bind("<Enter>", lambda e: b.config(bg=hover))
            b.bind("<Leave>", lambda e: b.config(bg=bg))
            b.bind("<Button-1>", lambda e: command())
            return b

        def close():
            win.grab_release(); win.destroy()

        def do_copy():
            txt = (f"Call Duration: {duration_str}\n"
                   f"Rate: ${rate:,.2f} / hr\n"
                   f"Calculated Cost: ${raw_cost:,.2f}\n"
                   f"Final (rounded up): ${final_cost:,d}\n"
                   f"Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"End:   {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            try: self.clipboard_clear(); self.clipboard_append(txt)
            except Exception: pass

        def do_save():
            row = {
                "CUSTOMER_NAME":   name_ent.get().strip(),
                "CUSTOMER_NUMBER": num_ent.get().strip(),
                "START_TIME":      start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "END_TIME":        end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "TOTAL_$":         f"{final_cost:.2f}",
                "RATE_$":          f"{rate:.2f}",
                "TECH_NOTES":      notes_txt.get("1.0", "end").strip(),
            }
            self._append_log_row(row)
            close()

        make_btn("Save Log", do_save, bg=C_GREEN, hover=C_GREEN_H)
        make_btn("Copy",     do_copy)
        make_btn("Skip",     close, bg=C_RED, hover=C_RED_H)

        # Place & modal
        win.update_idletasks()
        w, h = 520, 520
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.deiconify(); win.grab_set()
        name_ent.focus_set()
        win.bind("<Return>", lambda _e: do_save())
        win.bind("<Escape>", lambda _e: close())
        self.wait_window(win)

    def on_end(self):
        if not self.running:
            messagebox.showinfo("No Active Call", "Start a call with 'New Call'.")
            return

        if self.paused and self.pause_started is not None:
            self.paused_accum += self._now() - self.pause_started
            self.pause_started = None

        secs = self._elapsed_seconds()
        raw_cost = self._cost(secs)
        final_cost = math.ceil(raw_cost)
        start_dt = self.call_started_at or dt.datetime.now()
        end_dt = dt.datetime.now()

        # Styled popup with fields + CSV logging
        self._show_summary_and_collect(self._format_hms(secs), self.rate_per_hour, raw_cost, final_cost, start_dt, end_dt)

        # Reset AFTER popup closes
        self.running = False
        self.paused = False
        self.start_time = None
        self.call_started_at = None
        self.paused_accum = 0.0
        self.pause_started = None
        self._disable(self.pause_btn)
        self._disable(self.end_btn)
        self.pause_btn.config(text="Pause")

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