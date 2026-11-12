from .dialogs import HelpDialog
from utils import reveal_folder

class MenuMixin:    
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
        em.addAction(self.act_piece_fades)
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

    def show_help(self):
        HelpDialog(self).exec()
