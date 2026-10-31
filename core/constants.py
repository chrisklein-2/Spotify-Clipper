"""
constants.py - paths, limits, filter strings, help text.
"""

import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXPORT_DIR = os.path.join(APP_DIR, "exports")
DEFAULT_FINALS_DIR = os.path.join(APP_DIR, "finals")
SESSION_DIR = os.path.join(APP_DIR, "session")
PLAY_BLOCK = 8192
ORPHAN_AGE = 24 * 3600

LOAD_FILTER = (
    "Audio / video (*.wav *.flac *.ogg *.aiff *.mp3 *.m4a *.mp4 *.aac "
    "*.opus *.webm *.mkv *.mov *.wma);;All files (*)"
)

HELP_HTML = """
<h3>1 &nbsp;Capture</h3>
<p><b>Source</b> menu &#8594; pick a <b>LOOPBACK</b> device. Press <b>Record</b>, play
the episode, press <b>Stop</b>. Audio goes straight to disk, so a 2 hour podcast costs
about 15 MB of RAM. For speech tick <b>Mono</b> and pick <b>32 000 Hz</b>.</p>

<h3>2 &nbsp;Finding a spot</h3>
<ul>
<li><b>Go to</b> box: type <b>4:20</b>, <b>1:04:20</b>, <b>4m20s</b> or <b>260</b> and
press Enter.</li>
<li><b>Scrollbar</b> under the waveform pans when you are zoomed in.</li>
<li><b>&minus; / +</b> buttons (or the <b>-</b> and <b>+</b> keys) zoom <i>around the
playhead</i>. So: click the ruler where you want to look, then press <b>+</b>. No mouse
precision needed.</li>
<li><b>Home / End</b> jump to the ends, <b>PageUp / PageDown</b> pan a screen.</li>
<li>Wheel zooms at the cursor, Shift+wheel or middle-drag pans.</li>
</ul>

<h3>3 &nbsp;Selecting with markers</h3>
<p>Click the ruler at the start, press <b>[</b> (Mark in). Click the ruler at the end,
press <b>]</b> (Mark out). Yellow flags show both. Then <b>Del</b>. You can also just
drag across the waveform, or drag a blue edge to adjust.</p>

<h3>4 &nbsp;Cut</h3>
<ul>
<li><b>Delete selection (Del)</b> removes that audio.
<b>Restore selection (Ctrl+R)</b> brings it back.</li>
<li><b>Undo (Ctrl+Z)</b> / <b>Redo (Ctrl+Y)</b> — unlimited and instant.</li>
<li><b>Auto-trim silence (Ctrl+T)</b> deletes the quiet head and tail.</li>
</ul>
<p>Green = kept, dark/dashed = deleted, <b>orange wedges</b> = the fades.</p>

<h3>5 &nbsp;Fades at every cut</h3>
<p><b>Fade per cut</b> gives every kept piece its own fade in and fade out. At the
default <b>500 ms</b> each cut is half a second down then half a second up.
<b>End fade</b> is an extra long fade on the very end.</p>

<h3>6 &nbsp;Combining two recordings</h3>
<p>Record half, edit, <b>Export as... &#8594; .wav</b>. Record the other half, edit,
export. Then <b>File &#8594; Join audio files</b>, add both, drag into order, Join.
Each file becomes its own piece. <b>File &#8594; Append audio file</b> adds one to the
end of what is loaded, keeping your cuts.</p>

<h3>7 &nbsp;Output</h3>
<ul>
<li><b>Quiet down loud parts</b> — compressor + ceiling. Only turns things
<i>down</i>, never up.</li>
<li><b>Threshold</b> — audio above this gets compressed. -20 gentle, -28 aggressive.</li>
<li><b>Ceiling</b> — absolute maximum. Nothing exceeds it.</li>
<li><b>Cover</b> — pick any image; it gets embedded in .m4a and .mp3 as artwork.</li>
<li><b>Bitrate</b> — 48 kbps AAC is plenty for speech.</li>
</ul>

<h3>8 &nbsp;Export and phone</h3>
<p><b>Export (Ctrl+E)</b> writes to <b>exports/</b>, auto-numbered.
<b>Finalize (Ctrl+Shift+F)</b> writes straight into <b>finals/</b>.
<b>Send folder to phone (Ctrl+P)</b> serves a whole folder over Wi-Fi —
scan the QR code and pick any file. Sending is not saving.</p>
<p>Personal use only.</p>
"""