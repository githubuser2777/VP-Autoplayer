# gui.py
#!/usr/bin/env python3
"""Tk/ttk front-end for the Virtual-/Roblox-Piano Autoplayer.

• Per-sheet BPM / Subdivision saved & restored via #META header  
• Progress bar and time label always in real seconds  
• Editing BPM / Subdivision / Humanise / Hold while playing retimes the next note  
• Humanise slider shows tick-marks at 50 % and 75 %  
• Toggle-key field applies immediately
"""

from __future__ import annotations
from queue import Queue, Empty
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pynput.keyboard import Listener, Key
from ttkbootstrap import Style

import autoplayer_core as core
CFG = core.CFG

ACCENT   = "#007acc"
BG_LIGHT = "#f7f9fc"
BG_DARK  = "#1e1e1e"

# ────────────────────────── tooltip helper ───────────────────────────
class Tip:
    def __init__(self, widget: tk.Widget, text: str):
        self.text = text
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        self.top: tk.Toplevel | None = None

    def _show(self, evt):
        if self.top: return
        x = evt.widget.winfo_rootx() + 10
        y = evt.widget.winfo_rooty() + evt.widget.winfo_height() + 6
        self.top = tw = tk.Toplevel(evt.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True, "-alpha", 0.95)
        tk.Label(
            tw, text=self.text, bg="#222", fg="#f0f0f0",
            font=("Segoe UI", 9), wraplength=260, justify="left",
            padx=8, pady=4
        ).pack()
        tw.geometry(f"+{x}+{y}")

    def _hide(self, _):
        if self.top:
            self.top.destroy(); self.top = None

# ───────────────────── hot-key parser ────────────────────────────────
def parse_combo(expr: str) -> frozenset[Key | str]:
    mod = {"ctrl": Key.ctrl, "alt": Key.alt, "shift": Key.shift,
           "cmd": Key.cmd,  "meta": Key.cmd}
    named = {f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)} | {
        "space": Key.space, "enter": Key.enter, "tab": Key.tab,
        "backspace": Key.backspace, "esc": Key.esc, "escape": Key.esc,
    }
    return frozenset(mod.get(p) or named.get(p) or p
                     for p in expr.lower().split("+") if p)

