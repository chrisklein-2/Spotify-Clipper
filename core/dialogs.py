"""
dialogs.py - modal dialogs: BusyDialog, SourceDialog, JoinDialog.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout,
)

from audio_backends import default_device_index, list_capture_devices
from .constants import HELP_HTML, LOAD_FILTER


class BusyDialog(QDialog):
    """Progress dialog that can be a spinner or a real percentage bar."""

    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setMinimumWidth(400)
        self.label = QLabel(message)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        lay = QVBoxLayout(self)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)

    def set_progress(self, fraction):
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 1000)
        self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))


class SourceDialog(QDialog):
    """Picks the capture source in a dialog rather than a menu."""

    def __init__(self, current_label=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select audio source")
        self.setMinimumSize(560, 340)
        self.devices = []
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        note = QLabel(
            "LOOPBACK records everything your speakers play.\n"
            "To capture Spotify alone: install VB-CABLE, set Spotify's output to\n"
            "CABLE Input in the Windows volume mixer, then pick INPUT CABLE Output here."
        )
        note.setStyleSheet("color:#9699a3;")
        refresh = QPushButton("Refresh list")
        refresh.clicked.connect(self.refresh)
        ok = QPushButton("Use this source")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(refresh)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root = QVBoxLayout(self)
        root.addWidget(note)
        root.addWidget(self.list, 1)
        root.addLayout(buttons)
        self.refresh(current_label)

    def refresh(self, keep_label=None):
        if keep_label is None:
            current = self.list.currentItem()
            keep_label = current.data(Qt.UserRole).label if current else None
        self.devices = list_capture_devices()
        self.list.clear()
        for device in self.devices:
            item = QListWidgetItem(device.label)
            item.setData(Qt.UserRole, device)
            self.list.addItem(item)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole).label == keep_label:
                self.list.setCurrentRow(i)
                return
        index = default_device_index(self.devices)
        if 0 <= index < self.list.count():
            self.list.setCurrentRow(index)

    def chosen(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None


class JoinDialog(QDialog):
    """Pick several files and drag them into playback order."""

    def __init__(self, start_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Join audio files")
        self.setMinimumSize(540, 330)
        self.start_dir = start_dir
        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setToolTip("Drag to reorder. They are joined top to bottom.")
        add = QPushButton("Add files...")
        add.clicked.connect(self.add_files)
        rm = QPushButton("Remove")
        rm.clicked.connect(self.remove_selected)
        up = QPushButton("Move up")
        up.clicked.connect(lambda: self.move(-1))
        dn = QPushButton("Move down")
        dn.clicked.connect(lambda: self.move(1))
        ok = QPushButton("Join")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        side = QVBoxLayout()
        for b in (add, rm, up, dn):
            side.addWidget(b)
        side.addStretch(1)
        side.addWidget(ok)
        side.addWidget(cancel)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        body.addLayout(side)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Joined top to bottom - drag to reorder.\n"
            "Sample rate and channels convert automatically."
        ))
        root.addLayout(body, 1)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add files", self.start_dir, LOAD_FILTER
        )
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)

    def remove_selected(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def move(self, delta):
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self.list.count()):
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def files(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]


class HelpDialog(QDialog):
    """Scrollable help window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("How to use SpotClip")
        self.resize(680, 620)
        browser = QTextBrowser()
        browser.setHtml(HELP_HTML)
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(browser)
        lay.addWidget(close)