from PySide6.QtGui import QAction, QKeySequence

class ActionsMixin:
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
        self.act_piece_fades = QAction("Set fades for this piece...", self, shortcut="Ctrl+F")
        self.act_piece_fades.triggered.connect(lambda: self.edit_piece_fades())
        for a in (
            self.act_mark_in, self.act_mark_out, self.act_delete, self.act_restore,
            self.act_undo, self.act_redo, self.act_trim, self.act_reset, self.act_fit,
            self.act_zoomsel, self.act_selall, self.act_play, self.act_from_start,
            self.act_export, self.act_send, self.act_pieces, self.act_help, self.act_bookmark, self.act_rm_bookmark,
            self.act_clear_bookmarks, self.act_prev_bookmark,
            self.act_next_bookmark, self.act_finalize, self.act_piece_fades,
        ):
            self.addAction(a)