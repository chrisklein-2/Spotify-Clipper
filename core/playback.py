"""
playback.py - StreamPlayer (queue-buffered audio output) and TaskThread.
"""

import queue
import threading

import sounddevice as sd
from PySide6.QtCore import QThread, Signal

from .constants import PLAY_BLOCK


class TaskThread(QThread):
    """Runs one callable off the GUI thread with progress reporting."""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self.func = func

    def run(self):
        try:
            self.done.emit(self.func(self.progress.emit))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class StreamPlayer:
    """Plays a ClipStreamer without ever materialising it.

    A filler thread reads blocks into a queue and the audio callback only
    pops from it, so a page fault on the memmap can never stall the device.
    """

    def __init__(self):
        self.stream = None
        self.streamer = None
        self.queue = queue.Queue(maxsize=8)
        self.filler = None
        self.stop_flag = threading.Event()
        self.started_at = 0
        self.played = 0
        self.samplerate = 44100
        self.mode = None
        self.finished = False
        self._pending = None
        self._pending_at = 0

    def play(self, streamer, mode, start_frame=0):
        self.stop()
        if streamer is None or streamer.total_frames() <= 0:
            return
        self.streamer = streamer
        self.mode = mode
        self.samplerate = streamer.store.samplerate
        channels = streamer.store.channels
        self.started_at = max(0, min(int(start_frame), streamer.total_frames() - 1))
        self.played = 0
        self.finished = False
        self._pending = None
        self._pending_at = 0
        streamer.seek(self.started_at)
        self.queue = queue.Queue(maxsize=8)
        self.stop_flag.clear()
        self.filler = threading.Thread(target=self._fill, daemon=True)
        self.filler.start()
        self.stream = sd.OutputStream(
            samplerate=self.samplerate, channels=channels,
            dtype="float32", blocksize=1024, callback=self._cb,
        )
        self.stream.start()

    def _fill(self):
        while not self.stop_flag.is_set():
            block = self.streamer.read(PLAY_BLOCK)
            if len(block) == 0:
                try:
                    self.queue.put(None, timeout=1.0)
                except queue.Full:
                    pass
                return
            while not self.stop_flag.is_set():
                try:
                    self.queue.put(block, timeout=0.2)
                    break
                except queue.Full:
                    pass

    def _cb(self, outdata, frames, time_info, status):
        need, offset = frames, 0
        while need > 0:
            if self._pending is None:
                try:
                    self._pending = self.queue.get_nowait()
                except queue.Empty:
                    outdata[offset:] = 0.0
                    return
                if self._pending is None:
                    outdata[offset:] = 0.0
                    self.finished = True
                    raise sd.CallbackStop()
                self._pending_at = 0
            block = self._pending
            take = min(need, len(block) - self._pending_at)
            outdata[offset:offset + take] = block[self._pending_at:self._pending_at + take]
            self._pending_at += take
            offset += take
            need -= take
            self.played += take
            if self._pending_at >= len(block):
                self._pending = None

    def is_playing(self):
        return self.stream is not None and self.stream.active and not self.finished

    def out_frame(self):
        return self.started_at + self.played

    def stop(self):
        self.stop_flag.set()
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.filler is not None:
            self.filler.join(timeout=1.0)
            self.filler = None
        self._pending = None
        self._pending_at = 0
        self.mode = None