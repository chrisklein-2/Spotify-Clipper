"""controllers/folders.py - FoldersMixin: export/finals folders, move, send to phone."""
import os
import shutil

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from processing import unique_path
from share import ShareDialog, ShareFolderDialog
from config import DEFAULT_EXPORT_DIR, DEFAULT_FINALS_DIR


class FoldersMixin:

    def _ensure_dir(self, attr, default):
        path = getattr(self, attr)
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            path = default
            setattr(self, attr, path)
            os.makedirs(path, exist_ok=True)
        return path

    def ensure_export_dir(self):
        return self._ensure_dir("export_dir", DEFAULT_EXPORT_DIR)

    def ensure_finals_dir(self):
        return self._ensure_dir("finals_dir", DEFAULT_FINALS_DIR)

    def choose_export_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose export folder", self.ensure_export_dir())
        if not path:
            return
        self.export_dir = path
        self.settings.setValue("export_dir", path)
        self.ensure_export_dir()
        self.statusBar().showMessage(f"Exports will go to {path}", 8000)

    def choose_finals_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose finals folder", self.ensure_finals_dir())
        if not path:
            return
        self.finals_dir = path
        self.settings.setValue("finals_dir", path)
        self.ensure_finals_dir()
        self.statusBar().showMessage(f"Finals will go to {path}", 8000)

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

    def send_folder_to_phone(self):
        dlg = ShareFolderDialog(
            [("Finals", self.ensure_finals_dir()),
             ("Exports", self.ensure_export_dir())], self)
        if dlg.exec() == QDialog.Accepted and dlg.chosen():
            ShareDialog(dlg.chosen(), self).exec()