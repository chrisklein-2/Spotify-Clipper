"""core/transport.py - TransportMixin: play / pause / seek / raw / test tone."""
import sounddevice as sd

from editor import ClipStreamer, Piece
from processing import ceiling_test_tone


class TransportMixin:

    def stop_playback(self):
        self.player.stop()
        self.update_actions()

    def _play_clip(self, from_playhead):
        streamer = self.make_streamer()
        if streamer is None:
            self.statusBar().showMessage(
                "Nothing to play - everything is deleted.", 4000
            )
            return
        start = 0
        if from_playhead:
            src = int(self.wave.playhead * self.timeline.samplerate())
            start = streamer.out_frame(src)
            if start >= streamer.total_frames():
                start = 0
        self.player.play(streamer, "clip", start)
        self.update_actions()

    def toggle_play(self):
        if self.player.is_playing():
            self.stop_playback()
        else:
            self._play_clip(from_playhead=True)

    def play_from_start(self):
        self._play_clip(from_playhead=False)

    def play_raw(self):
        if self.timeline.duration() <= 0:
            return
        start = int(self.wave.playhead * self.timeline.samplerate())
        piece = Piece(0, start, max(1, self.timeline.frames() - start), 0)
        streamer = ClipStreamer(self.timeline.store, [piece], None, 0)
        streamer.raw_offset = start
        self.player.play(streamer, "raw", 0)
        self.update_actions()

    def on_playhead_moved(self, t):
        if self.player.is_playing():
            self._seek_target = t
            self._seek_timer.start()
        self.update_status()

    def _do_seek(self):
        t, self._seek_target = self._seek_target, None
        if t is None or not self.player.is_playing():
            return
        if self.player.mode == "raw":
            self.play_raw()              # reads wave.playhead, already moved
            return
        streamer = self.make_streamer()
        if streamer is None:
            self.stop_playback()
            return
        start = streamer.out_frame(int(t * self.timeline.samplerate()))
        if start >= streamer.total_frames():
            self.stop_playback()
            return
        self.player.play(streamer, "clip", start)

    # Play a 1 s tone at the ceiling: the loudest any export can ever be.
    def test_ceiling(self):
        self.stop_playback()
        rate = 44100
        sd.play(ceiling_test_tone(self.ceiling.value(), rate), rate)
        self.statusBar().showMessage(
            f"Playing a {self.ceiling.value():.1f} dBFS tone \u2014 nothing in the "
            f"export will be louder than this at your current volume.", 6000)