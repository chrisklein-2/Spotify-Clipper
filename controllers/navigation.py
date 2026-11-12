from PySide6.QtCore import Qt
from editor import format_time, parse_time

from PySide6.QtWidgets import QListWidgetItem

class NavigationMixin:

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


    def on_piece_clicked(self, item):
        a, b = item.data(Qt.UserRole)
        self.wave.set_selection(a, b)
        self.wave.goto(a)

    def on_fade_changed(self, value):
        self.wave.set_fade_ms(value)
        self.invalidate()

    def refresh_pieces(self):
        self.seg_list.clear()
        for i, keep in enumerate(self.timeline.keeps, 1):
            text = (f"{i}.  {format_time(keep.start)}\n"
                    f"     {format_time(keep.end)}   ({keep.length():.1f}s)")
            if keep.fade_in is not None or keep.fade_out is not None:
                fi = "def" if keep.fade_in is None else f"{keep.fade_in:g}s"
                fo = "def" if keep.fade_out is None else f"{keep.fade_out:g}s"
                text += f"\n     fade {fi} / {fo}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, (keep.start, keep.end))
            self.seg_list.addItem(item)

    def on_piece_double_clicked(self, item):
        self.edit_piece_fades(self.seg_list.row(item))


    def on_end_fade_changed(self, value):
        self.wave.set_end_fade(value)
        self.invalidate()

    def on_block_selected(self, index):
        """Double-click on the waveform: open the pieces tab, highlight it."""
        if index >= 0:
            self.act_pieces.setChecked(True)      # opens the panel
            self.seg_list.setCurrentRow(index)
            item = self.seg_list.item(index)
            if item is not None:
                self.seg_list.scrollToItem(item)
        else:
            self.seg_list.clearSelection()        # a deleted gap has no row
        self.update_actions()