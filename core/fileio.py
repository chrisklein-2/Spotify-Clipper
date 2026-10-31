"""
app_fileio.py - FileIOMixin: session management, load, append, join.

Mixed into MainWindow.
"""

import os
import time

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from store import AudioStore                                      
from editor import Keep, format_time                                  
from processing import append_decoded, decode_to_raw                   
from .constants import LOAD_FILTER, SESSION_DIR                        
from .dialogs import JoinDialog                                       
from .helpers import mbytes                                            

class FileIOMixin:

    def new_session_path(self):
        os.makedirs(SESSION_DIR, exist_ok=True)
        return os.path.join(SESSION_DIR, f"rec_{int(time.time())}.raw")

    def drop_session(self):
        if self.timeline.store is not None:
            self.timeline.store.close()
        if self.session_path and os.path.exists(self.session_path):
            try:
                os.remove(self.session_path)
            except OSError:
                pass
        self.session_path = None

    def confirm_discard(self, verb="start a new recording"):
        if self.timeline.duration() <= 0:
            return True
        if self.unsaved:
            text = (
                f"The current clip has NOT been exported.\n\n"
                f"If you {verb} now, those edits are gone for good.\n\nContinue?"
            )
        else:
            text = (
                "This will replace the current recording.\n\n"
                "(Your last export is safe on disk.)\n\nContinue?"
            )
        return (
            QMessageBox.warning(
                self, "Discard current recording?", text,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _show_store(self, store, name_hint=None, keeps=None):
        self.timeline.set_store(store)
        if keeps:
            self.timeline._tidy(keeps)
        self.wave.set_timeline(self.timeline)
        self.wave.set_fade_ms(self.cut_fade.value())
        self.wave.set_bookmarks(self.bookmarks)
        if name_hint:
            self.clip_name.setText(name_hint)
        self.last_export = None
        self.invalidate()
        self.sync_scrollbar()
        self.statusBar().showMessage(
            f"{format_time(store.duration())} on disk "
            f"({mbytes(os.path.getsize(store.path))}), overview "
            f"{mbytes(store.pyramid_bytes())} in RAM",
            10000,
        )

    def load_file(self):
        if not self.confirm_discard("load a file"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open audio / video", self.ensure_export_dir(), LOAD_FILTER
        )
        if not path:
            return
        self.stop_playback()
        self.drop_session()
        self.bookmarks.clear()
        raw = self.new_session_path()
        self.session_path = raw

        def work(report):
            _, rate, chans = decode_to_raw(path, raw)
            store = AudioStore(raw, rate, chans)
            store.build_pyramid(report)
            return store

        def done(store):
            self._show_store(store, os.path.splitext(os.path.basename(path))[0])
            self.unsaved = False
            self.update_actions()

        self.run_task("Loading", f"Decoding {os.path.basename(path)}...", work, done)

    def append_file(self):
        if self.timeline.duration() <= 0:
            self.load_file()
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Append audio / video to the end",
            self.ensure_export_dir(), LOAD_FILTER,
        )
        if not path:
            return
        self.stop_playback()
        old_keeps = [(k.start, k.end) for k in self.timeline.keeps]
        old_end = self.timeline.duration()
        raw = self.session_path
        rate = self.timeline.samplerate()
        chans = self.timeline.channels()
        self.timeline.store.close()

        def work(report):
            append_decoded(path, raw, rate, chans)
            store = AudioStore(raw, rate, chans)
            store.build_pyramid(report)
            return store

        def done(store):
            keeps = [Keep(a, b) for a, b in old_keeps]
            keeps.append(Keep(old_end, store.duration()))
            self._show_store(store, keeps=keeps)
            self.statusBar().showMessage(
                f"Appended {os.path.basename(path)} - total "
                f"{format_time(store.duration())}",
                10000,
            )

        self.run_task(
            "Appending",
            f"Decoding and joining {os.path.basename(path)}...",
            work, done,
        )

    def join_files(self):
        if not self.confirm_discard("join files"):
            return
        dlg = JoinDialog(self.ensure_export_dir(), self)
        if dlg.exec() != QDialog.Accepted:
            return
        paths = dlg.files()
        if not paths:
            return
        self.stop_playback()
        self.drop_session()
        self.bookmarks.clear()
        raw = self.new_session_path()
        self.session_path = raw

        def work(report):
            frames, rate, chans = decode_to_raw(paths[0], raw)
            bounds = [frames]
            for p in paths[1:]:
                bounds.append(append_decoded(p, raw, rate, chans))
            store = AudioStore(raw, rate, chans)
            store.build_pyramid(report)
            return store, bounds, rate

        def done(result):
            store, bounds, rate = result
            keeps, start = [], 0
            for end in bounds:
                if end > start:
                    keeps.append(Keep(start / rate, end / rate))
                start = end
            self._show_store(
                store,
                os.path.splitext(os.path.basename(paths[0]))[0] + "_joined",
                keeps,
            )
            self.statusBar().showMessage(
                f"Joined {len(paths)} files - {format_time(store.duration())}", 10000
            )

        self.run_task(
            "Joining", f"Decoding and joining {len(paths)} files...", work, done
        )