"""
waveform/view.py - WaveformView: state, navigation and input.

All drawing lives in painter.py. This file owns what gets drawn: the zoom
window, the selection and markers, the playhead, and the cached pixel peaks.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QMenu, QSizePolicy, QWidget

from . import painter
from .painter import RULER_H

EDGE_PX = 6
MIN_SPAN = 0.02


class WaveformView(QWidget):
    selectionChanged = Signal()
    playheadMoved = Signal(float)
    viewChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.timeline = None
        self.live_mono = None
        self.live_label = ""
        self.fade_ms = 500.0
        self.end_fade_s = 0.0 
        self.playhead = 0.0
        self.sel_a = self.sel_b = None
        self.view_start = 0.0
        self.view_end = 1.0
        self.context_actions = []
        self._drag = None
        self._pan = None
        self.peaks = None
        self._peaks_key = None
        self.bookmarks = []

    # ---- model / mode ----------------------------------------------------

    def set_bookmarks(self, bookmarks):
        """Accept a list of source-time bookmarks to display on the ruler."""
        self.bookmarks = list(bookmarks)
        self.update()

    def set_timeline(self, timeline):
        self.timeline = timeline
        self.live_mono = None
        self.sel_a = self.sel_b = None
        self.playhead = 0.0
        self._peaks_key = None
        self.zoom_fit()
        self.selectionChanged.emit()

    def set_fade_ms(self, value):
        self.fade_ms = float(value)
        self.update()

    def set_end_fade(self, seconds):
        self.end_fade_s = float(seconds)
        self.update()
        
    def set_live(self, mono, label=""):
        self.live_mono = mono
        self.live_label = label
        self.update()

    def clear_live(self):
        self.live_mono = None
        self.update()

    def duration(self):
        return self.timeline.duration() if self.timeline else 0.0

    # ---- view window -----------------------------------------------------

    def span(self):
        return max(MIN_SPAN, self.view_end - self.view_start)

    def _commit_view(self, start, span):
        total = max(MIN_SPAN, self.duration())
        span = min(total, max(MIN_SPAN, span))
        start = max(0.0, min(start, total - span))
        self.view_start, self.view_end = start, start + span
        self._peaks_key = None
        self.viewChanged.emit()
        self.update()

    def zoom_fit(self):
        self._commit_view(0.0, max(MIN_SPAN, self.duration()))

    def zoom_selection(self):
        sel = self.selection()
        if not sel:
            return
        pad = max(0.02, (sel[1] - sel[0]) * 0.1)
        self._commit_view(sel[0] - pad, (sel[1] - sel[0]) + pad * 2)

    def zoom_at(self, focus, factor):
        if self.duration() <= 0:
            return
        span = self.span()
        frac = (focus - self.view_start) / span if span > 0 else 0.5
        frac = min(max(frac, 0.0), 1.0)
        new_span = min(max(span * factor, MIN_SPAN), max(MIN_SPAN, self.duration()))
        self._commit_view(focus - frac * new_span, new_span)

    def zoom_anchor(self):
        if self.view_start <= self.playhead <= self.view_end:
            return self.playhead
        return self.view_start + self.span() / 2.0

    def zoom_in(self):
        self.zoom_at(self.zoom_anchor(), 0.5)

    def zoom_out(self):
        self.zoom_at(self.zoom_anchor(), 2.0)

    def scroll_to(self, start):
        self._commit_view(start, self.span())

    def centre_on(self, t):
        self._commit_view(t - self.span() / 2.0, self.span())

    def t2x(self, t):
        return (t - self.view_start) / self.span() * self.width()

    def x2t(self, x):
        return self.view_start + (x / max(1, self.width())) * self.span()

    def clamp(self, t):
        return min(max(0.0, t), self.duration())

    # ---- selection / markers / playhead -----------------------------------

    def selection(self):
        if self.sel_a is None or self.sel_b is None:
            return None
        a, b = sorted((self.sel_a, self.sel_b))
        return None if b - a < 0.005 else (a, b)

    def clear_selection(self):
        self.sel_a = self.sel_b = None
        self.selectionChanged.emit()
        self.update()

    def select_all(self):
        if self.duration() > 0:
            self.sel_a, self.sel_b = 0.0, self.duration()
            self.selectionChanged.emit()
            self.update()

    def set_selection(self, a, b):
        self.sel_a, self.sel_b = self.clamp(a), self.clamp(b)
        self.selectionChanged.emit()
        self.update()

    def mark_in(self):
        if self.duration() <= 0:
            return
        self.sel_a = self.playhead
        if self.sel_b is None:
            self.sel_b = self.playhead
        self.selectionChanged.emit()
        self.update()

    def mark_out(self):
        if self.duration() <= 0:
            return
        self.sel_b = self.playhead
        if self.sel_a is None:
            self.sel_a = self.playhead
        self.selectionChanged.emit()
        self.update()

    def set_playhead(self, t):
        self.playhead = self.clamp(t)
        self.update()

    def goto(self, t):
        self.set_playhead(t)
        if not (self.view_start <= self.playhead <= self.view_end):
            self.centre_on(self.playhead)
        self.playheadMoved.emit(self.playhead)

    # ---- input -------------------------------------------------------------

    def mousePressEvent(self, ev):
        if self.duration() <= 0 or self.live_mono is not None:
            return
        x, y = ev.position().x(), ev.position().y()
        if ev.button() == Qt.MiddleButton:
            self._pan = (x, self.view_start)
            return
        if ev.button() != Qt.LeftButton:
            return
        if y < RULER_H:
            self._drag = "playhead"
            self.set_playhead(self.x2t(x))
            self.playheadMoved.emit(self.playhead)
            return
        sel = self.selection()
        if sel:
            if abs(x - self.t2x(sel[0])) <= EDGE_PX:
                self.sel_a, self.sel_b = sel[1], sel[0]
                self._drag = "edge"
                return
            if abs(x - self.t2x(sel[1])) <= EDGE_PX:
                self.sel_a, self.sel_b = sel[0], sel[1]
                self._drag = "edge"
                return
        self.sel_a = self.sel_b = self.clamp(self.x2t(x))
        self._drag = "edge"
        self.set_playhead(self.sel_a)
        self.playheadMoved.emit(self.playhead)
        self.selectionChanged.emit()

    def mouseMoveEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        if self._pan is not None:
            x0, s0 = self._pan
            shift = (x0 - x) / max(1, self.width()) * self.span()
            self._commit_view(s0 + shift, self.span())
            return
        if self._drag == "playhead":
            self.set_playhead(self.x2t(x))
            self.playheadMoved.emit(self.playhead)
            return
        if self._drag == "edge":
            self.sel_b = self.clamp(self.x2t(x))
            self.selectionChanged.emit()
            self.update()
            return
        sel = self.selection()
        near = sel and (abs(x - self.t2x(sel[0])) <= EDGE_PX or
                        abs(x - self.t2x(sel[1])) <= EDGE_PX)
        if y < RULER_H:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.SizeHorCursor if near else Qt.IBeamCursor)

    def mouseReleaseEvent(self, ev):
        if self._drag == "edge" and self.selection() is None:
            self.sel_a = self.sel_b = None
            self.selectionChanged.emit()
        self._drag = None
        self._pan = None
        self.update()

    def mouseDoubleClickEvent(self, ev):
        self.select_all()

    def wheelEvent(self, ev):
        if self.duration() <= 0:
            return
        delta = ev.angleDelta().y()
        if ev.modifiers() & Qt.ShiftModifier:
            self._commit_view(self.view_start - delta / 120.0 * self.span() * 0.15,
                              self.span())
        else:
            self.zoom_at(self.x2t(ev.position().x()), 0.8 if delta > 0 else 1.25)

    def keyPressEvent(self, ev):
        if self.duration() <= 0:
            super().keyPressEvent(ev)
            return
        key = ev.key()
        if key == Qt.Key_Home:
            self.goto(0.0)
        elif key == Qt.Key_End:
            self.goto(self.duration())
        elif key == Qt.Key_PageUp:
            self._commit_view(self.view_start - self.span() * 0.9, self.span())
        elif key == Qt.Key_PageDown:
            self._commit_view(self.view_start + self.span() * 0.9, self.span())
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
        elif key == Qt.Key_Minus:
            self.zoom_out()
        else:
            super().keyPressEvent(ev)

    def contextMenuEvent(self, ev):
        if not self.context_actions:
            return
        menu = QMenu(self)
        for action in self.context_actions:
            menu.addSeparator() if action is None else menu.addAction(action)
        menu.exec(ev.globalPos())

    # True while the user is dragging the playhead on the ruler.
    def is_scrubbing(self):
        return self._drag == "playhead"

    # ---- peak cache / painting ----------------------------------------------

    def ensure_peaks(self, width):
        """Fetch the pixel envelope from the pyramid, cached per view/size."""
        store = self.timeline.store if self.timeline else None
        if store is None:
            self.peaks = None
            return
        key = (width, round(self.view_start, 5), round(self.view_end, 5),
               store.frames())
        if key == self._peaks_key:
            return
        sr = store.samplerate
        self.peaks = store.peaks(self.view_start * sr, self.view_end * sr, width)
        self._peaks_key = key

    def paintEvent(self, ev):
        p = QPainter(self)
        try:
            painter.paint(self, p)
        finally:
            p.end()