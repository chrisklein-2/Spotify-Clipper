import warnings

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