# ─────────────────────────── GUI class ───────────────────────────────
class App(tk.Tk):
    # ─── per-sheet META I/O helpers ──────────────────────────────────
    def _store_current_meta(self):
        try:
            bpm    = int(self.var_bpm.get())
            subdiv = max(0.1, float(self.var_sub.get()))
            note   = self._get_note_text()
            core.write_sheet_meta(CFG.sheet, bpm, subdiv, note)
        except ValueError:
            pass

    # ctor ------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self.title("VP Autoplayer")
        self.attributes("-topmost", True)
        self.minsize(500, 565)
        try:
            icon_path = Path(__file__).with_name("Icon.ico")
            if icon_path.exists():
                self.iconbitmap(default=str(icon_path))
        except Exception:
            pass

        scale = self._detect_scaling()*1.2
        self.tk.call("tk", "scaling", scale)
        self.option_add("*Font", ("Segoe UI", int(12*scale/1.2)))

        self.style = Style("darkly" if CFG.dark else "flatly")
        self.configure(bg=BG_DARK if CFG.dark else BG_LIGHT)

        # runtime
        self.queue: Queue = Queue()
        self.player: core.Player | None = None
        self.total_tokens = self._tok_done = 0
        self.toggle_combo = parse_combo(CFG.toggle)
        self._pressed: set = set()
        self._suspend_trace = False

        self._build_form()
        self._build_fab()
        self._on_sheet_change()

        Listener(on_press=self._hk_press,
                 on_release=self._hk_release,
                 daemon=True).start()
        self.after(50, self._poll)

    # ─── UI builders -------------------------------------------------
    def _info_icon(self, parent, txt):
        size, pad, bg = 16, 1, self.cget("background")
        cv = tk.Canvas(parent, width=size, height=size, bg=bg,
                       highlightthickness=0, bd=0, cursor="hand2")
        cv.create_oval(pad, pad, size-pad, size-pad, fill=ACCENT, outline="")
        cv.create_text(size//2, size//2, text="i", fill="white",
                       font=("Segoe UI", 8, "bold"))
        Tip(cv, txt); return cv

    def _build_form(self):
        body = ttk.Frame(self, padding=12)
        body.pack(expand=True, fill="both"); body.columnconfigure(1, weight=1)

        info = {
            "Sheet":       "Song text file",
            "BPM":         "Beats per minute – tempo",
            "Subdivision": "Notes per beat (4 = quarter, 8 = eighth, …)",
            "Humanise %":  ("0% ⇒ Disabled, 100% accuracy \n"
                            "0–49 %  ⇒ near-perfect timing\n"
                            "50–74 % ⇒ realistic player\n"
                            "75–100 % ⇒ sloppy human feel"),
            "Hold %":      "Key-down fraction of each note",
            "Toggle key":  "Global hot-key to Start / Pause playback",
            "Target":      "Only auto-play when this window is focused",
            "Auto":        "Pause whenever the window loses focus",
            "Note":        "Stores a short message to the sheet. Ex: Transposition -5"
        }

        def row(r, lbl, widget, key=None):
            fr = ttk.Frame(body)
            ttk.Label(fr, text=lbl).pack(side="left")
            if key: self._info_icon(fr, info[key]).pack(side="left", padx=(4,0))
            fr.grid(row=r, column=0, sticky="w", padx=(0,6), pady=3)
            widget.grid(row=r, column=1, sticky="ew", pady=3)

        # Folder
        self.var_folder = tk.StringVar(value=str(CFG.folder))
        fr = ttk.Frame(body)
        ttk.Entry(fr, textvariable=self.var_folder).pack(side="left", fill="x", expand=True)
        ttk.Button(fr, text="Browse", command=self._pick_folder).pack(side="left", padx=4)
        row(0, "Folder", fr)

        # Sheet
        self.var_sheet = tk.StringVar()
        self.box_sheet = ttk.Combobox(body, textvariable=self.var_sheet, state="readonly")
        self.box_sheet.bind("<<ComboboxSelected>>", self._on_sheet_change)
        row(1, "Sheet", self.box_sheet, "Sheet")

        # BPM / Subdivision
        self.var_bpm = tk.StringVar(); self.var_sub = tk.StringVar()
        self.var_bpm.trace_add("write", lambda *_: self._timing_changed())
        self.var_sub.trace_add("write", lambda *_: self._timing_changed())
        row(2, "BPM", ttk.Entry(body, textvariable=self.var_bpm, width=6, justify="center"), "BPM")
        row(3, "Subdivision", ttk.Entry(body, textvariable=self.var_sub, width=6, justify="center"), "Subdivision")

        # Humanise / Hold
        self.var_human = tk.IntVar(value=int(CFG.human*100))
        self.var_hold  = tk.IntVar(value=int(CFG.hold *100))
        self.var_human.trace_add("write", lambda *_: self._expressiveness_changed())
        self.var_hold .trace_add("write", lambda *_: self._expressiveness_changed())
        row(4, "Humanise %", self._percent_slider(body, self.var_human, marks=[50,75]), "Humanise %")
        row(5, "Hold %",     self._percent_slider(body, self.var_hold),               "Hold %")

        # Toggle key (instant update)
        self.var_key = tk.StringVar(value=CFG.toggle)
        self.var_key.trace_add("write", lambda *_: self._toggle_key_changed())
        row(6, "Toggle key", ttk.Entry(body, textvariable=self.var_key, width=12), "Toggle key")

        # NEW ───────────── Notes row ─────────────
        note_fr = ttk.Frame(body)
        self.txt_note = tk.Text(note_fr, width=1, height=3, wrap="word")
        self.txt_note.pack(fill="both", expand=True)
        self.txt_note.bind("<KeyRelease>", lambda _e: self._note_changed())
        row(7, "Note", note_fr, "Note")

        # Theme & Auto-pause
        self.theme_btn = ttk.Button(body, text="🌙" if CFG.dark else "☀",
                                    width=4, command=self._flip)
        row(8, "Mode", self.theme_btn)

        # Target window
        self.var_win = tk.StringVar()
        self.box_win = ttk.Combobox(body, textvariable=self.var_win, state="readonly")
        self.box_win.bind("<Button-1>", lambda _e: self._refresh_windows())
        row(9, "Target", self.box_win, "Target")

        self.var_auto = tk.BooleanVar(value=CFG.auto_pause)
        ck = ttk.Checkbutton(body, text="Auto-play when focused",
                             variable=self.var_auto, command=self._toggle_auto)
        ck.grid(row=10, column=0, columnspan=2, sticky="w", pady=(4,0))
        Tip(ck, info["Auto"])

        # Progress
        self.prog = ttk.Progressbar(body, mode="determinate")
        self.prog.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(10,2))
        self.lbl_time = tk.Label(body, text="00:00 / 00:00")
        self.lbl_time.grid(row=12, column=0, columnspan=2, sticky="e")

        self._refresh_sheets(); self._refresh_windows()

    def _note_changed(self):
        # save on every keystroke
        self._store_current_meta()

    def _get_note_text(self) -> str:
        return self.txt_note.get("1.0", "end-1c").strip()

    # slider helper (with optional tick marks) ------------------------
    def _percent_slider(self, parent: tk.Widget, var: tk.IntVar, marks=None):
        fr = ttk.Frame(parent)
        bar = ttk.Frame(fr); bar.pack(side="left", fill="x", expand=True)
        ttk.Scale(bar, from_=0, to=100, orient="horizontal", variable=var,
                  command=lambda v: var.set(max(0, min(100, int(float(v)))))) \
            .pack(fill="x", expand=True)
        if marks:
            bg = parent.winfo_toplevel().cget("background")
            canvas = tk.Canvas(bar, height=8, highlightthickness=0, bg=bg)
            canvas.pack(fill="x")
            def _redraw(e):
                canvas.delete("all"); w=e.width
                for m in marks:
                    x = w*m/100; canvas.create_line(x,1,x,7,width=2,fill=ACCENT)
            canvas.bind("<Configure>", _redraw)
        ttk.Entry(fr, textvariable=var, width=4, justify="center")\
            .pack(side="left", padx=4)
        return fr

    def _build_fab(self):
        self.fab = tk.Button(self, text="▶", fg="#fff", bg=ACCENT,
                             activebackground="#0a61b5",
                             font=("Segoe UI", 18, "bold"),
                             bd=0, highlightthickness=0,
                             command=self._fab_pressed)
        self.fab.place(relx=1, rely=1, x=-24, y=-24, width=52, height=52, anchor="se")

    # ─── live-update: Toggle-key -------------------------------------
    def _toggle_key_changed(self):
        txt = self.var_key.get().strip()
        try:
            combo = parse_combo(txt)
            if combo:
                CFG.toggle = txt
                self.toggle_combo = combo
                self._pressed.clear()
        except Exception:
            pass

    # ─── callbacks & logic ───────────────────────────────────────────
    def _pick_folder(self):
        if (d := filedialog.askdirectory(initialdir=CFG.folder)):
            CFG.folder = Path(d); self.var_folder.set(d); self._refresh_sheets()

    def _refresh_sheets(self):
        vals = [p.name for p in sorted(CFG.folder.glob("*.txt"))]
        self.box_sheet["values"] = vals
        if vals and self.var_sheet.get() not in vals:
            self.var_sheet.set(vals[0])

    def _refresh_windows(self):
        self.box_win["values"] = [t for _, t in core.windows()]

    # sheet switch
    def _on_sheet_change(self, _=None):
        self._store_current_meta()
        new_sheet = CFG.folder / self.var_sheet.get()
        if not new_sheet.exists(): return
        CFG.sheet = new_sheet
        meta = core.read_sheet_meta(CFG.sheet)
        self._suspend_trace = True
        self.var_bpm.set(str(meta.get("bpm",    CFG.bpm)))
        self.var_sub.set(str(meta.get("subdiv", CFG.subdiv)))
        note = meta.get("note", "")
        self.txt_note.delete("1.0", "end")
        if note: self.txt_note.insert("1.0", note)
        self._suspend_trace = False
        self._timing_changed()
        if self.player:
            self._stop_player()
            if self._apply_cfg(): self._start_player()
            else: self._update_time(self._tok_done)

    # tempo edited
    def _timing_changed(self):
        if self._suspend_trace: return
        try:
            CFG.bpm    = int(self.var_bpm.get())
            CFG.subdiv = max(0.1, float(self.var_sub.get()))
        except ValueError: return
        core.write_sheet_meta(CFG.sheet, CFG.bpm, CFG.subdiv, self._get_note_text())
        if self.total_tokens:
            self.prog["maximum"] = self.total_tokens * CFG.sec_per_tok()
            self.prog["value"]   = self._tok_done   * CFG.sec_per_tok()
        self._update_time(self._tok_done)

    # Humanise / Hold change
    def _expressiveness_changed(self):
        CFG.human = max(0.0, min(1.0, self.var_human.get()/100))
        CFG.hold  = max(0.0, min(1.0, self.var_hold .get()/100))
        self.var_human.set(int(CFG.human*100))
        self.var_hold .set(int(CFG.hold *100))

    # auto-pause toggle
    def _toggle_auto(self):
        if self.var_auto.get() and not self.var_win.get().strip():
            messagebox.showwarning("Target window required",
                                   "Select a target window before enabling Auto-play.")
            self.var_auto.set(False); return
        CFG.auto_pause = self.var_auto.get()

    # play / pause
    def _fab_pressed(self):
        if not self.player:
            if not self._apply_cfg(): return
            self._start_player()
        else:
            self.player.toggle(); self._update_fab_icon()

    # validate / apply
    def _apply_cfg(self) -> bool:
        try:
            CFG.human  = self.var_human.get()/100
            CFG.hold   = self.var_hold .get()/100
            CFG.toggle = self.var_key.get()
            CFG.folder = Path(self.var_folder.get())
            if self.var_sheet.get(): CFG.sheet = CFG.folder / self.var_sheet.get()
            self.toggle_combo = parse_combo(CFG.toggle)
        except Exception as exc:
            messagebox.showerror("Config error", str(exc)); return False
        CFG.target_title = self.var_win.get().strip() or None
        if self.var_auto.get() and not CFG.target_title:
            messagebox.showwarning("Target window required",
                                   "Auto-play is enabled but no target window selected.")
            return False
        self._store_current_meta(); return True

    # player control
    def _start_player(self):
        self.total_tokens = self._tok_done = 0
        self.prog.config(value=0, maximum=1, mode="determinate")
        self.player = core.Player(CFG.sheet, self.queue); self.player.start()
        self._update_fab_icon()

    def _stop_player(self):
        if self.player:
            self.player.stop(); self.player = None; self._update_fab_icon()

    def _update_fab_icon(self):
        self.fab["text"] = "⏸" if (self.player and self.player.resume_evt.is_set()) else "▶"

    # hot-key hooks
    def _hk_press(self, k):
        if k in self.toggle_combo: self._pressed.add(k)
        if self.toggle_combo.issubset(self._pressed): self.after(0, self._fab_pressed)
    def _hk_release(self, k): self._pressed.discard(k)

    # queue poller
    def _poll(self):
        try:
            while True:
                tag, *d = self.queue.get_nowait()
                if tag == "total":
                    self.total_tokens = d[0]
                    self.prog["maximum"] = self.total_tokens * CFG.sec_per_tok()
                    self._update_time(0)
                elif tag == "progress":
                    self._tok_done = d[0]
                    self.prog["value"] = self._tok_done * CFG.sec_per_tok()
                    self._update_time(self._tok_done)
                elif tag == "done":
                    self._stop_player()
                    self.prog["value"] = self.total_tokens * CFG.sec_per_tok()
        except Empty: pass
        self.after(50, self._poll)

    def _update_time(self, done_tok: int):
        if not self.total_tokens: return
        sec_done = done_tok * CFG.sec_per_tok()
        sec_tot  = self.total_tokens * CFG.sec_per_tok()
        fmt = lambda s: f"{int(s//60):02d}:{int(s%60):02d}"
        self.lbl_time["text"] = f"{fmt(sec_done)} / {fmt(sec_tot)}"

    # theme / DPI / shutdown
    def _flip(self):
        CFG.dark = not CFG.dark
        self.style.theme_use("darkly" if CFG.dark else "flatly")
        self.configure(bg=BG_DARK if CFG.dark else BG_LIGHT)
        self.theme_btn["text"] = "🌙" if CFG.dark else "☀"

    @staticmethod
    def _detect_scaling() -> float:
        try:
            import ctypes
            user32 = ctypes.windll.user32; user32.SetProcessDPIAware()
            hdc = ctypes.windll.gdi32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            ctypes.windll.gdi32.ReleaseDC(0, hdc)
            return dpi / 96
        except Exception: return 1.0

    def destroy(self):
        self._store_current_meta(); self._stop_player(); core.save_cfg(); super().destroy()

# ─────────────────────────── run ─────────────────────────────────────
if __name__ == "__main__":
    App().mainloop()
