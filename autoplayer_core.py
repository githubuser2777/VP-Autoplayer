#!/usr/bin/env python3
"""Virtual-/Roblox-Piano Autoplayer – density- & Shift-aware humaniser (July 2025)

• 0 % = exact robot playback  
• 1–50 % ultra-tight • 50–75 % balanced realism • 75–100 % sloppy / intermediate  
"""

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Tuple
import json, threading, time, sys, math, random

import win32gui
from pynput.keyboard import Controller, Key

__all__ = [
    "CFG", "save_cfg", "windows", "Player",
    "press", "release", "SHIFT_MAP",
    "read_sheet_meta", "write_sheet_meta",              # ← new helpers
]

# ───────── constants ────────────────────────────────────────────────
def _config_path() -> Path:
    # In PyInstaller one-file builds, `__file__` points at the temporary extract
    # directory. Use the executable directory instead so settings persist.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).with_name("vp_autoplayer.json")
    return Path(__file__).with_name("vp_autoplayer.json")

DATA_FILE = _config_path()

SHIFT_MAP: Dict[str, str] = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6",
    "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=",
    "{": "[", "}": "]", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/"
}
SHIFT_REV: Dict[str, str] = {v: k for k, v in SHIFT_MAP.items()}

NEIGHBOURS: Dict[str, List[str]] = {
    "a":["s","q","w","z"], "s":["a","d","w","e","x","z"],
    "d":["s","f","e","r","c","x"], "f":["d","g","r","t","v","c"],
    "g":["f","h","t","y","b","v"], "h":["g","j","y","u","n","b"],
    "j":["h","k","u","i","m","n"], "k":["j","l","i","o",",","m"],
    "l":["k","o","p","."],
    "q":["w","a"], "w":["q","e","s","a"], "e":["w","r","d","s"],
    "r":["e","t","f","d"], "t":["r","y","g","f"], "y":["t","u","h","g"],
    "u":["y","i","j","h"], "i":["u","o","k","j"], "o":["i","p","l","k"],
    "p":["o","l"]
}

KB = Controller()

