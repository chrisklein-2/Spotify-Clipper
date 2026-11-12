import os
import subprocess
import sys
import time

from config import SESSION_DIR, ORPHAN_AGE

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