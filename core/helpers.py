"""
helpers.py - small pure-ish utilities used across the app.
"""

import os
import re
import subprocess
import sys
import time

from PySide6.QtWidgets import QFrame, QPushButton

from .constants import SESSION_DIR, ORPHAN_AGE


def parse_time(text):
    """Parse 4:20, 1:04:20, 4m20s, 260 or 2h into seconds; None if unreadable."""
    text = (text or "").strip().lower().replace(" ", "")
    if not text:
        return None
    if ":" in text:
        try:
            total = 0.0
            for part in text.split(":"):
                total = total * 60 + float(part or 0)
            return total
        except ValueError:
            return None
    match = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s?)?", text
    )
    if not match or not any(match.groups()):
        return None
    hours = float(match.group(1) or 0)
    minutes = float(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def sep():
    """Thin vertical separator line."""
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setFrameShadow(QFrame.Plain)
    return f


def abtn(action, primary=False, min_w=0):
    """QPushButton wired to a QAction."""
    b = QPushButton(action.text())
    tip = action.text()
    if not action.shortcut().isEmpty():
        tip += f"   [{action.shortcut().toString()}]"
    b.setToolTip(tip)
    b.setEnabled(action.isEnabled())
    b.clicked.connect(action.trigger)
    action.changed.connect(lambda a=action, b=b: b.setEnabled(a.isEnabled()))
    if primary:
        b.setObjectName("primary")
    if min_w:
        b.setMinimumWidth(min_w)
    return b


def reveal_folder(path):
    """Open a folder in the system file manager."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        print("could not open folder:", exc)


def clean_orphan_sessions():
    """Delete leftover session files from crashed runs."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    now = time.time()
    for name in os.listdir(SESSION_DIR):
        path = os.path.join(SESSION_DIR, name)
        try:
            if now - os.path.getmtime(path) > ORPHAN_AGE:
                os.remove(path)
        except OSError:
            pass


def mbytes(value):
    """Megabytes, formatted."""
    return f"{value / 1e6:.1f} MB"