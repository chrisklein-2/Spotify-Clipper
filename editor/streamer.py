import numpy as np
import bisect
from .fades import piece_gain, end_gain

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

    def _apply_piece_fade(self, block, offset, piece):
        gain = piece_gain(offset, len(block), piece.frames,
                          piece.fade_in, piece.fade_out)
        if gain is not None:
            block *= gain[:, None]
            
    def _apply_end_fade(self, block, block_out_start):
        gain = end_gain(block_out_start, len(block), self.total, self.end_fade)
        if gain is not None:
            block *= gain[:, None]