# ───────── per-sheet #META helpers (NEW) ────────────────────────────
def read_sheet_meta(path: Path) -> dict:
    """
    Return dict from first non-blank line that starts with “#META”.
    May include 'bpm', 'subdiv', and now optional 'note'.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                if line.lstrip().startswith("#META"):
                    return json.loads(line.split(None, 1)[1])
                break
    except Exception:
        pass
    return {}

def write_sheet_meta(
        path: Path,
        bpm: int | None = None,
        subdiv: float | None = None,
        note: str | None = None
) -> None:
    """
    Update the #META line at the top of *path*.
    Any argument left as None keeps its previous value.
    """
    try:
        meta = read_sheet_meta(path)           # start with what’s already there
        if bpm    is not None: meta["bpm"]    = bpm
        if subdiv is not None: meta["subdiv"] = subdiv
        if note   is not None: meta["note"]   = note

        header = f'#META {json.dumps(meta, ensure_ascii=False)}'
        lines  = path.read_text("utf-8").splitlines()
        if lines and lines[0].lstrip().startswith("#META"):
            lines[0] = header
        else:
            lines.insert(0, header)

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        print("⚠ meta write:", exc, file=sys.stderr)
# ───────── persistent config ────────────────────────────────────────
@dataclass
class Config:
    folder: Path = Path.cwd()
    sheet:  Path | None = None
    bpm: int = 120
    subdiv: float = 4.0                     # may be fractional
    human: float = .30
    hold:  float = .80
    toggle: str  = "f4"
    auto_pause: bool = True
    dark: bool = False
    target_title: Optional[str] = field(default=None, repr=False)

    def sec_per_tok(self) -> float:
        return 60 / (self.bpm * self.subdiv)

CFG = Config()

# ------------ load / save -------------------------------------------
if DATA_FILE.exists():
    try:
        raw = json.loads(DATA_FILE.read_text("utf-8"))
        allowed = set(Config.__dataclass_fields__.keys())  # type: ignore[attr-defined]
        for k, v in raw.items():
            if k not in allowed:
                continue

            if k in ("folder", "sheet"):
                if v is None:
                    setattr(CFG, k, None)
                elif isinstance(v, str) and v.strip():
                    setattr(CFG, k, Path(v))
                continue

            if k == "bpm":
                try:
                    setattr(CFG, k, int(v))
                except Exception:
                    pass
                continue

            if k in ("subdiv", "human", "hold"):
                try:
                    setattr(CFG, k, float(v))
                except Exception:
                    pass
                continue

            if k in ("auto_pause", "dark"):
                setattr(CFG, k, bool(v))
                continue

            if k == "toggle":
                if isinstance(v, str) and v.strip():
                    setattr(CFG, k, v.strip())
                continue

            if k == "target_title":
                setattr(CFG, k, (v.strip() if isinstance(v, str) and v.strip() else None))

        if not isinstance(CFG.folder, Path) or not CFG.folder.exists():
            CFG.folder = Path.cwd()
        if isinstance(CFG.sheet, Path) and not CFG.sheet.exists():
            CFG.sheet = None
    except Exception as exc:
        print("⚠ settings load:", exc, file=sys.stderr)

def save_cfg() -> None:
    DATA_FILE.write_text(
        json.dumps(
            {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(CFG).items()},
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

# ───────── keyboard helpers ─────────────────────────────────────────
def press(ch: str):
    if ch in SHIFT_MAP:
        KB.press(Key.shift); KB.press(SHIFT_MAP[ch])
    elif ch.isupper():
        KB.press(Key.shift); KB.press(ch.lower())
    else:
        KB.press(ch)

def release(ch: str):
    if ch in SHIFT_MAP:
        KB.release(SHIFT_MAP[ch]); KB.release(Key.shift)
    elif ch.isupper():
        KB.release(ch.lower()); KB.release(Key.shift)
    else:
        KB.release(ch)

# ───────── window list helper ───────────────────────────────────────
def windows() -> list[Tuple[int, str]]:
    out: list[Tuple[int, str]] = []
    win32gui.EnumWindows(
        lambda h, _:
            out.append((h, win32gui.GetWindowText(h)))
            if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h)
            else None, None)
    return sorted(out, key=lambda t: t[1].lower())

# ───────── Player thread ────────────────────────────────────────────
class Player(threading.Thread):
    def __init__(self, sheet: Path, queue: Queue[Tuple[str, float]]):
        super().__init__(daemon=True)
        self.sheet, self.q = sheet, queue
        self.resume_evt = threading.Event(); self.resume_evt.set()
        self.stop_evt   = threading.Event()
        self._last_token_time = time.time()
        self._last_shift_needed = False        # for sticky-Shift

    def toggle(self): self.resume_evt.clear() if self.resume_evt.is_set() else self.resume_evt.set()
    def stop(self):   self.stop_evt.set()

    # strength mapping ------------------------------------------------
    @staticmethod
    def _human_strength() -> float:
        h = CFG.human * 100
        if h == 0:  return 0.0
        if h <= 50: return 0.30 * (h / 50)
        if h <= 75: return 0.30 + 0.30 * (h - 50) / 25
        return 0.60 + 0.40 * (h - 75) / 25

    # parameters (density-aware) -------------------------------------
    def _params(self, dens: float):
        s = self._human_strength()
        if s == 0:      # robot mode – everything zeroed
            return 0, 0, 0, 0, 0, 0, 0

        σ          = 0.12 * s**2
        span       = 0.08 * s**2
        drift      = 0.20 * s**2
        hold_jit   = 1.20 * s**2

        hi         = max(0.0, (CFG.human*100 - 75)/25)
        p_drop     = 0.40 * hi**2
        p_slip     = 0.10 * hi**3
        p_shift    = 0.25 * hi**2

        factor = 0.3 + 0.7 * dens
        return σ, span, drift, hold_jit, p_drop*factor, p_slip*factor, p_shift*factor

    # tokeniser (now skips lines starting with '#') -------------------
    @staticmethod
    def _tokenise(txt: str):
        for line in txt.splitlines():
            if line.lstrip().startswith("#"):   # skip #META / comments
                continue
            i = 0
            while i < len(line):
                if line[i] == "[":
                    chord = []; i += 1
                    while i < len(line) and line[i] != "]":
                        if not line[i].isspace() and (line[i].isalnum() or line[i] in SHIFT_MAP):
                            chord.append(line[i])
                        i += 1
                    if chord: yield chord
                elif not line[i].isspace():
                    yield line[i]
                i += 1

    @staticmethod
    def _needs_shift(tok) -> bool:
        if isinstance(tok, list):
            return any(Player._needs_shift(t) for t in tok)
        return tok in SHIFT_MAP or tok.isupper()

    @staticmethod
    def _neighbour(ch: str) -> str:
        return random.choice(NEIGHBOURS.get(ch.lower(), list(NEIGHBOURS.keys())))

    # run -------------------------------------------------------------
    def run(self):   # noqa: C901
        try:
            raw = self.sheet.read_text("utf-8")
        except Exception as exc:
            self.q.put(("error", 0, str(exc))); return

        toks = list(self._tokenise(raw)); total = len(toks)
        self.q.put(("total", total))
        t0 = time.time()

        for idx, tok in enumerate(toks, 1):
            if self.stop_evt.is_set(): break

            now = time.time()
            ios = now - self._last_token_time
            self._last_token_time = now
            density = max(0.0, min(1.0, (0.15 - ios) / 0.10))

            σ, span, drift, h_jit, p_drop, p_slip, p_shift = self._params(density)
            robot = (σ == 0)

            # sticky-Shift slip
            if self._last_shift_needed and isinstance(tok, str) and tok in SHIFT_REV \
               and random.random() < p_shift:
                tok = SHIFT_REV[tok]

            # ordinary drop / slip
            slipped = False
            if p_drop and random.random() < p_drop:
                self.q.put(("progress", idx)); self._last_shift_needed = False; continue
            if p_slip and isinstance(tok, str) and random.random() < p_slip:
                tok = self._neighbour(tok); slipped = True

            sec = CFG.sec_per_tok() * (1 + drift *
                  math.sin(2*math.pi*0.25*(time.time() - t0)))
            onset_off = random.gauss(0, σ)

            # focus / pause gate
            while (not self.resume_evt.is_set()) or (
                  CFG.auto_pause and CFG.target_title and
                  win32gui.GetWindowText(win32gui.GetForegroundWindow()) != CFG.target_title):
                if self.stop_evt.is_set(): break
                time.sleep(0.05)
            if self.stop_evt.is_set(): break

            if onset_off > 0: time.sleep(onset_off)

            # play token
            if tok == "|":
                time.sleep(sec)

            elif isinstance(tok, list):
                if robot:
                    for n in tok: press(n)
                    hold_len = max(0.06, CFG.hold * sec)
                    time.sleep(hold_len)
                    for n in reversed(tok): release(n)
                    time.sleep(max(0.0, sec - hold_len))
                else:
                    base = time.perf_counter()
                    for i, n in enumerate(tok):
                        press(n)
                        if i < len(tok)-1:
                            time.sleep(span * random.random())
                    hold_var = 1 + random.uniform(-h_jit, h_jit)
                    main_hold = max(0.06, sec*CFG.hold*hold_var)
                    time.sleep(max(0.0, main_hold - (time.perf_counter()-base)))
                    for n in reversed(tok): release(n)
                    time.sleep(max(0.0, sec - (time.perf_counter()-base)))

            else:
                press(tok)
                hold_len = max(
                    0.06,
                    CFG.hold * sec * (1 + (random.uniform(-h_jit, h_jit) if not robot else 0))
                )
                time.sleep(hold_len + max(0.0, onset_off))
                release(tok)
                time.sleep(max(0.0, sec - hold_len - max(0.0, onset_off)))

            if onset_off < 0: time.sleep(-onset_off)

            self.q.put(("progress", idx))
            self._last_shift_needed = self._needs_shift(tok)

            if slipped and random.random() < 0.20:
                time.sleep(random.uniform(0.3, 0.6))

        self.q.put(("done", 1))
