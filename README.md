# VP Autoplayer (Windows)

VP Autoplayer is a Windows desktop app that reads Virtual Piano-style song sheets (`.txt`) and "types" the notes into a target window (commonly Roblox / Virtual Piano). It includes timing controls and an optional humanizer to make playback less robotic.

This project is **Windows-only** (it uses Windows APIs for window detection and input).

## Features

- Play local `.txt` song sheets
- Change BPM / subdivision / humanize / hold while playing
- Humanizer (timing jitter + drift + small imperfections)
- Target window selection + optional auto-pause when unfocused
- Per-sheet `#META` header for sheet-specific settings
- Light/Dark theme
- Global hotkey to start/stop (default: `F4`)
- Saves your settings automatically

## Run From Source

```powershell
cd C:\path\to\VP-Autoplayer
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python gui.py
```

## Build a Standalone EXE (PyInstaller)

```powershell
cd C:\path\to\VP-Autoplayer
.\.venv\Scripts\python -m pip install -r requirements-build.txt
.\.venv\Scripts\pyinstaller gui.spec
```

Output: `dist\gui.exe`

## How to Use

1. Launch the app (`gui.py` or `dist\gui.exe`).
2. Click **Browse** and select a folder containing `.txt` sheets.
3. Pick a sheet from the dropdown.
4. Select the **Target Window** (the window that should receive key presses).
5. Press **Play** or hit the toggle hotkey (`F4` by default).

## Sheet Format

Sheets are plain text. You can paste sheets from Virtual Piano sites into a `.txt` file.

### Optional `#META` header

The first non-empty line may contain a JSON header:

```txt
#META {"bpm": 100, "subdiv": 4, "note": "Transposed -1"}
[A F G] r r u o | s d f | o f f f d x
```

- `bpm`: beats per minute
- `subdiv`: tokens per beat (can be fractional)
- `note`: freeform note shown in the UI

## Timing Tip

If a song plays too fast/slow, adjust **Subdivision** until the overall timing matches what you expect. Integers like `2`, `4`, `8` are a good start; fractional values also work.

## Config

- Global settings: `vp_autoplayer.json`
  - Packaged EXE: next to the EXE
  - Running from source: next to `autoplayer_core.py`
- Example config: `vp_autoplayer.example.json`
- Sheet-specific settings: stored in the sheet's `#META` header

## Requirements

- Windows 10/11

For running from source:

- Python 3.x
- Packages in `requirements.txt`

## Troubleshooting

- Keys go to the wrong place: re-select the **Target Window** and focus it.
- Auto-pause keeps stopping playback: disable auto-pause or update the target window.
- Nothing types: some apps/games block synthetic input; try running as Administrator (only if you trust the code).


## Disclaimer

Not affiliated with VirtualPiano.net or Roblox.
