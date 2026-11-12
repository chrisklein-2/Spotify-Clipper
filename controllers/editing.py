"""
core/editing.py - EditingMixin: delete, restore, undo, redo, trim, reset.

"""

from editor import format_time
from editor.timeline import AUTO_TRIM_DB
from PySide6.QtWidgets import QDialog
from ui.dialogs import PieceFadeDialog

class EditingMixin:

    def delete_selection(self):
        sel = self.wave.selection()
        if sel and self.timeline.delete_range(*sel):
            self.wave.clear_selection()
            self.after_edit(f"Deleted {format_time(sel[1] - sel[0])}")

    def restore_selection(self):
        sel = self.wave.selection()
        if sel and self.timeline.restore_range(*sel):
            self.after_edit("Restored selection")

    def auto_trim(self):
            removed = self.timeline.auto_trim_silence()
            if removed > 0.01:
                self.after_edit(f"Auto-trim removed {removed:.2f}s of silence")
            else:
                self.statusBar().showMessage(
                    f"Auto-trim: no silence found (threshold {AUTO_TRIM_DB:.0f} dB)", 5000)

    def reset_edits(self):
        if self.timeline.reset():
            self.after_edit("All edits reset")

    def do_undo(self):
        if self.timeline.undo():
            self.after_edit("Undo")

    def do_redo(self):
        if self.timeline.redo():
            self.after_edit("Redo")

    def after_edit(self, message):
        self.stop_playback()
        self.invalidate()
        self.wave.update()
        self.statusBar().showMessage(message, 4000)

    def edit_piece_fades(self, index=None):
        tl = self.timeline
        if not tl.keeps:
            return
        if index is None:
            index = tl.keep_index_at(self.wave.playhead)
        if index is None:
            self.statusBar().showMessage(
                "Put the playhead inside a kept piece, or double-click one "
                "in the pieces list.", 5000)
            return
        dlg = PieceFadeDialog(tl.keeps[index], self.cut_fade.value() / 1000.0,
                              index, self)
        if dlg.exec() != QDialog.Accepted:
            return
        fade_in, fade_out = dlg.values()
        if tl.set_piece_fades(index, fade_in, fade_out):
            self.after_edit(f"Piece {index + 1}: fades updated")