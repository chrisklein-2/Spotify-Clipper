"""
app.py - MainWindow: UI construction, navigation, playback routing, tick loop.

All domain logic lives in mixins:
  RecordingMixin  (app_recording)  - source selection, capture
  FileIOMixin     (app_fileio)     - load / append / join
  ExportMixin     (app_export)     - export, cover, loudness
  EditingMixin    (app_editing)    - delete / restore / undo / trim
"""

import shutil
import numpy as np
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QScrollBar, QSizePolicy, QVBoxLayout, QWidget,
)
# ── top-level modules (unchanged) ──
from audio_backends import SAMPLE_RATES, glitch_count
from editor import ClipStreamer, Piece, Timeline, format_time
from processing import BITRATES, estimate_mb
from waveform import WaveformView

from core import (
    DEFAULT_EXPORT_DIR, DEFAULT_FINALS_DIR, SESSION_DIR,
    abtn, clean_orphan_sessions, parse_time, reveal_folder, sep,
    BusyDialog, HelpDialog, StreamPlayer, TaskThread,
    RecordingMixin, FileIOMixin, ExportMixin, EditingMixin,
)


class MainWindow(QMainWindow, RecordingMixin, FileIOMixin, ExportMixin, EditingMixin):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpotClip")
        clean_orphan_sessions()
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
        self._plan = None
        self._task = None
        self._was_playing = False
        self._syncing_scroll = False
        self.bookmarks = []  

        self._seek_target = None
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(150)
        self._seek_timer.timeout.connect(self._do_seek)

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

        self.set_cover(self.cover_path)
        self.resolve_source()
        self.set_pieces_visible(False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)
        self.ensure_export_dir()
        self.update_actions()

    # ---- actions & menus ------------------------------------------------

    def _build_actions(self):
        self.act_mark_in = QAction("Mark in  [", self, shortcut="[")
        self.act_mark_in.triggered.connect(lambda: self.wave.mark_in())
        self.act_mark_out = QAction("Mark out  ]", self, shortcut="]")
        self.act_mark_out.triggered.connect(lambda: self.wave.mark_out())
        self.act_delete = QAction("Delete selection", self, shortcut=QKeySequence.Delete)
        self.act_delete.triggered.connect(self.delete_selection)
        self.act_restore = QAction("Restore selection", self, shortcut="Ctrl+R")
        self.act_restore.triggered.connect(self.restore_selection)
        self.act_undo = QAction("Undo", self, shortcut=QKeySequence.Undo)
        self.act_undo.triggered.connect(self.do_undo)
        self.act_redo = QAction("Redo", self, shortcut="Ctrl+Y")
        self.act_redo.triggered.connect(self.do_redo)
        self.act_trim = QAction("Auto-trim silence", self, shortcut="Ctrl+T")
        self.act_trim.triggered.connect(self.auto_trim)
        self.act_reset = QAction("Reset all edits", self)
        self.act_reset.triggered.connect(self.reset_edits)
        self.act_fit = QAction("Zoom fit", self, shortcut="Ctrl+0")
        self.act_fit.triggered.connect(lambda: self.wave.zoom_fit())
        self.act_zoomsel = QAction("Zoom to selection", self, shortcut="Ctrl+2")
        self.act_zoomsel.triggered.connect(lambda: self.wave.zoom_selection())
        self.act_selall = QAction("Select all", self, shortcut=QKeySequence.SelectAll)
        self.act_selall.triggered.connect(lambda: self.wave.select_all())
        self.act_play = QAction("Play / Pause", self, shortcut="Space")
        self.act_play.triggered.connect(self.toggle_play)
        self.act_from_start = QAction("From start", self, shortcut="Ctrl+Space")
        self.act_from_start.triggered.connect(self.play_from_start)
        self.act_export = QAction("Export", self, shortcut="Ctrl+E")
        self.act_export.triggered.connect(self.do_export)
        self.act_send = QAction("Send folder to phone...", self, shortcut="Ctrl+P")
        self.act_send.triggered.connect(self.send_folder_to_phone)
        self.act_finalize = QAction("Finalize", self, shortcut="Ctrl+Shift+F")
        self.act_finalize.setToolTip("Export the edited clip straight into finals/")
        self.act_finalize.triggered.connect(self.do_export_final)
        self.act_pieces = QAction("Show kept pieces", self, shortcut="Ctrl+L")
        self.act_pieces.setCheckable(True)
        self.act_pieces.setChecked(False)
        self.act_pieces.toggled.connect(self.set_pieces_visible)
        self.act_help = QAction("Help", self, shortcut="F1")
        self.act_help.triggered.connect(self.show_help)
        self.act_bookmark = QAction("Add bookmark", self, shortcut="Ctrl+B")
        self.act_bookmark.triggered.connect(self.add_bookmark)
        self.act_rm_bookmark = QAction("Remove nearest bookmark", self, shortcut="Ctrl+Shift+B")
        self.act_rm_bookmark.triggered.connect(self.remove_nearest_bookmark)
        self.act_clear_bookmarks = QAction("Clear all bookmarks", self)
        self.act_clear_bookmarks.triggered.connect(self.clear_bookmarks)
        self.act_prev_bookmark = QAction("Previous bookmark", self, shortcut="Ctrl+,")
        self.act_prev_bookmark.triggered.connect(self.goto_prev_bookmark)
        self.act_next_bookmark = QAction("Next bookmark", self, shortcut="Ctrl+.")
        self.act_next_bookmark.triggered.connect(self.goto_next_bookmark)
        for a in (
            self.act_mark_in, self.act_mark_out, self.act_delete, self.act_restore,
            self.act_undo, self.act_redo, self.act_trim, self.act_reset, self.act_fit,
            self.act_zoomsel, self.act_selall, self.act_play, self.act_from_start,
            self.act_export, self.act_send, self.act_pieces, self.act_help, self.act_bookmark, self.act_rm_bookmark,
            self.act_clear_bookmarks, self.act_prev_bookmark,
            self.act_next_bookmark, self.act_finalize
        ):
            self.addAction(a)

    def _build_menu_bar(self):
        bar = self.menuBar()
        fm = bar.addMenu("File")
        fm.addAction("Select audio source...", self.choose_source, "Ctrl+I")
        fm.addSeparator()
        fm.addAction("Load audio / video file...", self.load_file, "Ctrl+O")
        fm.addAction("Append audio file...", self.append_file)
        fm.addAction("Join audio files...", self.join_files, "Ctrl+J")
        fm.addSeparator()
        fm.addAction(self.act_export)
        fm.addAction("Export as...", self.do_export_as, "Ctrl+Shift+E")
        fm.addAction(self.act_finalize)
        fm.addAction("Move last export to finals", self.move_to_finals)
        fm.addAction(self.act_send)
        fm.addSeparator()
        fm.addAction("Choose cover image...", self.choose_cover)
        fm.addAction("Set export folder...", self.choose_export_dir)
        fm.addAction("Set finals folder...", self.choose_finals_dir)
        fm.addAction("Open export folder", lambda: reveal_folder(self.ensure_export_dir()))
        fm.addAction("Open finals folder", lambda: reveal_folder(self.ensure_finals_dir()))
        fm.addSeparator()
        fm.addAction("Quit", self.close, "Ctrl+Q")

        em = bar.addMenu("Edit")
        em.addAction(self.act_undo)
        em.addAction(self.act_redo)
        em.addSeparator()
        em.addAction(self.act_mark_in)
        em.addAction(self.act_mark_out)
        em.addAction(self.act_selall)
        em.addSeparator()
        em.addAction(self.act_delete)
        em.addAction(self.act_restore)
        em.addSeparator()
        em.addAction(self.act_trim)
        em.addAction(self.act_reset)
        em.addSeparator()                                                  # NEW
        em.addAction(self.act_bookmark)                                    # NEW
        em.addAction(self.act_rm_bookmark)                                 # NEW
        em.addAction(self.act_prev_bookmark)                               # NEW
        em.addAction(self.act_next_bookmark)                               # NEW
        em.addAction(self.act_clear_bookmarks)

        vm = bar.addMenu("View")
        vm.addAction(self.act_fit)
        vm.addAction(self.act_zoomsel)
        vm.addSeparator()
        vm.addAction(self.act_pieces)

        bar.addMenu("Help").addAction(self.act_help)

    # ---- UI build -------------------------------------------------------

    def _build_top_row(self):
        self.rec_btn = QPushButton("Record")
        self.rec_btn.setObjectName("record")
        self.rec_btn.setCheckable(True)
        self.rec_btn.setMinimumWidth(115)
        self.rec_btn.clicked.connect(self.toggle_record)
        self.stop_rec_btn = QPushButton("Stop rec")                        # NEW
        self.stop_rec_btn.setMinimumWidth(80)                              # NEW
        self.stop_rec_btn.setEnabled(False)                                # NEW
        self.stop_rec_btn.setToolTip("Finish recording and load for editing")
        self.stop_rec_btn.clicked.connect(self.stop_record)                # NEW
        self.source_btn = QPushButton("Source: none")
        self.source_btn.setMinimumWidth(230)
        self.source_btn.setToolTip("Click to choose what to record   [Ctrl+I]")
        self.source_btn.clicked.connect(self.choose_source)
        self.clip_name = QLineEdit("clip")
        self.clip_name.setPlaceholderText("Clip name (used as the filename and title)")
        self.clip_name.setMinimumWidth(320)
        self.clip_name.setToolTip("Filename and metadata title on export.")
        self.sr_box = QComboBox()
        for rate, label in SAMPLE_RATES:
            self.sr_box.addItem(label, rate)
        self.sr_box.setToolTip(
            "Match this to your device's rate in Windows Sound\n"
            "settings. A mismatch forces a resample."
        )
        self.sr_box.currentIndexChanged.connect(self.check_rate_match)
        self.mono_box = QCheckBox("Mono")
        self.mono_box.setToolTip("Halves disk and file size — ideal for podcasts.")
        row = QHBoxLayout()
        row.addWidget(self.rec_btn)
        row.addWidget(self.stop_rec_btn)                                   # NEW
        row.addWidget(self.source_btn)
        row.addWidget(sep())
        row.addWidget(QLabel("Name:"))
        row.addWidget(self.clip_name, 1)
        row.addWidget(sep())
        row.addWidget(self.sr_box)
        row.addWidget(self.mono_box)
        return row

    def _build_middle(self):
        self.wave = WaveformView()
        self.wave.set_timeline(self.timeline)
        self.wave.selectionChanged.connect(self.update_actions)
        self.wave.playheadMoved.connect(self.on_playhead_moved)
        self.wave.viewChanged.connect(self.sync_scrollbar)
        self.wave.context_actions = [
            self.act_mark_in, self.act_mark_out, None,
            self.act_delete, self.act_restore, None,
            self.act_selall, self.act_zoomsel, self.act_fit,
            None, self.act_undo, self.act_redo, None,                                
            self.act_bookmark, self.act_rm_bookmark,
        ]
        self.collapse_btn = QPushButton("\u25c0")
        self.collapse_btn.setObjectName("collapse")
        self.collapse_btn.setFixedWidth(14)
        self.collapse_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.collapse_btn.setCheckable(True)
        self.collapse_btn.setChecked(True)
        self.collapse_btn.setToolTip("Show / hide the kept pieces list  [Ctrl+L]")
        self.collapse_btn.toggled.connect(self.act_pieces.setChecked)
        self.seg_list = QListWidget()
        self.seg_list.setToolTip("Pieces joined into the clip. Click one to jump to it.")
        self.seg_list.itemClicked.connect(self.on_piece_clicked)
        self.pieces_panel = QWidget()
        self.pieces_panel.setFixedWidth(195)
        self.pieces_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        panel = QVBoxLayout(self.pieces_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.addWidget(QLabel("Kept pieces"))
        panel.addWidget(self.seg_list, 1)
        mid = QHBoxLayout()
        mid.addWidget(self.wave, 1)
        mid.addWidget(self.collapse_btn)
        mid.addWidget(self.pieces_panel)
        return mid

    def _build_nav_row(self):
        self.scroll = QScrollBar(Qt.Horizontal)
        self.scroll.setRange(0, 0)
        self.scroll.setToolTip("Pan the view when zoomed in")
        self.scroll.valueChanged.connect(self.on_scroll)
        self.zoom_out_btn = QPushButton("\u2212")
        self.zoom_out_btn.setObjectName("tiny")
        self.zoom_out_btn.setFixedWidth(32)
        self.zoom_out_btn.setToolTip("Zoom out around the playhead   [-]")
        self.zoom_out_btn.clicked.connect(lambda: self.wave.zoom_out())
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setObjectName("tiny")
        self.zoom_in_btn.setFixedWidth(32)
        self.zoom_in_btn.setToolTip("Zoom in around the playhead   [+]")
        self.zoom_in_btn.clicked.connect(lambda: self.wave.zoom_in())
        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setToolTip("Zoom out to the whole recording   [Ctrl+0]")
        self.fit_btn.clicked.connect(lambda: self.wave.zoom_fit())
        self.goto_edit = QLineEdit()
        self.goto_edit.setFixedWidth(110)
        self.goto_edit.setPlaceholderText("4:20")
        self.goto_edit.setToolTip(
            "Jump to a time: 4:20, 1:04:20, 4m20s or 260\nPress Enter."
        )
        self.goto_edit.returnPressed.connect(self.do_goto)
        goto_btn = QPushButton("Go")
        goto_btn.clicked.connect(self.do_goto)
        row = QHBoxLayout()
        row.addWidget(self.scroll, 1)
        row.addWidget(self.zoom_out_btn)
        row.addWidget(self.zoom_in_btn)
        row.addWidget(self.fit_btn)
        row.addWidget(sep())
        row.addWidget(QLabel("Go to"))
        row.addWidget(self.goto_edit)
        row.addWidget(goto_btn)
        return row

    def _build_edit_group(self):
        g = QGroupBox("EDIT")
        g.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        row = QHBoxLayout(g)
        for a in (
            self.act_undo, self.act_redo, None, self.act_mark_in,
            self.act_mark_out, self.act_selall, None, self.act_delete,
            self.act_restore, None, self.act_trim, self.act_reset,
        ):
            row.addWidget(sep() if a is None else abtn(a))
        row.addStretch(1)
        return g

    def _build_output_group(self):
        g = QGroupBox("OUTPUT  /  SLEEP-SAFE")
        g.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.cut_fade = QDoubleSpinBox()
        self.cut_fade.setRange(0.0, 5000.0)
        self.cut_fade.setValue(500.0)
        self.cut_fade.setSingleStep(50.0)
        self.cut_fade.setSuffix(" ms")
        self.cut_fade.setMinimumWidth(95)
        self.cut_fade.setToolTip(
            "Every kept piece fades in at its start and out at\n"
            "its end. 500 ms = half a second each way.\n"
            "The orange wedges on the waveform show it."
        )
        self.cut_fade.valueChanged.connect(self.on_fade_changed)
        self.fade_out = QDoubleSpinBox()
        self.fade_out.setRange(0.0, 60.0)
        self.fade_out.setValue(1.0)
        self.fade_out.setSuffix(" s")
        self.fade_out.setMinimumWidth(80)
        self.fade_out.setToolTip("Extra long fade on the very end of the clip.")
        self.fade_out.valueChanged.connect(self.invalidate)
        self.night_box = QCheckBox("Quiet down loud parts")
        self.night_box.setChecked(True)
        self.night_box.setToolTip("Compressor + ceiling. Only turns things DOWN.")
        self.night_box.toggled.connect(self.invalidate)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(-40.0, -6.0)
        self.threshold.setValue(-20.0)
        self.threshold.setSuffix(" dB")
        self.threshold.setMinimumWidth(85)
        self.threshold.setToolTip(
            "Audio above this gets compressed.\n-20 gentle, -28 aggressive."
        )
        self.threshold.valueChanged.connect(self.invalidate)
        self.ceiling = QDoubleSpinBox()
        self.ceiling.setRange(-24.0, -0.5)
        self.ceiling.setValue(-3.0)
        self.ceiling.setSuffix(" dB")
        self.ceiling.setMinimumWidth(85)
        self.ceiling.setToolTip("Peak ceiling. Nothing in the file exceeds this.")
        self.ceiling.valueChanged.connect(self.invalidate)
        self.test_btn = QPushButton("Test")
        self.test_btn.setObjectName("tiny")
        self.test_btn.setFixedWidth(44)
        self.test_btn.setToolTip("Play a 1 s tone at the ceiling level —\n"
                                 "the loudest the export is allowed to get.")
        self.test_btn.clicked.connect(self.test_ceiling)
        self.bitrate = QComboBox()
        for kbps, label in BITRATES:
            self.bitrate.addItem(label, kbps)
        self.bitrate.setCurrentIndex(1)
        self.bitrate.setToolTip("AAC / MP3 bitrate. 48 kbps is plenty for speech.")
        self.bitrate.currentIndexChanged.connect(self.update_status)
        self.cover_btn = QPushButton("Cover: none")
        self.cover_btn.setMinimumWidth(150)
        self.cover_btn.setToolTip("Artwork embedded into .m4a and .mp3 exports.")
        self.cover_btn.clicked.connect(self.choose_cover)
        self.cover_clear = QPushButton("\u00d7")
        self.cover_clear.setObjectName("tiny")
        self.cover_clear.setFixedWidth(26)
        self.cover_clear.setToolTip("Remove the cover image")
        self.cover_clear.clicked.connect(lambda: self.set_cover(None))
        self.play_btn = abtn(self.act_play, primary=True, min_w=115)
        self.start_btn = abtn(self.act_from_start, min_w=90)
        self.raw_btn = QPushButton("Play raw")
        self.raw_btn.setToolTip("Play the original recording, ignoring the cuts.")
        self.raw_btn.clicked.connect(self.play_raw)
        self.export_btn = abtn(self.act_export, primary=True, min_w=85)
        self.finalize_btn = abtn(self.act_finalize, primary=True, min_w=100)  # was send_btn

        top = QHBoxLayout()
        top.setSpacing(7)
        top.addWidget(QLabel("Fade per cut"))
        top.addWidget(self.cut_fade)
        top.addWidget(QLabel("End fade"))
        top.addWidget(self.fade_out)
        top.addWidget(sep())
        top.addWidget(self.night_box)
        top.addWidget(QLabel("Threshold"))
        top.addWidget(self.threshold)
        top.addWidget(QLabel("Ceiling"))
        top.addWidget(self.ceiling)
        top.addWidget(self.test_btn)
        top.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(7)
        bottom.addWidget(self.play_btn)
        bottom.addWidget(self.start_btn)
        bottom.addWidget(self.raw_btn)
        bottom.addWidget(sep())
        bottom.addWidget(self.bitrate)
        bottom.addWidget(self.cover_btn)
        bottom.addWidget(self.cover_clear)
        bottom.addStretch(1)
        bottom.addWidget(self.export_btn)
        bottom.addWidget(self.finalize_btn) 

        outer = QVBoxLayout(g)
        outer.setSpacing(7)
        outer.addLayout(top)
        outer.addLayout(bottom)
        return g

    def _build_hint(self):
        h = QLabel(
            "Drag = select  \u2022  Ruler = playhead  \u2022  [ ] = mark in/out  "
            "\u2022  Del = delete  \u2022  Space = from playhead  \u2022  "
            "Ctrl+B = bookmark  \u2022  + / - = zoom  \u2022  Ctrl+Z = undo  "
            "\u2022  F1 = help"
        )
        h.setObjectName("hint")
        h.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        h.setFixedHeight(h.sizeHint().height())
        return h

    # ---- navigation / view ----------------------------------------------

    def set_pieces_visible(self, shown):
        self.pieces_panel.setVisible(shown)
        self.collapse_btn.setChecked(shown)
        self.collapse_btn.setText("\u25c0" if shown else "\u25b6")

    def sync_scrollbar(self):
        self._syncing_scroll = True
        total = self.timeline.duration()
        span = self.wave.span()
        if total <= span + 1e-6:
            self.scroll.setRange(0, 0)
            self.scroll.setEnabled(False)
        else:
            self.scroll.setEnabled(True)
            self.scroll.setRange(0, int((total - span) * 1000))
            self.scroll.setPageStep(max(1, int(span * 1000)))
            self.scroll.setSingleStep(max(1, int(span * 100)))
            self.scroll.setValue(int(self.wave.view_start * 1000))
        self._syncing_scroll = False

    def on_scroll(self, value):
        if self._syncing_scroll:
            return
        self.wave.scroll_to(value / 1000.0)

    def do_goto(self):
        seconds = parse_time(self.goto_edit.text())
        if seconds is None:
            self.statusBar().showMessage(
                "Could not read that time. Try 4:20, 1:04:20, 4m20s or 260", 5000
            )
            return
        if self.timeline.duration() <= 0:
            return
        if seconds > self.timeline.duration():
            self.statusBar().showMessage(
                f"{format_time(seconds)} is past the end "
                f"({format_time(self.timeline.duration())})",
                5000,
            )
            return
        self.wave.goto(seconds)
        self.wave.setFocus()

    def on_fade_changed(self, value):
        self.wave.set_fade_ms(value)
        self.invalidate()

    def on_playhead_moved(self, t):
        if self.player.is_playing():
            self._seek_target = t
            self._seek_timer.start()
        self.update_status()

    # Restart the active stream at the requested time.
    def _do_seek(self):
        if self._seek_target is None or not self.player.is_playing():
            self._seek_target = None
            return
        t, self._seek_target = self._seek_target, None
        if self.player.mode == "raw":
            self.play_raw()          # reads self.wave.playhead, already moved
            return
        if self._plan is None:
            return
        src = int(t * self.timeline.samplerate())
        start = self._plan.out_frame(src)
        if start >= self._plan.total_frames():
            self.stop_playback()
            return
        self.player.play(self._plan, "clip", start)

    def on_piece_clicked(self, item):
        a, b = item.data(Qt.UserRole)
        self.wave.set_selection(a, b)
        self.wave.goto(a)

    # ---- invalidation / task runner -------------------------------------

    def invalidate(self, *_):
        self._plan = None
        self.unsaved = True
        self.update_actions()

    def run_task(self, title, message, func, on_done):
        dlg = BusyDialog(title, message, self)
        task = TaskThread(func, self)
        self._task = task
        task.progress.connect(dlg.set_progress)
        task.done.connect(lambda r: (dlg.accept(), on_done(r)))
        task.failed.connect(
            lambda m: (dlg.accept(), QMessageBox.critical(self, title, m))
        )
        task.start()
        dlg.exec()

    # ---- playback -------------------------------------------------------

    def stop_playback(self):
        self.player.stop()
        self.update_actions()

    def toggle_play(self):
        if self.player.is_playing():
            self.stop_playback()
            return
        streamer = self.make_streamer()
        if streamer is None:
            self.statusBar().showMessage(
                "Nothing to play - everything is deleted.", 4000
            )
            return
        src = int(self.wave.playhead * self.timeline.samplerate())
        start = streamer.out_frame(src)
        if start >= streamer.total_frames():
            start = 0
        self._plan = streamer
        self.player.play(streamer, "clip", start)
        self.update_actions()

    def play_from_start(self):
        streamer = self.make_streamer()
        if streamer is None:
            self.statusBar().showMessage(
                "Nothing to play - everything is deleted.", 4000
            )
            return
        self._plan = streamer
        self.player.play(streamer, "clip", 0)
        self.update_actions()

    def play_raw(self):
        if self.timeline.duration() <= 0:
            return
        rate = self.timeline.samplerate()
        start = int(self.wave.playhead * rate)
        piece = Piece(0, start, max(1, self.timeline.frames() - start), 0)
        streamer = ClipStreamer(self.timeline.store, [piece], None, 0)
        streamer.raw_offset = start
        self._plan = streamer
        self.player.play(streamer, "raw", 0)
        self.update_actions()

    def show_help(self):
        HelpDialog(self).exec()

    # ---- status / tick --------------------------------------------------

    def update_actions(self):
        has = self.timeline.duration() > 0
        sel = self.wave.selection() is not None
        self.act_delete.setEnabled(has and sel)
        self.act_restore.setEnabled(has and sel)
        self.act_zoomsel.setEnabled(has and sel)
        self.act_undo.setEnabled(self.timeline.can_undo())
        self.act_redo.setEnabled(self.timeline.can_redo())
        self.act_bookmark.setEnabled(has or self.recorder is not None)
        self.act_rm_bookmark.setEnabled(has and bool(self.bookmarks))
        self.act_clear_bookmarks.setEnabled(bool(self.bookmarks))
        self.act_prev_bookmark.setEnabled(has and bool(self.bookmarks))
        self.act_next_bookmark.setEnabled(has and bool(self.bookmarks))
        for action in (
            self.act_mark_in, self.act_mark_out, self.act_trim, self.act_reset,
            self.act_fit, self.act_selall, self.act_play, self.act_from_start,
            self.act_export, self.act_finalize,
        ):
            action.setEnabled(has)
        for widget in (
            self.raw_btn, self.goto_edit, self.zoom_in_btn,
            self.zoom_out_btn, self.fit_btn,
        ):
            widget.setEnabled(has)
        self.threshold.setEnabled(self.night_box.isChecked())
        self.ceiling.setEnabled(self.night_box.isChecked())            # NEW
        self.test_btn.setEnabled(self.night_box.isChecked())
        self.cover_clear.setEnabled(self.cover_path is not None)
        playing = self.player.is_playing()
        self.act_play.setText("Pause" if playing else "Play / Pause")
        self.play_btn.setText("Pause" if playing else "Play / Pause")
        self.seg_list.clear()
        for i, keep in enumerate(self.timeline.keeps, 1):
            item = QListWidgetItem(
                f"{i}.  {format_time(keep.start)}\n"
                f"     {format_time(keep.end)}   ({keep.length():.1f}s)"
            )
            item.setData(Qt.UserRole, (keep.start, keep.end))
            self.seg_list.addItem(item)
        self.update_status()

    def update_status(self):
        if self.recorder is not None:
            return
        clip = self.timeline.kept_duration()
        size = estimate_mb(clip, self.bitrate.currentData())
        ram = self.timeline.store.pyramid_bytes() if self.timeline.store else 0
        parts = [
            f"clip {format_time(clip)} of {format_time(self.timeline.duration())}",
            f"{len(self.timeline.keeps)} piece(s)",
            f"~{size:.1f} MB @ {self.bitrate.currentData()} kbps",
            f"RAM {ram / 1e6:.0f} MB",
            f"at {format_time(self.wave.playhead)}",
        ]
        if self.unsaved and self.timeline.duration() > 0:
            parts.append("\u25cf UNSAVED")
        self.statusBar().showMessage("   \u2502   ".join(parts))

    def tick(self):
        if self.recorder is not None:
            error = self.recorder.error()
            if error:
                QMessageBox.critical(self, "Recording stopped", error)
                self.stop_record()
                return
            elapsed = self.recorder.elapsed()
            # ---- paused state ----
            if self.recorder.paused:
                self.wave.set_live(
                    self.recorder.latest_mono(8.0),
                    f"PAUSED   {format_time(elapsed)}   (click Resume to continue)",
                )
                bk = f"   {len(self.bookmarks)} bookmark(s)" if self.bookmarks else ""
                self.statusBar().showMessage(
                    f"Paused at {format_time(elapsed)}{bk}"
                )
                return
            # ---- actively recording ----
            peak = self.recorder.peak()
            self.wave.set_live(
                self.recorder.latest_mono(8.0),
                f"RECORDING   {format_time(elapsed)}   (last 8 s)",
            )
            notes = []
            if peak < 1e-4 and elapsed > 3:
                notes.append("silence — wrong source?")
            dropped = glitch_count()
            if dropped:
                notes.append(f"{dropped} dropout(s)")
            if self.bookmarks:
                notes.append(f"{len(self.bookmarks)} bookmark(s)")
            tail = ("   \u2502   " + "   \u2502   ".join(notes)) if notes else ""
            self.statusBar().showMessage(
                f"Recording {format_time(elapsed)} to disk   \u2502   input peak "
                f"{20.0 * np.log10(max(peak, 1e-9)):5.1f} dBFS{tail}"
            )
            return
        # ---- playback / idle (unchanged) ----
        if self.player.is_playing() and self._plan is not None:
            if not self.wave.is_scrubbing() and self._seek_target is None:   # NEW guard
                if self.player.mode == "raw":
                    frame = getattr(self._plan, "raw_offset", 0) + self.player.out_frame()
                else:
                    frame = self._plan.source_frame(self.player.out_frame())
                self.wave.set_playhead(frame / float(self.timeline.samplerate()))
        elif self._was_playing:
            self.update_actions()
        self._was_playing = self.player.is_playing()

    def closeEvent(self, ev):
        if self.timeline.duration() > 0 and self.unsaved:
            if (
                QMessageBox.warning(
                    self,
                    "Exit without saving?",
                    "The current clip has NOT been exported to the computer and the "
                    "recording will be deleted.\n\n(Sending to the phone does not save "
                    "it here.)\n\nExit anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                != QMessageBox.Yes
            ):
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

        # ---- bookmarks -------------------------------------------------------

    def add_bookmark(self):
        """Drop a yellow marker at the current position."""
        if self.recorder is not None:
            t = self.recorder.elapsed()
        elif self.timeline.duration() > 0:
            t = self.wave.playhead
        else:
            return
        self.bookmarks.append(t)
        self.bookmarks.sort()
        self.wave.set_bookmarks(self.bookmarks)
        self.statusBar().showMessage(f"Bookmark at {format_time(t)}", 3000)

    def remove_nearest_bookmark(self):
        """Remove the bookmark closest to the playhead (within 2 s)."""
        if not self.bookmarks or self.timeline.duration() <= 0:
            return
        t = self.wave.playhead
        nearest = min(self.bookmarks, key=lambda b: abs(b - t))
        if abs(nearest - t) < max(2.0, self.wave.span() * 0.02):
            self.bookmarks.remove(nearest)
            self.wave.set_bookmarks(self.bookmarks)
            self.statusBar().showMessage(
                f"Removed bookmark at {format_time(nearest)}", 3000
            )

    def clear_bookmarks(self):
        """Remove all bookmarks."""
        self.bookmarks.clear()
        self.wave.set_bookmarks(self.bookmarks)
        self.statusBar().showMessage("All bookmarks cleared", 3000)

    def goto_prev_bookmark(self):
        """Jump the playhead to the previous bookmark."""
        if not self.bookmarks:
            return
        before = [b for b in self.bookmarks if b < self.wave.playhead - 0.05]
        if before:
            self.wave.goto(before[-1])

    def goto_next_bookmark(self):
        """Jump the playhead to the next bookmark."""
        if not self.bookmarks:
            return
        after = [b for b in self.bookmarks if b > self.wave.playhead + 0.05]
        if after:
            self.wave.goto(after[0])