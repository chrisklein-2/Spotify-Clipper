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

## Run

    python main.py

## Project layout

    main.py             entry point
    app.py              main window
    editor.py           edit model + clip streamer
    processing.py       output chain + ffmpeg I/O
    share.py            send-to-phone server
    store.py            disk-backed audio + peak pyramid
    theme.py            dark theme
    audio_backends/     device discovery + recorder
    core/               pieces of the main window
    waveform/           waveform widget
    assets/             thumbnail, test audio
    exports/            exported clips (configurable in-app)
    finals/             finished clips (configurable in-app)
    session/            scratch recordings (auto-cleaned)

## What each script does

### main.py
- Entry point: Qt app, dark theme, ffmpeg check, show the window.

### app.py
- `MainWindow`: builds the UI (menus, capture row, waveform, navigation,
  edit/output groups), routes playback, runs the tick loop and status bar,
  confirms before discarding unsaved work.

### editor.py
- `format_time()`.
- `Keep` / `Piece` dataclasses.
- `Timeline` — keep-ranges edit model: delete/restore/trim/reset, undo/redo,
  `plan()` to turn keeps into pieces.
- `ClipStreamer` — renders the edited clip block by block: per-piece fades,
  end fade, loudness guard, source/output frame mapping.

### processing.py
- Utilities: `db_to_lin`, `estimate_mb`, `missing_tools`, `unique_path`, etc.
- `LoudnessGuard` — streaming compressor + ceiling with carried gain state.
- `probe_audio`, `decode_to_raw`, `append_decoded` — ffmpeg decode to raw int16.
- `prepare_cover` — shrink artwork for embedding.
- `export_stream` — stream the clip into soundfile (.wav) or ffmpeg (.m4a/.mp3).

### share.py
- `FileServer` — throwaway HTTP server for one file at a random token URL,
  with Range support.
- `qr_pixmap` — QR rendering.
- `ShareDialog` — shows the QR code; closing it stops the server.

### store.py
- `AudioStore` — memmap over a raw int16 file, peak pyramid build/query,
  `loud_bounds` for auto-trim, close/delete lifecycle.

### theme.py
- Colour constants, the Qt stylesheet, `apply_dark_theme()`.

### audio_backends/
- `devices.py` — `CaptureDevice`, device enumeration, default loopback pick,
  native sample rate lookup, loopback help text.
- `recorder.py` — `Recorder` (capture thread → queue → writer thread → disk),
  dropout counting, live preview ring buffer.

### core/
- `constants.py` — paths, limits, filter strings, help text.
- `helpers.py` — `parse_time`, small UI helpers, session cleanup.
- `dialogs.py` — `BusyDialog`, `SourceDialog`, `JoinDialog`, `HelpDialog`.
- `playback.py` — `StreamPlayer` (queue-buffered output), `TaskThread`.
- `recording.py` — source selection and record start/stop (MainWindow mixin).
- `fileio.py` — session management, load/append/join (MainWindow mixin).
- `export_.py` — export, finals folder, cover art, loudness settings
  (MainWindow mixin).
- `editing.py` — delete/restore/trim/undo/redo (MainWindow mixin).

### waveform/
- `view.py` — `WaveformView`: zoom/pan state, selection and markers,
  playhead, mouse/keyboard/wheel input, peak cache.
- `painter.py` — all drawing: ruler, waveform, deleted zones, fade wedges,
  selection, marker flags, playhead, live recording view.

## Workflow

1. **Record** (pick a LOOPBACK source) or **File → Load** a file.
2. Edit: drag or use `[` `]` markers, `Del` to cut, `Ctrl+Z` to undo.
3. **Export (Ctrl+E)** writes to `exports/`.
4. When a clip is finished: **File → Move last export to finals**, or
   **Export to finals (Ctrl+Shift+F)** to write there directly.
5. **Send to phone (Ctrl+P)** serves the clip over Wi-Fi via QR code.