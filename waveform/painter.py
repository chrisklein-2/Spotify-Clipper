"""
waveform/painter.py - all drawing for WaveformView.

Every function takes the view and a QPainter. Painting reads the view's
state but never changes it, except asking the view to refresh its peak
cache, so this file stays a pure consumer of view.py.
"""

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF

from editor import format_time
from editor.fades import cap_fades
from theme import (COL_BG, COL_DEL_BG, COL_FADE, COL_MARK, COL_PLAYHEAD,
                   COL_RULER, COL_RULER_LINE, COL_SEL, COL_SEL_EDGE, COL_TEXT,
                   COL_TEXT_BRIGHT, COL_WAVE_DEL, COL_WAVE_KEEP,
                   COL_WAVE_KEEP_SOFT)

RULER_H = 22
MIN_WEDGE_PX = 4.0           # narrowest a fade is drawn, so it shows fully zoomed out
FILL_MIN_PX = 14.0           # narrower than this, the translucent fill is dropped
FULL_WEDGE_PX = 24.0         # this wide or wider, the lines are full thickness
NICE_STEPS = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600,
              1800, 3600]


# Pick a readable tick interval for the ruler at this zoom.
def pick_tick_step(span, width):
    target = max(1, width // 95)
    for step in NICE_STEPS:
        if span / step <= target:
            return step
    return NICE_STEPS[-1]


# Per-pixel min/max envelope of a flat mono array (live view only).
def live_peaks(mono, width):
    if width < 1 or len(mono) < 2:
        return None
    edges = np.linspace(0, len(mono), width + 1).astype(np.int64)
    mins = np.zeros(width, dtype=np.float32)
    maxs = np.zeros(width, dtype=np.float32)
    for i in range(width):
        a, b = edges[i], max(edges[i] + 1, edges[i + 1])
        chunk = mono[a:min(b, len(mono))]
        if chunk.size:
            mins[i], maxs[i] = chunk.min(), chunk.max()
    return mins, maxs

# Per-pixel min/max from a bucket overview (the whole-recording live view).
def env_peaks(mins, maxs, width):
    n = len(mins)
    if width < 1 or n < 1:
        return None
    if n <= width:
        idx = (np.arange(width) * n / float(width)).astype(np.int64)
        return mins[idx], maxs[idx]
    starts = np.linspace(0, n, width + 1).astype(np.int64)[:-1]
    return np.minimum.reduceat(mins, starts), np.maximum.reduceat(maxs, starts)

# Boolean mask: which pixel columns are inside kept audio.
def keep_mask(view, width):
    mask = np.zeros(width, dtype=bool)
    if not view.timeline:
        return mask
    for keep in view.timeline.keeps:
        x1 = int(np.floor(view.t2x(keep.start)))
        x2 = int(np.ceil(view.t2x(keep.end)))
        mask[max(0, x1):min(width, max(0, x2))] = True
    return mask


# Paint everything: ruler, waveform, deleted zones, fades, selection,
# markers, playhead. Called from WaveformView.paintEvent.
def paint(view, p):
    w, h = view.width(), view.height()
    bt, bh = RULER_H, h - RULER_H
    mid = bt + bh / 2.0
    p.fillRect(view.rect(), COL_BG)
    p.fillRect(0, 0, w, RULER_H, COL_RULER)
    p.setPen(QPen(COL_RULER_LINE, 1))
    p.drawLine(0, RULER_H - 1, w, RULER_H - 1)

    if view.live_mono is not None:
        _paint_live(view, p, w, bt, bh, mid)
        return
    if not view.timeline or view.duration() <= 0:
        p.setPen(COL_TEXT)
        p.drawText(view.rect(), Qt.AlignCenter,
                   "Press Record and play something,\n"
                   "or load an audio file.    (F1 = help)")
        return

    view.ensure_peaks(w)
    for a, b in view.timeline.deleted_ranges():
        x1, x2 = view.t2x(a), view.t2x(b)
        p.fillRect(QRectF(x1, bt, max(1.0, x2 - x1), bh), COL_DEL_BG)

    scale = bh / 2.0 - 6
    if view.peaks is not None:
        mins, maxs = view.peaks
        mask = keep_mask(view, w)
        pk, pd = QPen(COL_WAVE_KEEP, 1), QPen(COL_WAVE_DEL, 1)
        for x in range(w):
            p.setPen(pk if mask[x] else pd)
            p.drawLine(x, int(mid - maxs[x] * scale), x, int(mid - mins[x] * scale))
        p.setPen(QPen(COL_WAVE_KEEP_SOFT, 1))
        for keep in view.timeline.keeps:
            p.drawLine(int(view.t2x(keep.start)), int(mid),
                       int(view.t2x(keep.end)), int(mid))
    p.setPen(QPen(COL_WAVE_DEL, 1, Qt.DashLine))
    for a, b in view.timeline.deleted_ranges():
        p.drawLine(int(view.t2x(a)), int(mid), int(view.t2x(b)), int(mid))

    _paint_fades(view, p, mid, scale)
    _paint_selection(view, p, bt, h)
    _paint_ruler(view, p, w)
    _paint_bookmarks(view, p)
    px = view.t2x(view.playhead)
    p.setPen(QPen(COL_PLAYHEAD, 1))
    p.drawLine(int(px), 0, int(px), h)


# Shade the selection and flag its two marker edges.
def _paint_selection(view, p, bt, h):
    sel = view.selection()
    if sel:
        x1, x2 = view.t2x(sel[0]), view.t2x(sel[1])
        p.fillRect(QRectF(x1, bt, x2 - x1, h - bt), QBrush(COL_SEL))
        p.setPen(QPen(COL_SEL_EDGE, 2))
        p.drawLine(int(x1), bt, int(x1), h)
        p.drawLine(int(x2), bt, int(x2), h)
        p.setPen(COL_SEL_EDGE)
        p.drawText(int(min(x1, x2)) + 6, bt + 32,
                   f"{format_time(sel[1] - sel[0])} selected")
    for value, label, right in ((view.sel_a, "[", False), (view.sel_b, "]", True)):
        if value is None:
            continue
        _paint_flag(view, p, view.t2x(value), bt, label, right)


# Draw one marker flag: a small tag hanging off the top of the body.
def _paint_flag(view, p, x, bt, label, right):
    width, height = 13.0, 15.0
    sign = -1.0 if right else 1.0
    poly = QPolygonF([QPointF(x, bt), QPointF(x + sign * width, bt),
                      QPointF(x + sign * width, bt + height - 5),
                      QPointF(x, bt + height)])
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(COL_MARK))
    p.drawPolygon(poly)
    p.setPen(QPen(COL_MARK, 1))
    p.drawLine(int(x), bt, int(x), view.height())
    font = QFont(p.font())
    font.setBold(True)
    font.setPointSize(8)
    p.setFont(font)
    p.setPen(QColor("#1a1400"))
    p.drawText(QRectF(x + (0 if not right else -width), bt, width, height - 3),
               Qt.AlignCenter, label)


