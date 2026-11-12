import re

# Format seconds as m:ss.hh, or h:mm:ss for long recordings.
def format_time(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    rest = seconds - hours * 3600 - minutes * 60
    if hours:
        return f"{hours}:{minutes:02d}:{rest:05.2f}"
    return f"{minutes}:{rest:05.2f}"


def parse_time(text):
    """Parse 4:20, 1:04:20, 4m20s, 260 or 2h into seconds; None if unreadable."""
    text = (text or "").strip().lower().replace(" ", "")
    if not text:
        return None
    if ":" in text:
        try:
            total = 0.0
            for part in text.split(":"):
                total = total * 60 + float(part or 0)
            return total
        except ValueError:
            return None
    match = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s?)?", text
    )
    if not match or not any(match.groups()):
        return None
    hours = float(match.group(1) or 0)
    minutes = float(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds

