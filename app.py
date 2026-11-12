"""
app.py - MainWindow: owns state, builds the window, wires the mixins together.

  ui/*              widget construction (no logic)
  core/transport    play / pause / seek
  core/navigation   scrollbar, go-to, pieces list
  core/bookmarks    bookmark list
  core/status       action enabling, status bar, tick loop
  core/recording    source selection, capture
  core/fileio       load / append / join
  core/export       export, finals, share
  core/editing      delete / restore / undo / trim
"""
import shutil

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QMainWindow, QMessageBox, QVBoxLayout, QWidget

from config import DEFAULT_EXPORT_DIR, DEFAULT_FINALS_DIR, SESSION_DIR
from utils import clean_orphan_sessions
from editor import Timeline
from audio_backends import StreamPlayer
from ui import (BusyDialog, ActionsMixin, MenuMixin, PanelsMixin, OutputPanelMixin)
from controllers import (
    TaskThread, SourceMixin, RecordingMixin, FileIOMixin, ExportMixin,
    FoldersMixin, CoverMixin, EditingMixin, TransportMixin, NavigationMixin,
    BookmarksMixin, StatusMixin,
)

class MainWindow(
    QMainWindow,
    ActionsMixin, MenuMixin, PanelsMixin, OutputPanelMixin,
    RecordingMixin, FileIOMixin, ExportMixin, EditingMixin,
    FoldersMixin, CoverMixin,
    TransportMixin, NavigationMixin, BookmarksMixin, StatusMixin, SourceMixin,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpotClip")
        clean_orphan_sessions()
        self._init_state()
        self._build_ui()
        self._post_build()

    # ---- setup ----------------------------------------------------------

    def _init_state(self):
        self.settings = QSettings("SpotClip", "SpotClip")
        self.export_dir = self.settings.value("export_dir", DEFAULT_EXPORT_DIR)
        self.finals_dir = self.settings.value("finals_dir", DEFAULT_FINALS_DIR)
        self.cover_path = self.settings.value("cover", None)
        self.source_label = self.settings.value("source_label", None)

        self.device = None
        self.timeline = Timeline()
        self.player = StreamPlayer()
        self.recorder = None
        self.session_path = None
        self.last_export = None
        self.unsaved = False
        self.bookmarks = []

        self._task = None
        self._was_playing = False
        self._syncing_scroll = False
        self._seek_target = None
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(150)
        self._seek_timer.timeout.connect(self._do_seek)

    def _build_ui(self):
        self._build_actions()
        self._build_menu_bar()
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(8, 6, 8, 2)
        lay.setSpacing(5)
        lay.addLayout(self._build_top_row())
        lay.addLayout(self._build_middle(), 1)
        lay.addLayout(self._build_nav_row())
        lay.addWidget(self._build_edit_group())
        lay.addWidget(self._build_output_group())
        lay.addWidget(self._build_hint())
        self.setCentralWidget(central)
        self.statusBar()
        self.setMinimumSize(880, 600)
        self.resize(1080, 680)

    def _post_build(self):
        self.set_cover(self.cover_path)
        self.resolve_source()
        self.set_pieces_visible(False)
        self.ensure_export_dir()
        self.update_actions()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)

    # ---- shared plumbing ------------------------------------------------

    def invalidate(self, *_):
        """Something that affects the output changed."""
        if self.timeline.duration() > 0:
            self.unsaved = True
        self.refresh_pieces()
        self.update_actions()

    def run_task(self, title, message, func, on_done, on_fail=None):
        dlg = BusyDialog(title, message, self)
        task = TaskThread(func, self)
        self._task = task
        task.progress.connect(dlg.set_progress)
        task.done.connect(lambda r: (dlg.accept(), on_done(r)))
        def failed(msg):
            dlg.accept()
            QMessageBox.critical(self, title, msg)
            if on_fail:
                on_fail(msg)
        task.failed.connect(failed)
        task.start()
        dlg.exec()

    def closeEvent(self, ev):
        if self.timeline.duration() > 0 and self.unsaved:
            answer = QMessageBox.warning(
                self, "Exit without saving?",
                "The current clip has NOT been exported to the computer and the "
                "recording will be deleted.\n\n(Sending to the phone does not save "
                "it here.)\n\nExit anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                ev.ignore()
                return
        self.player.stop()
        if self.recorder is not None:
            try:
                self.recorder.stop()
            except Exception:
                pass
        self.drop_session()
        shutil.rmtree(SESSION_DIR, ignore_errors=True)
        ev.accept()