# One wedge: the part of the waveform body that the gain ramp takes away,
# between x=xa (gain ga) and x=xb (gain gb), both 0..1. The line gets thinner
# as the wedge shrinks, and the translucent fill disappears below FILL_MIN_PX.
def _lost_area(p, xa, ga, xb, gb, mid, top, bot):
    size = abs(xb - xa)
    k = min(1.0, max(0.0, (size - MIN_WEDGE_PX) / (FULL_WEDGE_PX - MIN_WEDGE_PX)))
    pen_w = 1.0 + k
    fill = None
    if size >= FILL_MIN_PX:
        fill = QColor(COL_FADE)
        fill.setAlpha(50)
    for edge in (top, bot):
        ya = mid + (edge - mid) * ga
        yb = mid + (edge - mid) * gb
        if fill is not None:
            poly = QPolygonF([QPointF(xa, ya), QPointF(xa, edge),
                              QPointF(xb, edge), QPointF(xb, yb)])
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(fill))
            p.drawPolygon(poly)
            p.setBrush(Qt.NoBrush)
        p.setPen(QPen(COL_FADE, pen_w))
        p.drawLine(QPointF(xa, ya), QPointF(xb, yb))


# Draw the fade in / fade out of every kept piece, plus the end fade.
# The last piece shows ONE out-wedge: whichever of its own fade and the
# end fade is longer, because that is what the audio does.
def _paint_fades(view, p, mid, scale):
    tl = view.timeline
    if not tl or not tl.keeps or view.span() <= 0:
        return
    px_per_s = view.width() / view.span()
    default = view.fade_ms / 1000.0
    top, bot = mid - scale, mid + scale
    keeps = tl.keeps
    last = len(keeps) - 1
    end_s = min(getattr(view, "end_fade_s", 0.0), tl.kept_duration())

    end_wins = False
    for i, keep in enumerate(keeps):
        x1, x2 = view.t2x(keep.start), view.t2x(keep.end)
        fin, fout = tl.effective_fades(keep, default)
        fin, fout = cap_fades(fin, fout, keep.length())
        if i == last and end_s > fout:
            end_wins = True
            fout = 0.0
        if x2 < -20 or x1 > view.width() + 20:
            continue
        half = (x2 - x1) / 2.0
        if fin > 0:
            f = min(max(fin * px_per_s, MIN_WEDGE_PX), half)
            if f >= 1.0:
                _lost_area(p, x1, 0.0, x1 + f, 1.0, mid, top, bot)
        if fout > 0:
            f = min(max(fout * px_per_s, MIN_WEDGE_PX), half)
            if f >= 1.0:
                _lost_area(p, x2 - f, 1.0, x2, 0.0, mid, top, bot)

    if not end_wins or end_s <= 0:
        return
    if end_s * px_per_s < MIN_WEDGE_PX:
        xe = view.t2x(keeps[-1].end)
        width = xe - view.t2x(keeps[-1].start)
        xs = xe - min(MIN_WEDGE_PX, max(1.0, width))
        _lost_area(p, xs, 1.0, xe, 0.0, mid, top, bot)
        return
    acc = 0.0                            # output seconds already covered
    for keep in reversed(keeps):
        if acc >= end_s:
            break
        use = min(end_s - acc, keep.length())
        g_end, g_start = acc / end_s, (acc + use) / end_s
        xe, xs = view.t2x(keep.end), view.t2x(keep.end - use)
        _lost_area(p, xs, g_start, xe, g_end, mid, top, bot)
        acc += use
        
