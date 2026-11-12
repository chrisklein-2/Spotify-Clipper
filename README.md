# SpotClip

Record, edit and export audio clips. Captures system audio (loopback) or any
input device straight to disk, edits non-destructively with unlimited undo,
and exports with fades, loudness control and embedded cover art. A 2 hour
recording costs ~15 MB of RAM because samples live on disk behind a memmap
and everything streams block by block.

Personal use only.

## Requirements

- Python 3.10+
- `PySide6`, `numpy`, `sounddevice`, `soundcard`, `soundfile`
- `qrcode` (optional — for the Send to phone QR code)
- **ffmpeg / ffprobe on PATH** (loading mp3/m4a/mp4 and exporting anything
  other than .wav fails without them)

Install into a virtual environment:

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

## Run

    python main.py

## Project layout

```
SpotClip/
├── main.py                  entry point
├── app.py                   MainWindow: state + wiring only
├── config.py                paths and constants (exports/, finals/, session/ live beside main.py)
├── utils.py                 reveal_folder, mbytes, clean_orphan_sessions
├── theme.py                 dark theme and colours
├── processing.py            loudness guard + ffmpeg decode / encode
├── store.py                 disk-backed audio + peak pyramid
├── share.py                 send-a-folder-to-phone HTTP server + dialogs
├── requirements.txt
├── README.md
│
├── editor/                  the edit model (no GUI)
│   ├── __init__.py
│   ├── timeline.py          Keep, Piece, Timeline (cuts, undo, per-piece fades)
│   ├── streamer.py          ClipStreamer (renders the clip block by block)
│   ├── fades.py             all fade gain math
│   └── timefmt.py           format_time, parse_time
│
├── audio_backends/          capture and playback
│   ├── __init__.py
│   ├── devices.py           device discovery
│   ├── recorder.py          capture thread -> disk, live overview
│   ├── glitches.py          dropout counter
│   └── player.py            StreamPlayer (queue-buffered output)
│
├── waveform/                waveform widget
│   ├── __init__.py
│   ├── view.py              state, navigation, input
│   └── painter.py           all drawing
│
├── ui/                      widget construction only
│   ├── __init__.py
│   ├── actions.py           QActions and shortcuts
│   ├── menus.py             menu bar
│   ├── panels.py            top row, waveform + pieces panel, nav row, edit group
│   ├── output_panel.py      fades / loudness / export controls
│   ├── widgets.py           sep(), abtn()
│   ├── dialogs.py           Busy, Source, Join, Help, PieceFade, Settings dialogs, confirm()
│   └── help_text.py         HELP_HTML
│
├── controllers/             MainWindow behaviour, one mixin per concern
│   ├── __init__.py
│   ├── source.py            capture source selection
│   ├── recording.py         record / pause / resume / stop / abort
│   ├── fileio.py            load / append / join, new recording, session files
│   ├── export.py            output chain, export, finalize
│   ├── folders.py           export / finals folders, send to phone
│   ├── cover.py             cover art
│   ├── editing.py           delete / restore / undo / trim / piece fades
│   ├── transport.py         play / pause / seek / raw / test tone
│   ├── navigation.py        scrollbar, go-to, pieces list, record/edit mode
│   ├── bookmarks.py         bookmarks (also while recording)
│   ├── settings.py          persisted settings + settings window
│   ├── status.py            action enabling, status bar, tick loop
│   └── tasks.py             TaskThread for background work
│
├── assets/                  thumbnail, test audio
├── exports/                 exported clips (configurable in-app)
├── finals/                  finished clips (configurable in-app)
└── session/                 scratch recordings (auto-cleaned)
```

## What each script does

### main.py
- Entry point: Qt app, dark theme, ffmpeg check, show the window.

### app.py
- `MainWindow`: owns state, builds the window from the `ui/` mixins, combines
  the `controllers/` mixins, runs the timer, confirms before discarding work.

### config.py / utils.py
- Paths (`exports/`, `finals/`, `session/`), block sizes, file filters.
- `reveal_folder`, `mbytes`, `clean_orphan_sessions`.

### editor/
- `timeline.py` — `Keep` (with optional per-piece fades), `Piece`, `Timeline`:
  delete / restore / trim / reset, undo / redo, `plan()`, `block_at()`.
- `streamer.py` — `ClipStreamer`: renders the edited clip block by block with
  fades, end fade and the loudness guard; source / output frame mapping.
- `fades.py` — fade gain curves.
- `timefmt.py` — `format_time`, `parse_time`.

### processing.py
- `LoudnessGuard` — streaming compressor + ceiling with carried gain state.
- `probe_audio`, `decode_to_raw`, `append_decoded` — ffmpeg decode to raw int16.
- `prepare_cover`, `export_stream` — cover art and streamed export (.wav /
  .m4a / .mp3).
- Small utilities: `db_to_lin`, `estimate_mb`, `unique_path`, `missing_tools`.

### store.py
- `AudioStore` — memmap over a raw int16 file, peak pyramid build / query,
  `loud_bounds` for auto-trim, close / delete lifecycle.

### share.py
- `FolderServer` — throwaway HTTP server for a folder behind a random token
  URL, with Range support.
- `qr_pixmap`, `ShareDialog`, `ShareFolderDialog` — QR code and folder picker.

### theme.py
- Colour constants, the Qt stylesheet, `apply_dark_theme()`.

### audio_backends/
- `devices.py` — `CaptureDevice`, enumeration, default loopback pick, native
  sample rate lookup, loopback help text.
- `recorder.py` — `Recorder` (capture thread → queue → writer thread → disk),
  live ring buffer and whole-recording overview.
- `glitches.py` — dropout counter.
- `player.py` — `StreamPlayer` (queue-buffered output).

### waveform/
- `view.py` — `WaveformView`: zoom / pan, selection and marks, playhead,
  bookmarks, mouse / keyboard / wheel input, peak cache.
- `painter.py` — ruler, waveform, deleted zones, fade wedges, selection and
  flags, bookmarks, playhead, live recording view.

### ui/
- Widget construction only: actions, menus, panels, output panel, dialogs,
  help text. No application logic.

### controllers/
- One mixin per concern, all combined into `MainWindow`: recording, source
  selection, file I/O, export, folders, cover art, editing, transport,
  navigation (including record / edit screen switching), bookmarks, settings,
  status and tick loop.

## Workflow

1. **Record** (pick a LOOPBACK source) and press **Stop rec**, or
   **File → Load** a file. The app switches to the edit screen.
2. Edit: drag or double-click to select, `[` `]` to mark in / out, `Del` to
   cut, `Ctrl+Z` to undo, `Ctrl+F` for a custom fade on one piece.
3. **Export (Ctrl+E)** writes to `exports/`; **Finalize (Ctrl+Shift+F)**
   writes to `finals/`. The app returns to the record screen.
4. **Send to phone (Ctrl+P)** serves a folder over Wi-Fi via QR code.
5. **File → New recording (Ctrl+N)** scraps the current clip and returns to the
   record screen. **Settings → All settings** shows every option in one window.