"""Recorder: capture thread → queue → writer thread → raw int16 on disk."""

import os
import queue
import threading
import warnings

import numpy as np
import sounddevice as sd

from store import AudioStore

try:
    import soundcard as sc
except Exception:
    sc = None

from .devices import DEFAULT_SR

LIVE_SECONDS = 10.0
ENV_BUCKET = 1024            # frames per min/max bucket of the whole-recording overview

# ── glitch counter ──────────────────────────────────────────────
_glitches = 0
_real_showwarning = warnings.showwarning


def _catch_glitch(message, category, filename, lineno, file=None, line=None):
    global _glitches
    if "discontinuity" in str(message).lower():
        _glitches += 1
        return
    _real_showwarning(message, category, filename, lineno, file, line)


warnings.showwarning = _catch_glitch
warnings.filterwarnings("always", message=".*discontinuity.*")

def glitch_count():
    return _glitches


def reset_glitches():
    global _glitches
    _glitches = 0


# ── utilities ───────────────────────────────────────────────────
def fit_channels(block, channels):
    block = np.asarray(block, dtype=np.float32)
    if block.ndim == 1:
        block = block[:, None]
    if block.shape[1] == channels:
        return np.ascontiguousarray(block)
    if channels == 1:
        return np.ascontiguousarray(block.mean(axis=1, keepdims=True))
    if block.shape[1] == 1:
        return np.ascontiguousarray(np.repeat(block, channels, axis=1))
    return np.ascontiguousarray(block[:, :channels])


