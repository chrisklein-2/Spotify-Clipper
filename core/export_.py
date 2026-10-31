"""
app_export.py - ExportMixin: cover art, loudness guard, export, share.

Mixed into MainWindow.
"""

import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog

from editor import ClipStreamer                   
from processing import IMAGE_FILTER, LoudnessGuard, export_stream, unique_path
from share import ShareDialog, ShareFolderDialog                                          
from .constants import APP_DIR, DEFAULT_EXPORT_DIR, DEFAULT_FINALS_DIR 
from .helpers import mbytes                                            


import sounddevice as sd                                    # add at top
from processing import (IMAGE_FILTER, LoudnessGuard, ceiling_test_tone,
                        export_stream, unique_path)         # updated


class ExportMixin:

    def ensure_export_dir(self):
        try:
            os.makedirs(self.export_dir, exist_ok=True)
        except Exception:
            self.export_dir = DEFAULT_EXPORT_DIR
            os.makedirs(self.export_dir, exist_ok=True)
        return self.export_dir

    def choose_export_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose export folder", self.ensure_export_dir()
        )
        if not path:
            return
        self.export_dir = path
        self.settings.setValue("export_dir", path)
        self.ensure_export_dir()
        self.statusBar().showMessage(f"Exports will go to {path}", 8000)

    def set_cover(self, path):
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                self.cover_path = path
                self.cover_btn.setIcon(
                    QIcon(pix.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                )
                name = os.path.basename(path)
                self.cover_btn.setText(
                    name if len(name) <= 16 else name[:15] + "\u2026"
                )
                self.cover_btn.setToolTip(f"Cover: {path}\nEmbedded in .m4a and .mp3.")
                self.settings.setValue("cover", path)
                return
        self.cover_path = None
        self.cover_btn.setIcon(QIcon())
        self.cover_btn.setText("Cover: none")
        self.cover_btn.setToolTip("Artwork embedded into .m4a and .mp3 exports.")
        self.settings.remove("cover")

    def choose_cover(self):
        start = os.path.dirname(self.cover_path) if self.cover_path else APP_DIR
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose cover image", start, IMAGE_FILTER
        )
        if path:
            self.set_cover(path)

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

    # Serve a whole folder to the phone; defaults to the finals folder.
    # Pick a folder (with contents preview), then serve it to the phone.
    def send_folder_to_phone(self):
        dlg = ShareFolderDialog(
            [("Finals", self.ensure_finals_dir()),
             ("Exports", self.ensure_export_dir())], self)
        if dlg.exec() == QDialog.Accepted and dlg.chosen():
            ShareDialog(dlg.chosen(), self).exec()

    # Make sure the finals folder exists, falling back to the default.
    def ensure_finals_dir(self):
        try:
            os.makedirs(self.finals_dir, exist_ok=True)
        except Exception:
            self.finals_dir = DEFAULT_FINALS_DIR
            os.makedirs(self.finals_dir, exist_ok=True)
        return self.finals_dir

    # Let the user point finished clips at another folder.
    def choose_finals_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choose finals folder",
                                                self.ensure_finals_dir())
        if not path:
            return
        self.finals_dir = path
        self.settings.setValue("finals_dir", path)
        self.ensure_finals_dir()
        self.statusBar().showMessage(f"Finals will go to {path}", 8000)

    # Export straight into the finals folder, auto-numbered.
    def do_export_final(self):
        name = self.clip_name.text().strip() or "clip"
        path = unique_path(os.path.join(self.ensure_finals_dir(), f"{name}.m4a"))
        self._write_clip(path)

    # Move the most recent export from exports/ into finals/.
    def move_to_finals(self):
        if not self.last_export or not os.path.exists(self.last_export):
            QMessageBox.information(self, "Nothing to move",
                                    "Export a clip first (Ctrl+E).")
            return
        dest = unique_path(os.path.join(self.ensure_finals_dir(),
                                        os.path.basename(self.last_export)))
        shutil.move(self.last_export, dest)
        self.last_export = dest
        self.statusBar().showMessage(f"Moved to {dest}", 8000)

    # Play a 1 s tone at the ceiling: the loudest any export can ever be.
    def test_ceiling(self):
        self.stop_playback()
        rate = 44100
        sd.play(ceiling_test_tone(self.ceiling.value(), rate), rate)
        self.statusBar().showMessage(
            f"Playing a {self.ceiling.value():.1f} dBFS tone — nothing in the "
            f"export will be louder than this at your current volume.", 6000)
