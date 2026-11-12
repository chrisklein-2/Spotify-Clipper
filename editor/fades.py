"""editor/fades.py - the only place fade gain curves are computed."""
import numpy as np


def cap_fades(fade_in, fade_out, length):
    """Clamp two fades so together they never exceed the piece (any unit)."""
    fade_in = max(0, min(fade_in, length))
    fade_out = max(0, min(fade_out, length))
    total = fade_in + fade_out
    if total > length and total > 0:
        k = length / total
        fade_in, fade_out = fade_in * k, fade_out * k
    return fade_in, fade_out


def piece_gain(offset, count, piece_frames, fade_in, fade_out):
    """Gain for frames [offset, offset+count) of one piece, or None if flat."""
    if count <= 0 or (fade_in < 2 and fade_out < 2):
        return None
    if offset >= fade_in and offset + count <= piece_frames - fade_out:
        return None
    idx = np.arange(offset, offset + count, dtype=np.int64)
    gain = np.ones(count, dtype=np.float32)
    if fade_in >= 2:
        m = idx < fade_in
        if m.any():
            gain[m] = idx[m] / float(fade_in)
    if fade_out >= 2:
        m = idx >= piece_frames - fade_out
        if m.any():
            gain[m] = np.minimum(gain[m],
                                 (piece_frames - 1 - idx[m]) / float(fade_out))
    np.clip(gain, 0.0, 1.0, out=gain)
    return gain


def end_gain(block_start, count, total_frames, end_fade):
    fade = min(int(end_fade), int(total_frames))
    if fade < 2 or count <= 0:
        return None
    start = total_frames - fade
    if block_start + count <= start:
        return None
    idx = np.arange(block_start, block_start + count, dtype=np.int64)
    gain = np.ones(count, dtype=np.float32)
    inside = idx >= start
    gain[inside] = np.clip((total_frames - 1 - idx[inside]) / float(fade), 0.0, 1.0)
    return gain