# ── Recorder ────────────────────────────────────────────────────
class Recorder:

    def __init__(self, device, path, samplerate=DEFAULT_SR, channels=2):
        self.device = device
        self.path = path
        self.samplerate = int(samplerate)
        self.channels = 1 if channels == 1 else 2
        self._queue = queue.Queue(maxsize=512)
        self._stop = threading.Event()
        self._cap_thread = None
        self._wr_thread = None
        self._stream = None
        self._file = None
        self._error = None
        self._frames = 0
        self._peak = 0.0
        self._ring = np.zeros(int(LIVE_SECONDS * self.samplerate), dtype=np.float32)
        self._ring_pos = 0
        self._ring_full = False
        self.paused = False
        self.env_bucket = ENV_BUCKET
        self._env_lock = threading.Lock()
        self._env_min = np.zeros(0, dtype=np.float32)
        self._env_max = np.zeros(0, dtype=np.float32)
        self._env_tail = np.zeros(0, dtype=np.float32)

    def start(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        reset_glitches()
        self._file = open(self.path, "wb", buffering=1 << 20)
        self._stop.clear()
        self._wr_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._wr_thread.start()
        self._start_capture()

    # stop capture but keep the file open for resuming.
    def pause(self):
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._cap_thread is not None:
            self._cap_thread.join(timeout=3.0)
            self._cap_thread = None
        # tell writer to drain then exit
        try:
            self._queue.put(None, timeout=1.0)
        except queue.Full:
            pass
        if self._wr_thread is not None:
            self._wr_thread.join(timeout=10.0)
            self._wr_thread = None
        if self._file is not None:
            self._file.flush()
        self.paused = True

    # continue recording to the same file after a pause.
    def resume(self):
        if not self.paused or self._file is None:
            raise RuntimeError("Cannot resume: not paused or file closed")
        self.paused = False
        self._stop.clear()
        self._queue = queue.Queue(maxsize=512)
        self._wr_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._wr_thread.start()
        self._start_capture()

    def _start_capture(self):
        if self.device.backend == "soundcard":
            if sc is None:
                raise RuntimeError("soundcard library is not available")
            self._cap_thread = threading.Thread(target=self._sc_loop, daemon=True)
            self._cap_thread.start()
        else:
            self._start_sd()

    def _writer_loop(self):
        while True:
            try:
                block = self._queue.get(timeout=0.2)
            except queue.Empty:
                if self._stop.is_set():
                    break
                continue
            if block is None:
                break
            try:
                self._file.write(block.tobytes())
            except Exception as exc:
                self._error = f"write failed: {exc}"
                break

    def _sc_loop(self):
        try:
            mic = sc.get_microphone(self.device.ident,
                                    include_loopback=self.device.is_loopback)
            with mic.recorder(samplerate=self.samplerate, blocksize=1024) as rec:
                while not self._stop.is_set():
                    self._submit(rec.record(numframes=4096))
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"

    def _start_sd(self):
        info = sd.query_devices(self.device.ident)
        native = max(1, min(2, int(info["max_input_channels"])))
        self._stream = sd.InputStream(device=self.device.ident, channels=native,
                                      samplerate=self.samplerate, dtype="float32",
                                      blocksize=2048, callback=self._sd_cb)
        self._stream.start()

    def _sd_cb(self, indata, frames, time_info, status):
        global _glitches
        if status and (status.input_overflow or status.input_underflow):
            _glitches += 1
        self._submit(indata)

    def _submit(self, raw):
        block = fit_channels(raw, self.channels)
        if block.size == 0:
            return
        peak = float(np.abs(block).max())
        if peak > self._peak:
            self._peak = peak
        mono = block[:, 0] if self.channels == 1 else block.mean(axis=1)
        self._push_ring(mono)
        self._push_env(mono)
        pcm = (np.clip(block, -1.0, 1.0) * 32767.0).astype(np.int16)
        try:
            self._queue.put_nowait(pcm)
            self._frames += len(pcm)
        except queue.Full:
            self._error = "disk cannot keep up with the recording"
    
    def _push_env(self, mono):
        """Fold samples into the running min/max overview of the whole take."""
        with self._env_lock:
            data = np.concatenate([self._env_tail, mono]) if len(self._env_tail) else mono
            n = len(data) // ENV_BUCKET
            if n:
                view = data[:n * ENV_BUCKET].reshape(n, ENV_BUCKET)
                self._env_min = np.concatenate([self._env_min, view.min(axis=1)])
                self._env_max = np.concatenate([self._env_max, view.max(axis=1)])
            self._env_tail = np.array(data[n * ENV_BUCKET:], dtype=np.float32)

    def envelope(self):
        """(mins, maxs) of everything recorded so far, one pair per bucket."""
        with self._env_lock:
            return self._env_min, self._env_max
        
    def _push_ring(self, mono):
        size = len(self._ring)
        n = len(mono)
        if n >= size:
            self._ring[:] = mono[-size:]
            self._ring_pos = 0
            self._ring_full = True
            return
        end = self._ring_pos + n
        if end <= size:
            self._ring[self._ring_pos:end] = mono
        else:
            split = size - self._ring_pos
            self._ring[self._ring_pos:] = mono[:split]
            self._ring[:end - size] = mono[split:]
        self._ring_pos = end % size
        if end >= size:
            self._ring_full = True

    def elapsed(self):
        return self._frames / float(self.samplerate)

    def peak(self):
        return self._peak

    def error(self):
        return self._error

    def latest_mono(self, seconds):
        want = min(int(seconds * self.samplerate), len(self._ring))
        if not self._ring_full and self._ring_pos < want:
            return self._ring[:max(1, self._ring_pos)].copy()
        start = (self._ring_pos - want) % len(self._ring)
        if start + want <= len(self._ring):
            return self._ring[start:start + want].copy()
        return np.concatenate([self._ring[start:],
                               self._ring[:start + want - len(self._ring)]])

    def stop(self):
        if self.paused:
            self.paused = False
        else:
            self._stop.set()
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            if self._cap_thread is not None:
                self._cap_thread.join(timeout=3.0)
                self._cap_thread = None
            try:
                self._queue.put(None, timeout=1.0)
            except queue.Full:
                pass
            if self._wr_thread is not None:
                self._wr_thread.join(timeout=10.0)
                self._wr_thread = None
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
        if self._error:
            raise RuntimeError(self._error)
        return AudioStore(self.path, self.samplerate, self.channels)