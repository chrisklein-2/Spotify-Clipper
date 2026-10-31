"""Device discovery: enumerate capture sources, pick defaults."""

from dataclasses import dataclass

import sounddevice as sd

try:
    import soundcard as sc
except Exception as _exc:
    sc = None
    SOUNDCARD_ERROR = str(_exc)
else:
    SOUNDCARD_ERROR = ""

DEFAULT_SR = 48000
SAMPLE_RATES = [
    (48000, "48 000 Hz  (usual Windows default)"),
    (44100, "44 100 Hz  (CD rate)"),
    (32000, "32 000 Hz  (speech)"),
    (24000, "24 000 Hz  (speech, smallest)"),
]


@dataclass
class CaptureDevice:
    backend: str
    ident: object
    label: str
    is_loopback: bool

    def __str__(self):
        return self.label


def list_capture_devices():
    devices = []
    if sc is not None:
        try:
            for mic in sc.all_microphones(include_loopback=True):
                loop = bool(getattr(mic, "isloopback", False))
                tag = "LOOPBACK" if loop else "MIC"
                devices.append(CaptureDevice("soundcard", mic.id,
                                             f"{tag}  {mic.name}", loop))
        except Exception as exc:
            print("soundcard enumeration:", exc)
    try:
        hostapis = sd.query_hostapis()
        for idx, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                api = hostapis[dev["hostapi"]]["name"]
                devices.append(CaptureDevice("sounddevice", idx,
                                             f"INPUT  {dev['name']} ({api})", False))
    except Exception as exc:
        print("sounddevice enumeration:", exc)
    devices.sort(key=lambda d: (not d.is_loopback, d.label.lower()))
    return devices


def default_device_index(devices):
    if not devices:
        return -1
    name = None
    if sc is not None:
        try:
            name = sc.default_speaker().name
        except Exception:
            pass
    if name:
        for i, dev in enumerate(devices):
            if dev.is_loopback and name.lower() in dev.label.lower():
                return i
    for i, dev in enumerate(devices):
        if dev.is_loopback:
            return i
    return 0


def native_samplerate(device):
    if device is None:
        return None
    try:
        if device.backend == "sounddevice":
            return int(sd.query_devices(device.ident)["default_samplerate"])
        hostapis = sd.query_hostapis()
        for i, api in enumerate(hostapis):
            if "WASAPI" in api["name"]:
                out = sd.query_hostapis(i)["default_output_device"]
                if out >= 0:
                    return int(sd.query_devices(out)["default_samplerate"])
        return int(sd.query_devices(sd.default.device[1])["default_samplerate"])
    except Exception:
        return None


def loopback_help():
    if sc is None:
        return (
            "soundcard is not installed (%s). Install it, or route Spotify "
            "through VB-Cable / BlackHole and pick it as an INPUT."
            % (SOUNDCARD_ERROR or "unknown error")
        )
    return (
        "LOOPBACK records what your speakers play. To capture Spotify only, "
        "route it through VB-Cable and pick INPUT CABLE Output."
    )