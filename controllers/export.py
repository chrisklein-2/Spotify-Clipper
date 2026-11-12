
"""core/export.py - ExportMixin: build the output chain and write clips."""

import os

from PySide6.QtWidgets import QFileDialog, QMessageBox

from editor import ClipStreamer
from processing import LoudnessGuard, export_stream, unique_path
from utils import mbytes                                          
      

class ExportMixin:

    def make_guard(self):
        return LoudnessGuard(
            self.timeline.samplerate(),
            enabled=self.night_box.isChecked(),
            threshold_db=self.threshold.value(),
            ceiling_db=self.ceiling.value(),
        )

    def make_streamer(self):
        if not self.timeline.store or self.timeline.frames() == 0:
            return None
        pieces = self.timeline.plan(self.cut_fade.value())
        if not pieces:
            return None
        end_fade = int(self.fade_out.value() * self.timeline.samplerate())
        return ClipStreamer(self.timeline.store, pieces, self.make_guard(), end_fade)

    def do_export(self):
        name = self.clip_name.text().strip() or "clip"
        path = unique_path(os.path.join(self.ensure_export_dir(), f"{name}.m4a"))
        self._write_clip(path)

    def do_export_as(self):
        name = self.clip_name.text().strip() or "clip"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export clip as",
            os.path.join(self.ensure_export_dir(), f"{name}.m4a"),
            "iPhone-friendly AAC (*.m4a);;MP3 (*.mp3);;WAV lossless (*.wav)",
        )
        if path:
            self._write_clip(path)

    # Stream the clip to a file, reporting progress.
    def _write_clip(self, path):
        streamer = self.make_streamer()
        if streamer is None:
            QMessageBox.information(self, "Nothing to export",
                                    "Keep at least a little audio first.")
            return
        rate = self.timeline.samplerate()
        chans = self.timeline.channels()
        kbps = self.bitrate.currentData()
        cover = self.cover_path
        title = os.path.splitext(os.path.basename(path))[0]
        def work(report):
            return export_stream(path, streamer, rate, chans, kbps, title,
                                 cover, report)
        def done(written):
            self.last_export = written
            self.unsaved = False
            self.statusBar().showMessage(
                f"Saved {os.path.basename(written)} "
                f"({mbytes(os.path.getsize(written))}) "
                f"in {os.path.dirname(written)}", 10000)
            self.update_actions()
        self.run_task("Exporting", f"Writing {os.path.basename(path)}...",
                      work, done)


    # Export straight into the finals folder, auto-numbered.
    def do_export_final(self):
        name = self.clip_name.text().strip() or "clip"
        path = unique_path(os.path.join(self.ensure_finals_dir(), f"{name}.m4a"))
        self._write_clip(path)
