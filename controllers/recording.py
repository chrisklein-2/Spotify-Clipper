"""controllers/recording.py - RecordingMixin: record / pause / resume / stop."""
from PySide6.QtWidgets import QMessageBox

from audio_backends import Recorder, glitch_count, loopback_help


class RecordingMixin:

    def toggle_record(self):
        """Record / Pause / Resume cycle via the main button."""
        if self.recorder is None:
            self.start_record()
        elif self.recorder.paused:
            self.resume_record()
        else:
            self.pause_record()

    def start_record(self):
        if not self.confirm_discard():
            self.rec_btn.setChecked(False)
            return
        if self.device is None:
            self.rec_btn.setChecked(False)
            self.choose_source()
            return
        self.stop_playback()
        self.drop_session()
        self.bookmarks.clear()
        self.wave.set_bookmarks(self.bookmarks)
        self.session_path = self.new_session_path()
        channels = 1 if self.mono_box.isChecked() else 2
        try:
            self.recorder = Recorder(
                self.device, self.session_path, self.sr_box.currentData(), channels
            )
            self.recorder.start()
        except Exception as exc:
            self.recorder = None
            self.rec_btn.setChecked(False)
            QMessageBox.critical(
                self, "Could not start recording", f"{exc}\n\n{loopback_help()}"
            )
            return
        self.rec_btn.setText("Pause")
        self.rec_btn.setChecked(True)
        self.stop_rec_btn.setEnabled(True)
        for widget in (self.sr_box, self.mono_box, self.source_btn):
            widget.setEnabled(False)
        self.update_actions()                # enables Mark / Ctrl+B

    def pause_record(self):
        if self.recorder is None or self.recorder.paused:
            return
        self.recorder.pause()
        self.rec_btn.setText("Resume")
        self.rec_btn.setChecked(False)
        self.statusBar().showMessage(
            "Recording paused \u2014 click Resume to continue", 8000)

    def resume_record(self):
        if self.recorder is None or not self.recorder.paused:
            return
        try:
            self.recorder.resume()
        except Exception as exc:
            QMessageBox.critical(self, "Could not resume", str(exc))
            return
        self.rec_btn.setText("Pause")
        self.rec_btn.setChecked(True)
        self.statusBar().showMessage("Recording resumed", 3000)

    def _reset_record_ui(self):
        self.rec_btn.setText("Record")
        self.rec_btn.setChecked(False)
        self.stop_rec_btn.setEnabled(False)
        for widget in (self.sr_box, self.mono_box, self.source_btn):
            widget.setEnabled(True)
        self.wave.clear_live()
        self.update_actions()

    def stop_record(self):
        """Finalise the recording and show it for editing."""
        if self.recorder is None:
            return
        try:
            store = self.recorder.stop()
        except Exception as exc:
            QMessageBox.critical(self, "Recording failed", str(exc))
            store = None
        self.recorder = None
        self._reset_record_ui()
        if store is None or store.frames() == 0:
            self.statusBar().showMessage("Nothing captured \u2014 wrong source?", 8000)
            return
        dropped = glitch_count()
        if dropped:
            QMessageBox.warning(
                self, "Dropouts during recording",
                f"The audio layer reported {dropped} dropout(s). Those are real "
                f"lost samples and will sound like clicks.\n\nUsual causes: heavy "
                f"CPU load, or a sample rate mismatch between SpotClip and the "
                f"Windows device.",
            )

        def work(report):
            store.build_pyramid(report)
            return store

        self.run_task(
            "Scanning audio",
            "Building the peak overview (one pass, then editing is instant)...",
            work,
            lambda ready: self._show_store(ready),
        )

    def abort_record(self):
        """Stop capturing and throw the recording away (no dialog)."""
        rec, self.recorder = self.recorder, None
        if rec is not None:
            try:
                rec.stop().close()           # release the file so it can be deleted
            except Exception:
                pass
        self._reset_record_ui()
        self.drop_session()
        self.bookmarks.clear()
        self.wave.set_bookmarks(self.bookmarks)