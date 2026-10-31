"""
core/recording.py - RecordingMixin: source selection, record/pause/resume/stop.

Mixed into MainWindow.
"""

from PySide6.QtWidgets import QDialog, QMessageBox

from audio_backends import (
    Recorder, default_device_index, glitch_count, list_capture_devices,
    loopback_help, native_samplerate,
)
from .dialogs import SourceDialog


class RecordingMixin:

    # ---- source management (unchanged) -----------------------------------

    def resolve_source(self):
        devices = list_capture_devices()
        chosen = None
        for device in devices:
            if device.label == self.source_label:
                chosen = device
                break
        if chosen is None:
            index = default_device_index(devices)
            chosen = devices[index] if 0 <= index < len(devices) else None
        self.apply_source(chosen, remember=False)

    def apply_source(self, device, remember=True):
        self.device = device
        if device is None:
            self.source_btn.setText("Source: none \u2014 click to choose")
            self.source_btn.setToolTip(loopback_help())
            self.statusBar().showMessage("No capture source.  " + loopback_help())
            return
        label = device.label
        self.source_btn.setText(label if len(label) <= 32 else label[:31] + "\u2026")
        self.source_btn.setToolTip(f"{label}\n\nClick to change.   [Ctrl+I]")
        if remember:
            self.source_label = label
            self.settings.setValue("source_label", label)
        rate = native_samplerate(device)
        if rate is not None:
            for i in range(self.sr_box.count()):
                if self.sr_box.itemData(i) == rate:
                    self.sr_box.setCurrentIndex(i)
                    break
        self.check_rate_match()

    def choose_source(self):
        if self.recorder is not None:
            QMessageBox.information(self, "Recording", "Stop recording first.")
            return
        dialog = SourceDialog(self.source_label, self)
        if dialog.exec() == QDialog.Accepted and dialog.chosen():
            self.apply_source(dialog.chosen())

    def check_rate_match(self, *_):
        rate = native_samplerate(self.device)
        want = self.sr_box.currentData()
        if rate and want and rate != want:
            self.statusBar().showMessage(
                f"Note: the device runs at {rate} Hz but you chose {want} Hz. "
                f"Windows will resample, which can add grit.",
                12000,
            )

    # ---- recording lifecycle ---------------------------------------------

    def toggle_record(self):
        """Record / Pause / Resume cycle via the main button."""
        if self.recorder is None:
            self.start_record()
        elif self.recorder.paused:
            self.resume_record()
        else:
            self.pause_record()

    def start_record(self):
        """Open the device and begin capturing to disk."""
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

    def pause_record(self):
        """Pause the current recording — device is released."""
        if self.recorder is None or self.recorder.paused:
            return
        self.recorder.pause()
        self.rec_btn.setText("Resume")
        self.rec_btn.setChecked(False)
        self.statusBar().showMessage("Recording paused — click Resume to continue", 8000)

    def resume_record(self):
        """Continue the paused recording to the same file."""
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
        self.rec_btn.setText("Record")
        self.rec_btn.setChecked(False)
        self.stop_rec_btn.setEnabled(False)
        for widget in (self.sr_box, self.mono_box, self.source_btn):
            widget.setEnabled(True)
        self.wave.clear_live()
        if store is None or store.frames() == 0:
            self.statusBar().showMessage("Nothing captured — wrong source?", 8000)
            return
        dropped = glitch_count()
        if dropped:
            QMessageBox.warning(
                self,
                "Dropouts during recording",
                f"The audio layer reported {dropped} dropout(s). Those are real lost "
                f"samples and will sound like clicks.\n\nUsual causes: heavy CPU load, "
                f"or a sample rate mismatch between SpotClip and the Windows device.",
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

    def start_new_recording(self):
        """File menu action: stop any current recording, confirm, start fresh."""
        if self.recorder is not None:
            self.stop_record()
        self.start_record()