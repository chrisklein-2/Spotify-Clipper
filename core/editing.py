"""
app_editing.py - EditingMixin: delete, restore, undo, redo, trim, reset.

Mixed into MainWindow.
"""

from editor import format_time


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
                "Auto-trim: no silence found (threshold -45 dB)", 5000
            )

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