"""
audiostore.py - disk-backed audio plus a peak pyramid.

Why this exists: holding a 2 hour recording as float32 in RAM costs ~2.8 GB, and
drawing it by scanning every sample costs ~400 ms per repaint. Both are avoidable.

  * Samples live in a raw interleaved int16 file and are reached through np.memmap,
    so the OS pages in only what is touched and reclaims it under pressure. int16 is
    transparent here because the source is already lossy-decoded audio.
  * A peak pyramid (min/max per 256 samples, then per 2048, per 16384 ...) is built
    once. Drawing reads ~1000 buckets from whichever level matches the zoom, so it is
    O(pixels) instead of O(samples). This is how Audacity and Reaper do it.

2 hour stereo 48 kHz: 1.38 GB on disk, ~12 MB of pyramid in RAM, repaints in ~0.1 ms.
"""

import os

import numpy as np

BASE_BUCKET = 256
REDUCE = 8
MIN_BUCKETS = 512
SCALE = 1.0 / 32768.0


# Frames of int16 audio that fit in one raw file of this size.
def frames_in_file(path, channels):
    try:
        return os.path.getsize(path) // (2 * max(1, channels))
    except OSError:
        return 0



# Read-only view over a raw interleaved int16 file, plus the pyramid.
# Nothing is copied into RAM except the pyramid; read() pulls just the
# frames asked for and converts that slice to float32.
class AudioStore:

    # Wrap an existing raw int16 file.
    def __init__(self, path, samplerate, channels):
        self.path = path
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.map = None
        self.levels = []
        self._open()

    # Memory-map the file as (frames, channels), read only.
    def _open(self):
        count = frames_in_file(self.path, self.channels)
        if count < 1:
            self.map = np.zeros((0, self.channels), dtype=np.int16)
            return
        self.map = np.memmap(self.path, dtype=np.int16, mode="r",
                             shape=(count, self.channels))

    # Total frames held.
    def frames(self):
        return 0 if self.map is None else len(self.map)

    # Length in seconds.
    def duration(self):
        return self.frames() / float(self.samplerate)

    # Read a frame range as float32 in -1..1; only this slice is touched.
    def read(self, start, count):
        start = max(0, int(start))
        end = min(self.frames(), start + int(count))
        if end <= start:
            return np.zeros((0, self.channels), dtype=np.float32)
        return np.asarray(self.map[start:end], dtype=np.float32) * SCALE

    # Build the pyramid in one streaming pass; progress takes 0..1.
    def build_pyramid(self, progress=None):
        total = self.frames()
        base = BASE_BUCKET
        buckets = total // base
        if buckets < 1:
            self.levels = []
            return
        mins = np.empty(buckets, dtype=np.float32)
        maxs = np.empty(buckets, dtype=np.float32)
        step = 65536  # buckets per pass: ~16.7M frames, ~33 MB of page-ins
        for i in range(0, buckets, step):
            j = min(buckets, i + step)
            block = self.map[i * base:j * base]
            view = block.reshape(j - i, base * self.channels)
            mins[i:j] = view.min(axis=1)
            maxs[i:j] = view.max(axis=1)
            if progress:
                progress(j / float(buckets))
        mins *= SCALE
        maxs *= SCALE
        levels = [(base, mins, maxs)]
        while len(mins) > MIN_BUCKETS * REDUCE:
            count = len(mins) // REDUCE
            mins = mins[:count * REDUCE].reshape(count, REDUCE).min(axis=1)
            maxs = maxs[:count * REDUCE].reshape(count, REDUCE).max(axis=1)
            base *= REDUCE
            levels.append((base, mins, maxs))
        self.levels = levels

    # Bytes of RAM the pyramid occupies, for the status line.
    def pyramid_bytes(self):
        return sum(m.nbytes + x.nbytes for _, m, x in self.levels)

    # Index of the coarsest pyramid level still giving a bucket per pixel.
    def level_for(self, samples_per_pixel):
        chosen = 0
        for i, (base, _, _) in enumerate(self.levels):
            if base <= samples_per_pixel:
                chosen = i
            else:
                break
        return chosen

    # Per-pixel (mins, maxs) for a frame range, straight from the pyramid.
    def peaks(self, start_frame, end_frame, width):
        start_frame = max(0, int(start_frame))
        end_frame = min(self.frames(), int(end_frame))
        if width < 1 or end_frame - start_frame < 2:
            return None
        spp = (end_frame - start_frame) / float(width)
        if not self.levels or spp < BASE_BUCKET:
            return self._peaks_raw(start_frame, end_frame, width)
        base, mins, maxs = self.levels[self.level_for(spp)]
        edges = np.linspace(start_frame / base, end_frame / base,
                            width + 1).astype(np.int64)
        edges = np.clip(edges, 0, len(mins))
        out_min = np.zeros(width, dtype=np.float32)
        out_max = np.zeros(width, dtype=np.float32)
        for x in range(width):
            a = edges[x]
            b = max(a + 1, edges[x + 1])
            b = min(b, len(mins))
            if a >= b:
                continue
            out_min[x] = mins[a:b].min()
            out_max[x] = maxs[a:b].max()
        return out_min, out_max

    # Zoomed in past the pyramid: read the visible frames directly.
    def _peaks_raw(self, start_frame, end_frame, width):
        block = self.map[start_frame:end_frame]
        if len(block) < 2:
            return None
        edges = np.linspace(0, len(block), width + 1).astype(np.int64)
        out_min = np.zeros(width, dtype=np.float32)
        out_max = np.zeros(width, dtype=np.float32)
        for x in range(width):
            a = edges[x]
            b = max(a + 1, edges[x + 1])
            chunk = block[a:min(b, len(block))]
            if chunk.size:
                out_min[x] = chunk.min() * SCALE
                out_max[x] = chunk.max() * SCALE
        return out_min, out_max

    # First and last frame louder than a threshold, using the pyramid.
    def loud_bounds(self, threshold_db=-45.0):
        if not self.levels:
            return 0, self.frames()
        base, mins, maxs = self.levels[0]
        thr = 10.0 ** (threshold_db / 20.0)
        loud = np.where(np.maximum(np.abs(mins), np.abs(maxs)) > thr)[0]
        if loud.size == 0:
            return 0, self.frames()
        return int(loud[0] * base), int(min(self.frames(), (loud[-1] + 1) * base))

    # Release the mapping so the file can be deleted.
    def close(self):
        if self.map is not None and hasattr(self.map, "_mmap"):
            try:
                self.map._mmap.close()
            except Exception:
                pass
        self.map = None
        self.levels = []

    # Close and remove the backing file.
    def delete(self):
        self.close()
        try:
            os.remove(self.path)
        except OSError:
            pass