"""
editor/timeline.py - the edit model.

Editing never touches samples. It is a list of "keep" ranges over the
AudioStore, so every operation is O(number of pieces) and undo is a list copy.
plan() turns the keeps into Pieces; ClipStreamer (streamer.py) renders them.
"""

from dataclasses import dataclass
from typing import Optional

from .fades import cap_fades

MIN_KEEP = 0.01
UNDO_LIMIT = 400
AUTO_TRIM_DB = -45.0
EDGE_EPS = 1e-4      # "at the very start / end of the recording", in seconds

# A half-open range of the recording, in seconds, that survives into the
# clip. fade_in / fade_out are seconds; None means the global default.
@dataclass
class Keep:
    start: float
    end: float
    fade_in: Optional[float] = None
    fade_out: Optional[float] = None

    def length(self):
        return max(0.0, self.end - self.start)

    def copy(self):
        return Keep(self.start, self.end, self.fade_in, self.fade_out)


# One kept piece in frames: where it lands in the output, where to read it
# from, how long it is, and the frames to ramp at each end.
@dataclass
class Piece:
    out_start: int
    src_start: int
    frames: int
    fade_in: int = 0
    fade_out: int = 0

    def out_end(self):
        return self.out_start + self.frames


# Holds the store, the kept ranges and the undo stacks.
class Timeline:

    def __init__(self):
        self.store = None
        self.keeps = []
        self._undo = []
        self._redo = []

    # Attach a store and reset history. `keeps` (optional) pre-seeds the pieces.
    def set_store(self, store, keeps=None):
        if self.store is not None and self.store is not store:
            self.store.close()
        self.store = store
        self._undo.clear()
        self._redo.clear()
        if keeps:
            self._tidy(keeps)
        elif self.duration() > 0:
            self.keeps = [Keep(0.0, self.duration())]
        else:
            self.keeps = []

    def samplerate(self):
        return self.store.samplerate if self.store else 44100

    def channels(self):
        return self.store.channels if self.store else 2

    def frames(self):
        return self.store.frames() if self.store else 0

    def duration(self):
        return self.store.duration() if self.store else 0.0

    def kept_duration(self):
        return sum(k.length() for k in self.keeps)

    def clamp(self, t):
        return min(max(0.0, float(t)), self.duration())

    # The gaps between keeps, i.e. the deleted ranges.
    def deleted_ranges(self):
        gaps, cursor = [], 0.0
        for keep in self.keeps:
            if keep.start - cursor > 1e-6:
                gaps.append((cursor, keep.start))
            cursor = keep.end
        if self.duration() - cursor > 1e-6:
            gaps.append((cursor, self.duration()))
        return gaps

    # (start, end, keep_index) for the kept piece at t, or
    # (start, end, None) for the deleted gap at t; None if out of range.
    def block_at(self, t):
        t = self.clamp(t)
        for i, keep in enumerate(self.keeps):
            if keep.start <= t <= keep.end:
                return keep.start, keep.end, i
        for a, b in self.deleted_ranges():
            if a <= t <= b:
                return a, b, None
        return None

    # Index of the kept piece containing t, or None.
    def keep_index_at(self, t):
        for i, keep in enumerate(self.keeps):
            if keep.start - 1e-6 <= t <= keep.end + 1e-6:
                return i
        return None

    # ---- history ---------------------------------------------------------

    def _push(self):
        self._undo.append([k.copy() for k in self.keeps])
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            return False
        self._redo.append([k.copy() for k in self.keeps])
        self.keeps = self._undo.pop()
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append([k.copy() for k in self.keeps])
        self.keeps = self._redo.pop()
        return True

    # ---- editing ---------------------------------------------------------

    # Drop tiny keeps, merge touching ones (first fade-in, last fade-out win).
    def _tidy(self, keeps):
        keeps = sorted((k for k in keeps if k.length() >= MIN_KEEP),
                       key=lambda k: k.start)
        merged = []
        for keep in keeps:
            if merged and keep.start <= merged[-1].end + 1e-4:
                if keep.end > merged[-1].end:
                    merged[-1].end = keep.end
                    merged[-1].fade_out = keep.fade_out
            else:
                merged.append(keep)
        self.keeps = merged

    # Subtract a range without touching undo. New cut edges get default fades.
    def _delete_raw(self, a, b):
        out = []
        for keep in self.keeps:
            if b <= keep.start or a >= keep.end:
                out.append(keep)
                continue
            if a > keep.start:
                out.append(Keep(keep.start, a, keep.fade_in, None))
            if b < keep.end:
                out.append(Keep(b, keep.end, None, keep.fade_out))
        self._tidy(out)

    def delete_range(self, a, b):
        a, b = sorted((self.clamp(a), self.clamp(b)))
        if b - a < MIN_KEEP:
            return False
        self._push()
        self._delete_raw(a, b)
        return True

    def restore_range(self, a, b):
        a, b = sorted((self.clamp(a), self.clamp(b)))
        if b - a < MIN_KEEP:
            return False
        self._push()
        self._tidy(self.keeps + [Keep(a, b)])
        return True

    def reset(self):
        if self.duration() <= 0:
            return False
        self._push()
        self.keeps = [Keep(0.0, self.duration())]
        return True

    # Delete near-silent head and tail; returns seconds removed.
    def auto_trim_silence(self, threshold_db=AUTO_TRIM_DB, pad_ms=40.0):
        if not self.store or self.frames() == 0:
            return 0.0
        first, last = self.store.loud_bounds(threshold_db)
        sr = self.samplerate()
        pad = pad_ms / 1000.0
        head = max(0.0, first / sr - pad)
        tail = min(self.duration(), last / sr + pad)
        if head < MIN_KEEP and self.duration() - tail < MIN_KEEP:
            return 0.0
        before = self.kept_duration()
        self._push()
        self._delete_raw(0.0, head)
        self._delete_raw(tail, self.duration())
        return before - self.kept_duration()

    # Seconds, or None for the default. Returns True if anything changed.
    def set_piece_fades(self, index, fade_in, fade_out):
        if not 0 <= index < len(self.keeps):
            return False
        keep = self.keeps[index]
        if keep.fade_in == fade_in and keep.fade_out == fade_out:
            return False
        self._push()
        keep.fade_in, keep.fade_out = fade_in, fade_out
        return True

    # (fade_in, fade_out) in seconds for one piece. The true start and end of
    # the recording get no default fade; a fade set on the piece is always used.
    def effective_fades(self, keep, default_s):
        fade_in, fade_out = keep.fade_in, keep.fade_out
        if fade_in is None:
            fade_in = 0.0 if keep.start <= EDGE_EPS else default_s
        if fade_out is None:
            fade_out = 0.0 if keep.end >= self.duration() - EDGE_EPS else default_s
        return fade_in, fade_out

    # Turn the keeps into Pieces: the recipe the streamer follows.
    def plan(self, fade_ms=500.0):
        sr = self.samplerate()
        default = max(0.0, fade_ms / 1000.0)
        pieces, pos = [], 0
        for keep in self.keeps:
            a = max(0, int(keep.start * sr))
            b = min(self.frames(), int(keep.end * sr))
            n = b - a
            if n < 2:
                continue
            fi, fo = self.effective_fades(keep, default)
            fi, fo = cap_fades(int(fi * sr), int(fo * sr), n)
            pieces.append(Piece(pos, a, n, int(fi), int(fo)))
            pos += n
        return pieces