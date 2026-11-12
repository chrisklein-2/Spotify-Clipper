"""controllers/cover.py - CoverMixin: cover-art selection."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileDialog

from processing import IMAGE_FILTER
from config import APP_DIR


class CoverMixin:

    def set_cover(self, path):
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                self.cover_path = path
                self.cover_btn.setIcon(QIcon(
                    pix.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                name = os.path.basename(path)
                self.cover_btn.setText(name if len(name) <= 16 else name[:15] + "\u2026")
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
            self, "Choose cover image", start, IMAGE_FILTER)
        if path:
            self.set_cover(path)