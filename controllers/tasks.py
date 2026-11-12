from PySide6.QtCore import QThread, Signal

class TaskThread(QThread):
    """Runs one callable off the GUI thread with progress reporting."""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self.func = func

    def run(self):
        try:
            self.done.emit(self.func(self.progress.emit))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")