"""
processing.py - the streaming output chain and file I/O.

LoudnessGuard carries gain state across calls so playback and export can both feed it one
block at a time. Two things it gets right that are easy to get wrong:

  * The gain is computed per 4 ms block but applied as a per-sample interpolated ramp.
    Applying it as a step per block puts a discontinuity in the signal 250 times a
    second, which is audible as constant background hash (zipper noise).
  * Disabled means disabled. No ceiling, no clipping, nothing - so "bypass" is a real
    A/B reference and not a quietly-distorted one.

Everything else wraps ffmpeg: decoding any input to the raw int16 audiostore format,
concatenating on disk, preparing cover art, and streaming a ClipStreamer into an encoder
through stdin so memory stays flat no matter how long the clip is.
"""

import os
import shutil
import subprocess
import tempfile

import numpy as np
import soundfile as sf

EPS = 1e-9
BLOCK_MS = 4.0
EXPORT_BLOCK = 65536
COVER_PX = 640

NATIVE_READ = (".wav", ".flac", ".ogg", ".aiff", ".aif", ".au", ".w64")
ART_FORMATS = (".m4a", ".mp4", ".aac", ".mp3")
IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.webp *.bmp);;All files (*)"

BITRATES = [(32, "32 kbps  (speech, tiny)"),
            (48, "48 kbps  (speech, best value)"),
            (64, "64 kbps  (speech, safe)"),
            (96, "96 kbps  (music, good)"),
            (128, "128 kbps  (music, default)")]


# Short sine at the ceiling level, used by the Test button: the loudest
# any sample in the export is allowed to be.
def ceiling_test_tone(ceiling_db, samplerate=44100, seconds=1.0, freq=440.0):
    t = np.arange(int(samplerate * seconds), dtype=np.float32) / samplerate
    tone = np.sin(2.0 * np.pi * freq * t).astype(np.float32)
    fade = max(1, int(samplerate * 0.02))
    tone[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    tone[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return tone * db_to_lin(ceiling_db)

# Convert decibels to a linear gain.
def db_to_lin(db):
    return float(10.0 ** (db / 20.0))


# Estimated lossy file size in megabytes.
def estimate_mb(seconds, bitrate_kbps):
    return seconds * bitrate_kbps * 1000.0 / 8.0 / 1e6


# Which external tools are missing from PATH; empty list means all good.
def missing_tools():
    return [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]


# True if ffmpeg is callable.
def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


# True if this container can carry embedded cover art.
def supports_cover(path):
    return os.path.splitext(path)[1].lower() in ART_FORMATS


# Add _2, _3 ... to a path until it does not exist.
def unique_path(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"



# Streaming compressor plus optional ceiling, with gain state carried
# between blocks. Feed it consecutive blocks and the result matches
# processing the whole clip at once; after a seek call reset().
class LoudnessGuard:

    # Configure the guard; ceiling_db=None means no ceiling at all.
    def __init__(self, samplerate, enabled=True, threshold_db=-20.0, ratio=3.0,
                 ceiling_db=-3.0, attack_ms=10.0, release_ms=400.0):
        self.enabled = bool(enabled)
        self.samplerate = int(samplerate)
        self.block = max(8, int(samplerate * BLOCK_MS / 1000.0))
        self.threshold_db = float(threshold_db)
        self.ratio = max(1.0, float(ratio))
        self.ceiling = None if ceiling_db is None else db_to_lin(ceiling_db)
        self.attack = float(np.exp(-self.block / max(1.0, samplerate * attack_ms / 1000.0)))
        self.release = float(np.exp(-self.block / max(1.0, samplerate * release_ms / 1000.0)))
        self.gain = 1.0

    # Forget the gain history, e.g. after a seek.
    def reset(self):
        self.gain = 1.0

    # Per-block target gain: enough reduction to honour the ratio and the ceiling.
    def _targets(self, block, frames):
        size = self.block
        mono = np.abs(block).max(axis=1)
        pad = (-frames) % size
        if pad:
            mono = np.concatenate([mono, np.zeros(pad, dtype=np.float32)])
        peaks = mono.reshape(-1, size).max(axis=1)
        over = np.maximum(0.0, 20.0 * np.log10(np.maximum(peaks, EPS)) - self.threshold_db)
        target = np.power(10.0, (-over * (1.0 - 1.0 / self.ratio)) / 20.0).astype(np.float32)
        if self.ceiling is not None:
            np.minimum(target, self.ceiling / np.maximum(peaks, EPS), out=target)
        np.minimum(target, 1.0, out=target)
        return target

    # Smooth the per-block targets with one-pole attack/release, carrying state.
    def _smooth(self, target):
        gains = np.empty(len(target), dtype=np.float32)
        gain = self.gain
        for i in range(len(target)):
            want = float(target[i])
            coef = self.attack if want < gain else self.release
            gain = want + coef * (gain - want)
            gains[i] = gain
        return gains

    # Expand block gains to a per-sample ramp, anchored to the previous call.
    def _curve(self, gains, previous, frames):
        size = self.block
        count = len(gains)
        xp = np.empty(count + 1, dtype=np.float64)
        xp[0] = -size * 0.5
        xp[1:] = np.arange(count, dtype=np.float64) * size + size * 0.5
        fp = np.empty(count + 1, dtype=np.float64)
        fp[0] = previous
        fp[1:] = gains
        return np.interp(np.arange(frames, dtype=np.float64), xp, fp).astype(np.float32)

    # Attenuate one block in place and return it. Disabled does nothing at all.
    def process(self, block):
        frames = len(block)
        if frames == 0 or not self.enabled:
            return block
        target = self._targets(block, frames)
        previous = self.gain
        gains = self._smooth(target)
        self.gain = float(gains[-1])
        block *= self._curve(gains, previous, frames)[:, None]
        if self.ceiling is not None:
            np.clip(block, -self.ceiling, self.ceiling, out=block)
        return block


# Probe an input for its sample rate and channel count.
def probe_audio(path):
    if os.path.splitext(path)[1].lower() in NATIVE_READ:
        try:
            info = sf.info(path)
            return info.samplerate, min(2, info.channels)
        except Exception:
            pass
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=sample_rate,channels", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        parts = (out.stdout or "").strip().split(",")
        rate = int(parts[0]) if parts and parts[0].isdigit() else 44100
        chans = min(2, int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else 2
        return rate, chans
    except Exception:
        return 44100, 2


# Decode any audio/video file into a raw int16 file; returns (frames, sr, channels).
def decode_to_raw(src, dst, force_samplerate=None, force_channels=None):
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is not on PATH.")
    rate, chans = probe_audio(src)
    samplerate = int(force_samplerate or rate)
    channels = int(force_channels or chans)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-vn", "-ar", str(samplerate), "-ac", str(channels),
                    "-f", "s16le", "-c:a", "pcm_s16le", dst], check=True)
    return os.path.getsize(dst) // (2 * channels), samplerate, channels


# Append a decoded file onto the end of an existing raw file; returns total frames.
def append_decoded(src, raw_path, samplerate, channels):
    with tempfile.TemporaryDirectory(prefix="spotclip_") as tmp:
        part = os.path.join(tmp, "part.raw")
        decode_to_raw(src, part, samplerate, channels)
        with open(raw_path, "ab") as out, open(part, "rb") as inp:
            while True:
                chunk = inp.read(1 << 22)
                if not chunk:
                    break
                out.write(chunk)
    return os.path.getsize(raw_path) // (2 * channels)


# Re-encode artwork to a modest JPEG so embedding costs ~40 KB, not megabytes.
def prepare_cover(src, dst, max_px=COVER_PX):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-vf", f"scale='min({max_px},iw)':-2", "-frames:v", "1",
                    "-q:v", "3", dst], check=True)
    return dst


