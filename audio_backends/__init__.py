"""audio_backends - device discovery and disk-backed recording."""

from .devices import (
    SAMPLE_RATES, CaptureDevice, list_capture_devices,
    default_device_index, native_samplerate, loopback_help,
)
from .recorder import (
    Recorder, fit_channels, glitch_count, reset_glitches,
)

from .player import StreamPlayer