
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXPORT_DIR = os.path.join(APP_DIR, "exports")
DEFAULT_FINALS_DIR = os.path.join(APP_DIR, "finals")
SESSION_DIR = os.path.join(APP_DIR, "session")
PLAY_BLOCK = 8192
ORPHAN_AGE = 24 * 3600

LOAD_FILTER = (
    "Audio / video (*.wav *.flac *.ogg *.aiff *.mp3 *.m4a *.mp4 *.aac "
    "*.opus *.webm *.mkv *.mov *.wma);;All files (*)"
)
