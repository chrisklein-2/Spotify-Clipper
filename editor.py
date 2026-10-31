"""
editor.py - the edit model.

Editing never touches samples. It is a list of "keep" ranges over the AudioStore, so
every operation is O(number of pieces) - instant even on a 2 hour recording - and undo
is just a list copy.

plan() turns the keeps into a list of Pieces describing what the output looks like.
ClipStreamer then produces that output block by block on demand, so neither playback
nor export ever builds the whole clip in memory.
"""

import bisect
from dataclasses import dataclass

import numpy as np

MIN_KEEP = 0.01
UNDO_LIMIT = 400


# Format seconds as m:ss.hh, or h:mm:ss for long recordings.
def format_time(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    rest = seconds - hours * 3600 - minutes * 60
    if hours:
        return f"{hours}:{minutes:02d}:{rest:05.2f}"
    return f"{minutes}:{rest:05.2f}"



# A half-open range of the recording, in seconds, that survives into the clip.
@dataclass
class Keep:
    start: float
    end: float

    # Length in seconds.
    def length(self):
        return max(0.0, self.end - self.start)



# One kept piece expressed in frames, with its own fade length. This is
# all the streamer needs: where it lands in the output, where to read it
# from, how long it is, and how many frames to ramp at each end.
@dataclass
class Piece:
    out_start: int
    src_start: int
    frames: int
    fade: int

    # First output frame after this piece.
    def out_end(self):
        return self.out_start + self.frames



# Holds the store, the kept ranges and the undo stacks. The GUI only
# calls these methods; they are all cheap because no audio is touched.
class Timeline:

    # Create an empty timeline.
    def __init__(self):
        self.store = None
        self.keeps = []
        self._undo = []
        self._redo = []

    # Attach a store and reset all edits and history.
    def set_store(self, store):
        if self.store is not None and self.store is not store:
            self.store.close()
        self.store = store
        self.keeps = [Keep(0.0, self.duration())] if self.duration() > 0 else []
        self._undo.clear()
        self._redo.clear()

    # Sample rate of the recording.
    def samplerate(self):
        return self.store.samplerate if self.store else 44100

    # Channel count of the recording.
    def channels(self):
        return self.store.channels if self.store else 2

    # Total frames of the recording.
    def frames(self):
        return self.store.frames() if self.store else 0

    # Length of the whole recording in seconds.
    def duration(self):
        return self.store.duration() if self.store else 0.0

    # Total length of all kept ranges.
    def kept_duration(self):
        return sum(k.length() for k in self.keeps)

    # Clamp a time into the recording.
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

    # Save keeps onto the undo stack.
    def _push(self):
        self._undo.append([Keep(k.start, k.end) for k in self.keeps])
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()

    # Drop tiny keeps, merge touching ones.
    def _tidy(self, keeps):
        keeps = sorted((k for k in keeps if k.length() >= MIN_KEEP), key=lambda k: k.start)
        merged = []
        for keep in keeps:
            if merged and keep.start <= merged[-1].end + 1e-4:
                merged[-1].end = max(merged[-1].end, keep.end)
            else:
                merged.append(keep)
        self.keeps = merged

    # Subtract a range without touching undo.
    def _delete_raw(self, a, b):
        out = []
        for keep in self.keeps:
            if b <= keep.start or a >= keep.end:
                out.append(keep)
                continue
            if a > keep.start:
                out.append(Keep(keep.start, a))
            if b < keep.end:
                out.append(Keep(b, keep.end))
        self._tidy(out)

    # True if undo is available.
    def can_undo(self):
        return bool(self._undo)

    # True if redo is available.
    def can_redo(self):
        return bool(self._redo)

    # Step one edit backwards.
    def undo(self):
        if not self._undo:
            return False
        self._redo.append([Keep(k.start, k.end) for k in self.keeps])
        self.keeps = self._undo.pop()
        return True

    # Step one edit forwards.
    def redo(self):
        if not self._redo:
            return False
        self._undo.append([Keep(k.start, k.end) for k in self.keeps])
        self.keeps = self._redo.pop()
        return True

    # Remove a time range from the clip.
    def delete_range(self, a, b):
        a, b = sorted((self.clamp(a), self.clamp(b)))
        if b - a < MIN_KEEP:
            return False
        self._push()
        self._delete_raw(a, b)
        return True

    # Bring previously deleted audio back.
    def restore_range(self, a, b):
        a, b = sorted((self.clamp(a), self.clamp(b)))
        if b - a < MIN_KEEP:
            return False
        self._push()
        self._tidy(self.keeps + [Keep(a, b)])
        return True

    # Undo every edit: keep the whole recording.
    def reset(self):
        if self.duration() <= 0:
            return False
        self._push()
        self.keeps = [Keep(0.0, self.duration())]
        return True

    # Delete near-silent head and tail using the pyramid; returns seconds removed.
    def auto_trim_silence(self, threshold_db=-45.0, pad_ms=40.0):
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

    # Turn the keeps into Pieces: the recipe the streamer follows.
    def plan(self, fade_ms=500.0):
        sr = self.samplerate()
        fade_frames = max(0, int(sr * fade_ms / 1000.0))
        pieces, pos = [], 0
        for keep in self.keeps:
            a = max(0, int(keep.start * sr))
            b = min(self.frames(), int(keep.end * sr))
            n = b - a
            if n < 2:
                continue
            pieces.append(Piece(pos, a, n, min(fade_frames, n // 2)))
            pos += n
        return pieces



# Produces the edited clip on demand, block by block, from the store:
# reads the right source frames, applies each piece's fade in/out, skips
# the deleted parts, and optionally runs the loudness guard. Memory is
# one block, whatever the clip length.
class ClipStreamer:

    # Build a streamer over a plan.
    def __init__(self, store, pieces, guard=None, end_fade_frames=0):
        self.store = store
        self.pieces = pieces
        self.guard = guard
        self.end_fade = max(0, int(end_fade_frames))
        self.total = pieces[-1].out_end() if pieces else 0
        self._starts = [p.out_start for p in pieces]
        self.pos = 0

    # Total frames the clip will contain.
    def total_frames(self):
        return self.total

    # Clip length in seconds.
    def duration(self):
        return self.total / float(self.store.samplerate) if self.store else 0.0

    # Jump to an output frame and reset the guard so gain history is clean.
    def seek(self, out_frame):
        self.pos = max(0, min(int(out_frame), self.total))
        if self.guard:
            self.guard.reset()

    # Index of the piece holding an output frame.
    def _piece_at(self, out_frame):
        i = bisect.bisect_right(self._starts, out_frame) - 1
        return max(0, min(i, len(self.pieces) - 1))

    # Source frame that an output frame came from.
    def source_frame(self, out_frame):
        if not self.pieces:
            return 0
        out_frame = max(0, min(int(out_frame), self.total - 1))
        piece = self.pieces[self._piece_at(out_frame)]
        return piece.src_start + (out_frame - piece.out_start)

    # First output frame at or after a source frame, skipping deleted audio.
    def out_frame(self, src_frame):
        for piece in self.pieces:
            if src_frame < piece.src_start:
                return piece.out_start
            if src_frame < piece.src_start + piece.frames:
                return piece.out_start + (src_frame - piece.src_start)
        return self.total

    # Read the next count frames of the finished clip.
    def read(self, count):
        channels = self.store.channels
        out = np.zeros((count, channels), dtype=np.float32)
        filled = 0
        while filled < count and self.pos < self.total:
            piece = self.pieces[self._piece_at(self.pos)]
            offset = self.pos - piece.out_start
            take = min(count - filled, piece.frames - offset)
            if take <= 0:
                break
            block = self.store.read(piece.src_start + offset, take)
            if len(block) < take:
                take = len(block)
                if take == 0:
                    break
            self._apply_piece_fade(block, offset, piece)
            out[filled:filled + take] = block[:take]
            filled += take
            self.pos += take
        if filled == 0:
            return out[:0]
        result = out[:filled]
        self._apply_end_fade(result, self.pos - filled)
        if self.guard:
            self.guard.process(result)
        return result

    # Ramp the part of a block that falls inside this piece's fades.
    def _apply_piece_fade(self, block, offset, piece):
        fade = piece.fade
        if fade < 2 or len(block) == 0:
            return
        idx = np.arange(offset, offset + len(block), dtype=np.float32)
        env = np.ones(len(block), dtype=np.float32)
        rising = idx < fade
        if rising.any():
            env[rising] = idx[rising] / float(fade)
        tail_start = piece.frames - fade
        falling = idx >= tail_start
        if falling.any():
            env[falling] = np.minimum(env[falling],
                                      (piece.frames - 1 - idx[falling]) / float(fade))
        np.clip(env, 0.0, 1.0, out=env)
        block *= env[:, None]

    # Apply the long fade on the very end of the clip.
    def _apply_end_fade(self, block, block_out_start):
        fade = self.end_fade
        if fade < 2 or len(block) == 0:
            return
        start = self.total - fade
        idx = np.arange(block_out_start, block_out_start + len(block), dtype=np.float32)
        inside = idx >= start
        if not inside.any():
            return
        env = np.ones(len(block), dtype=np.float32)
        env[inside] = np.clip((self.total - 1 - idx[inside]) / float(fade), 0.0, 1.0)
        block *= env[:, None]