# Draw ruler tick marks and time labels.
def _paint_ruler(view, p, w):
    step = pick_tick_step(view.span(), w)
    font = QFont(p.font())
    font.setPointSize(8)
    font.setBold(False)
    p.setFont(font)
    p.setPen(COL_TEXT)
    t = np.ceil(view.view_start / step) * step
    while t <= view.view_end:
        x = int(view.t2x(t))
        p.drawLine(x, RULER_H - 6, x, RULER_H - 1)
        p.drawText(x + 3, RULER_H - 8, format_time(t))
        t += step


# Draw the live view while recording, with bookmark markers.
def _paint_live(view, p, w, bt, bh, mid):
    if view.live_env is not None:
        peaks = env_peaks(view.live_env[0], view.live_env[1], w)
    else:
        peaks = live_peaks(view.live_mono, w)
    if peaks is not None:
        mins, maxs = peaks
        scale = bh / 2.0 - 6
        p.setPen(QPen(QColor("#e05c5c"), 1))
        for x in range(w):
            p.drawLine(x, int(mid - maxs[x] * scale), x, int(mid - mins[x] * scale))
    if view.live_marks:
        r = 3
        y_dot = RULER_H - r - 2
        p.setPen(QPen(COL_MARK, 1))
        p.setBrush(QBrush(COL_MARK))
        for frac in view.live_marks:
            x = int(frac * w)
            p.drawEllipse(x - r, y_dot - r, r * 2, r * 2)
            p.drawLine(x, RULER_H, x, view.height())
        p.setBrush(Qt.NoBrush)
    p.setPen(COL_TEXT_BRIGHT)
    p.drawText(10, RULER_H - 7, view.live_label)


# Small yellow dots on the ruler for bookmarked spots.
def _paint_bookmarks(view, p):
    if not view.bookmarks:
        return
    p.setPen(QPen(COL_MARK, 1))
    p.setBrush(QBrush(COL_MARK))
    r = 3
    y_dot = RULER_H - r - 2
    for t in view.bookmarks:
        x = int(view.t2x(t))
        if -r <= x <= view.width() + r:
            p.drawEllipse(x - r, y_dot - r, r * 2, r * 2)
            p.drawLine(x, RULER_H, x, RULER_H + 8)
    p.setBrush(Qt.NoBrush)