# Build the ffmpeg argument list for one export.
def _encode_args(path, samplerate, channels, bitrate_kbps, title, art):
    ext = os.path.splitext(path)[1].lower()
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "s16le", "-ar", str(int(samplerate)), "-ac", str(int(channels)),
           "-i", "pipe:0"]
    if art:
        cmd += ["-i", art]
    cmd += ["-map", "0:a"]
    if art:
        cmd += ["-map", "1:v"]
    if ext in (".m4a", ".mp4", ".aac"):
        cmd += ["-c:a", "aac", "-b:a", f"{bitrate_kbps}k"]
    elif ext == ".mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", f"{bitrate_kbps}k"]
    if art:
        cmd += ["-c:v", "copy"]
        if ext == ".mp3":
            cmd += ["-id3v2_version", "3",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)"]
        else:
            cmd += ["-disposition:v:0", "attached_pic"]
    if ext in (".m4a", ".mp4"):
        cmd += ["-movflags", "+faststart"]
    if title:
        cmd += ["-metadata", f"title={title}", "-metadata", "artist=SpotClip"]
    return cmd + [path]


# Stream a ClipStreamer into a file; progress takes 0..1. Never holds the clip.
def export_stream(path, streamer, samplerate, channels, bitrate_kbps=48,
                  title=None, cover=None, progress=None):
    ext = os.path.splitext(path)[1].lower()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    total = max(1, streamer.total_frames())
    streamer.seek(0)
    if ext == ".wav":
        with sf.SoundFile(path, "w", samplerate=samplerate, channels=channels,
                          subtype="PCM_16") as handle:
            done = 0
            while True:
                block = streamer.read(EXPORT_BLOCK)
                if len(block) == 0:
                    break
                handle.write(block)
                done += len(block)
                if progress:
                    progress(done / total)
        return path
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is not on PATH - export as .wav instead.")
    with tempfile.TemporaryDirectory(prefix="spotclip_") as tmp:
        art = None
        if cover and os.path.exists(cover) and ext in ART_FORMATS:
            try:
                art = prepare_cover(cover, os.path.join(tmp, "cover.jpg"))
            except Exception as exc:
                print("cover art skipped:", exc)
                art = None
        cmd = _encode_args(path, samplerate, channels, bitrate_kbps, title, art)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        done = 0
        try:
            while True:
                block = streamer.read(EXPORT_BLOCK)
                if len(block) == 0:
                    break
                pcm = (np.clip(block, -1.0, 1.0) * 32767.0).astype("<i2")
                proc.stdin.write(pcm.tobytes())
                done += len(block)
                if progress:
                    progress(done / total)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError((err or b"").decode(errors="replace") or "ffmpeg failed")
    return path