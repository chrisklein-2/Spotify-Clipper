"""controllers/status.py - StatusMixin: action enabling, status bar, tick loop."""


import numpy as np
from PySide6.QtWidgets import QMessageBox

from audio_backends import glitch_count
from editor import format_time
from processing import estimate_mb

SEP = "   \u2502   "


class StatusMixin:

    def update_actions(self):
        recording = self.recorder is not None
        has = self.timeline.duration() > 0
        sel = self.wave.selection() is not None
        has_marks = bool(self.bookmarks)

        self.act_delete.setEnabled(has and sel)
        self.act_restore.setEnabled(has and sel)
        self.act_zoomsel.setEnabled(has and sel)
        self.act_undo.setEnabled(self.timeline.can_undo())
        self.act_redo.setEnabled(self.timeline.can_redo())
        self.act_bookmark.setEnabled(has or recording)
        self.mark_btn.setEnabled(recording)
        self.live_zoom_btn.setEnabled(recording)
        self.act_rm_bookmark.setEnabled(has and has_marks)
        self.act_clear_bookmarks.setEnabled(has_marks)
        self.act_prev_bookmark.setEnabled(has and has_marks)
        self.act_next_bookmark.setEnabled(has and has_marks)

        for action in (
            self.act_mark_in, self.act_mark_out, self.act_trim, self.act_reset,
            self.act_fit, self.act_selall, self.act_play, self.act_from_start,
            self.act_export, self.act_finalize, self.act_piece_fades,
        ):
            action.setEnabled(has)
        for widget in (
            self.raw_btn, self.goto_edit, self.zoom_in_btn,
            self.zoom_out_btn, self.fit_btn,
        ):
            widget.setEnabled(has)

        night = self.night_box.isChecked()
        for widget in (self.threshold, self.ceiling, self.test_btn):
            widget.setEnabled(night)
        self.cover_clear.setEnabled(self.cover_path is not None)

        label = "Pause" if self.player.is_playing() else "Play / Pause"
        self.act_play.setText(label)
        self.play_btn.setText(label)
        self.update_status()

    def update_status(self):
        if self.recorder is not None:
            return
        clip = self.timeline.kept_duration()
        kbps = self.bitrate.currentData()
        ram = self.timeline.store.pyramid_bytes() if self.timeline.store else 0
        parts = [
            f"clip {format_time(clip)} of {format_time(self.timeline.duration())}",
            f"{len(self.timeline.keeps)} piece(s)",
            f"~{estimate_mb(clip, kbps):.1f} MB @ {kbps} kbps",
            f"RAM {ram / 1e6:.0f} MB",
            f"at {format_time(self.wave.playhead)}",
        ]
        if self.unsaved and self.timeline.duration() > 0:
            parts.append("\u25cf UNSAVED")
        self.statusBar().showMessage(SEP.join(parts))

    # ---- tick -----------------------------------------------------------

    def tick(self):
        if self.recorder is not None:
            self._tick_recording()
        else:
            self._tick_playback()

    # Bookmark positions (0..1 across the live window) still inside the
    # rolling buffer that is being drawn.
    def _live_marks(self, mono, elapsed):
        span = len(mono) / float(self.recorder.samplerate)
        if span <= 0:
            return []
        return [1.0 - (elapsed - t) / span
                for t in self.bookmarks if 0.0 <= elapsed - t <= span]

    def _tick_recording(self):
        error = self.recorder.error()
        if error:
            QMessageBox.critical(self, "Recording stopped", error)
            self.stop_record()
            return
        elapsed = self.recorder.elapsed()
        mono = self.recorder.latest_mono(8.0)

        env, marks = None, []
        if self.live_zoom_btn.isChecked():
            mins, maxs = self.recorder.envelope()
            if len(mins) > 1:
                env = (mins, maxs)
                span = len(mins) * self.recorder.env_bucket / float(
                    self.recorder.samplerate)
                marks = [min(1.0, t / span) for t in self.bookmarks]
        if env is None:
            marks = self._live_marks(mono, elapsed)
        window = "whole recording" if env is not None else "last 8 s"

        # ---- paused state ----
        if self.recorder.paused:
            self.wave.set_live(
                mono,
                f"PAUSED   {format_time(elapsed)}   (click Resume to continue)",
                marks, env,
            )
            bk = f"   {len(self.bookmarks)} bookmark(s)" if self.bookmarks else ""
            self.statusBar().showMessage(f"Paused at {format_time(elapsed)}{bk}")
            return

        # ---- actively recording ----
        peak = self.recorder.peak()
        self.wave.set_live(
            mono,
            f"RECORDING   {format_time(elapsed)}   ({window})",
            marks, env,
        )
        notes = []
        if peak < 1e-4 and elapsed > 3:
            notes.append("silence \u2014 wrong source?")
        dropped = glitch_count()
        if dropped:
            notes.append(f"{dropped} dropout(s)")
        if self.bookmarks:
            notes.append(f"{len(self.bookmarks)} bookmark(s)")
        tail = (SEP + SEP.join(notes)) if notes else ""
        db = 20.0 * np.log10(max(peak, 1e-9))
        self.statusBar().showMessage(
            f"Recording {format_time(elapsed)} to disk{SEP}"
            f"input peak {db:5.1f} dBFS{tail}"
        )
        
    def _tick_playback(self):
        player = self.player
        if player.is_playing():
            streamer = player.streamer
            if (streamer is not None and not self.wave.is_scrubbing()
                    and self._seek_target is None):
                if player.mode == "raw":
                    frame = getattr(streamer, "raw_offset", 0) + player.out_frame()
                else:
                    frame = streamer.source_frame(player.out_frame())
                self.wave.set_playhead(frame / float(self.timeline.samplerate()))
        elif self._was_playing:
            self.update_actions()
        self._was_playing = player.is_playing()