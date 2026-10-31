"""
main.py - entry point for SpotClip.

    python main.py

Checks for ffmpeg/ffprobe up front, because a missing PATH entry otherwise only shows up
as a confusing failure halfway through an export.
"""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import MainWindow
from processing import missing_tools
from theme import apply_dark_theme


# Warn clearly if ffmpeg/ffprobe are not on PATH; returns True if we can continue.
def check_tools():
    missing = missing_tools()
    if not missing:
        return True
    QMessageBox.critical(
        None, "Missing tools",
        "SpotClip needs these on your PATH but cannot find them:\n\n    "
        + ", ".join(missing) +
        "\n\nCheck with:\n    where " + missing[0] +
        "\n\nIf that prints nothing, the PATH entry is wrong or stale — remember that "
        "PATH holds literal folder paths, so renaming or moving the ffmpeg\\bin folder "
        "breaks it.\n\nWithout these you can still record, but loading mp3/m4a/mp4 and "
        "exporting anything other than .wav will fail.")
    return True


# Start Qt, apply the dark theme, show the window.
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SpotClip")
    apply_dark_theme(app)
    check_tools()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())