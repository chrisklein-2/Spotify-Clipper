from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, 
    QPushButton, QScrollBar, QSizePolicy, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt
from waveform import WaveformView
from .widgets import sep, abtn
from audio_backends import SAMPLE_RATES


class PanelsMixin:
    
    # ---- UI build -------------------------------------------------------

    def _build_top_row(self):
        self.rec_btn = QPushButton("Record")
        self.rec_btn.setObjectName("record")
        self.rec_btn.setCheckable(True)
        self.rec_btn.setMinimumWidth(115)
        self.rec_btn.clicked.connect(self.toggle_record)
        self.stop_rec_btn = QPushButton("Stop rec")                       
        self.stop_rec_btn.setMinimumWidth(80)                             
        self.stop_rec_btn.setEnabled(False)                                
        self.stop_rec_btn.setToolTip("Finish recording and load for editing")
        self.stop_rec_btn.clicked.connect(self.stop_record)   
        self.mark_btn = QPushButton("Mark")
        self.mark_btn.setMinimumWidth(60)
        self.mark_btn.setEnabled(False)
        self.mark_btn.setToolTip(
            "Drop a bookmark at the current recording time   [Ctrl+B]")
        self.mark_btn.clicked.connect(self.add_bookmark)  
        self.live_zoom_btn = QPushButton("View: whole")
        self.live_zoom_btn.setMinimumWidth(100)
        self.live_zoom_btn.setCheckable(True)
        self.live_zoom_btn.setChecked(True)
        self.live_zoom_btn.setEnabled(False)
        self.live_zoom_btn.setToolTip(
            "While recording: show the whole recording so far, or only the last 8 s")
        self.live_zoom_btn.toggled.connect(
            lambda on: self.live_zoom_btn.setText(
                "View: whole" if on else "View: last 8 s"))           
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
        row.addWidget(self.stop_rec_btn)                                   
        row.addWidget(self.mark_btn)
        row.addWidget(self.live_zoom_btn)
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
        self.wave.blockSelected.connect(self.on_block_selected)
        self.wave.context_actions = [
            self.act_mark_in, self.act_mark_out, None,
            self.act_delete, self.act_restore, None,
            self.act_selall, self.act_zoomsel, self.act_fit,
            None, self.act_undo, self.act_redo, self.act_piece_fades ,None,                                
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
        self.seg_list.setToolTip("Click to jump, double-click to set this piece's fades.")
        self.seg_list.itemClicked.connect(self.on_piece_clicked)
        self.seg_list.itemDoubleClicked.connect(self.on_piece_double_clicked)
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
