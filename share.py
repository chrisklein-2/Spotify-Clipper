"""
share.py - serve a folder of clips to a phone over Wi-Fi.

A throwaway HTTP server serves every audio file in one folder behind a random
token URL. The QR code points to an index page; each file offers:

  * Download     -> the file with Content-Disposition: attachment.

The folder is re-scanned on every page load, so exporting another clip while
the dialog is open makes it appear on the phone after a refresh.
"""

import http.server
import mimetypes
import os
import secrets
import socket
import threading
import urllib.parse

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

try:
    import qrcode
except Exception:
    qrcode = None

AUDIO_EXTS = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac", ".opus")

PAGE_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpotClip</title>
<style>
body{{font-family:-apple-system,sans-serif;text-align:center;padding:30px 18px;
      background:#121216;color:#e7e7ec;margin:0}}
h2{{color:#1fd47a;margin:0 0 4px}}
p{{color:#9699a3;line-height:1.5;font-size:14px}}
.file{{border:1px solid #2b2b35;border-radius:12px;padding:12px;margin:14px auto;
       max-width:360px}}
.file p{{margin:2px 0 10px}}
.btn{{display:inline-block;margin:4px;padding:12px 18px;border-radius:10px;
      font-size:15px;font-weight:600;text-decoration:none}}
.files{{background:#1fd47a;color:#04140c}}
small{{color:#6c6f78;font-size:12px}}
</style>
</head><body>
<h2>SpotClip</h2>
<p><b>{folder}</b> &mdash; {count} file(s)</p>
{rows}
<p><small>Keep the SpotClip window open on the computer until downloads
finish. Reload this page to see newly exported files.</small></p>
</body></html>"""

ROW_HTML = """<div class="file">
<p><b>{name}</b><br><small>{size}</small></p>
<a class="btn files" href="{file_url}">Download</a>
</div>"""


# Best guess at this machine's LAN IP.
def local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


# Human-readable file size.
def pretty_size(path):
    mb = os.path.getsize(path) / 1e6
    return f"{mb * 1000:.0f} KB" if mb < 1 else f"{mb:.1f} MB"


# Audio files in a folder, sorted; re-scanned on every call.
def list_audio(folder):
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [n for n in names
            if os.path.splitext(n)[1].lower() in AUDIO_EXTS
            and os.path.isfile(os.path.join(folder, n))]


# Build a request handler class bound to one folder and one secret token.
def make_handler(folder, token):
    page_path = f"/{token}/"

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # Resolve a request path to a file inside the folder, or None.
        # Rejects anything that is not a plain basename of a listed file.
        def _file_for(self, path):
            clean = urllib.parse.unquote(path)
            prefix = f"/{token}/"
            if not clean.startswith(prefix):
                return None
            name = clean[len(prefix):]
            if (not name or "/" in name or "\\" in name
                    or name != os.path.basename(name)):
                return None
            if name not in list_audio(folder):
                return None
            return os.path.join(folder, name)

        def do_GET(self):
            clean = urllib.parse.unquote(self.path)
            if self.path == page_path or clean.rstrip("/") == f"/{token}":
                self._serve_page()
                return
            full = self._file_for(self.path)
            if full:
                self._serve_file(full)
            else:
                self.send_error(404)

        def do_HEAD(self):
            full = self._file_for(self.path)
            if full:
                self.send_response(200)
                self.send_header("Content-Length", str(os.path.getsize(full)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
            else:
                self.send_error(404)

        # Index page: one card per audio file, built fresh each request.
        def _serve_page(self):
            host = self.headers.get("Host") or local_ip()
            rows = []
            for name in list_audio(folder):
                file_url = f"/{token}/{urllib.parse.quote(name)}"
                rows.append(ROW_HTML.format(
                    name=name, size=pretty_size(os.path.join(folder, name)),
                    file_url=file_url))
            if not rows:
                rows = ["<p>No audio files in this folder yet.</p>"]
            html = PAGE_HTML.format(folder=os.path.basename(folder) or folder,
                                    count=len(rows),
                                    rows="".join(rows)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        # Serve one file as an attachment, honouring Range requests.
        def _serve_file(self, full):
            filename = os.path.basename(full)
            size = os.path.getsize(full)
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            start, end = self._range(size)
            length = end - start + 1
            self.send_response(206 if start or end != size - 1 else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{filename}"')
            if start or end != size - 1:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(full, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(262144, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _range(self, size):
            header = self.headers.get("Range", "")
            if not header.startswith("bytes="):
                return 0, size - 1
            try:
                first, _, last = header[6:].partition("-")
                s = int(first) if first else 0
                e = int(last) if last else size - 1
                return max(0, s), min(size - 1, e)
            except ValueError:
                return 0, size - 1

        def log_message(self, fmt, *args):
            pass

    return Handler


# Owns the throwaway HTTP server thread and the URL it serves.
class FolderServer:

    def __init__(self, folder):
        self.folder = folder
        self.token = secrets.token_urlsafe(8)
        self.httpd = None
        self.thread = None

    def start(self):
        handler = make_handler(self.folder, self.token)
        self.httpd = http.server.ThreadingHTTPServer(("0.0.0.0", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()
        port = self.httpd.server_address[1]
        return f"http://{local_ip()}:{port}/{self.token}/"

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


# Render a QR code pixmap, or None if the qrcode package is missing.
def qr_pixmap(text, px=280):
    if qrcode is None:
        return None
    code = qrcode.QRCode(border=2)
    code.add_data(text)
    code.make(fit=True)
    matrix = code.get_matrix()
    cells = len(matrix)
    scale = max(2, px // cells)
    image = QImage(cells * scale, cells * scale, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#000000"))
    for row in range(cells):
        for col in range(cells):
            if matrix[row][col]:
                painter.drawRect(col * scale, row * scale, scale, scale)
    painter.end()
    return QPixmap.fromImage(image)


# Modal window showing the QR code while the folder server runs.
class ShareDialog(QDialog):

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send folder to phone")
        self.setMinimumWidth(380)
        self.server = FolderServer(folder)
        try:
            url = self.server.start()
        except Exception as exc:
            url = f"(could not start server: {exc})"
        count = len(list_audio(folder))
        title = QLabel(f"<b>{os.path.basename(folder) or folder}</b>"
                       f"  —  {count} audio file(s)")
        title.setAlignment(Qt.AlignCenter)
        pix = qr_pixmap(url)
        qr_label = QLabel()
        if pix:
            qr_label.setPixmap(pix)
        else:
            qr_label.setText("pip install qrcode  to see a QR code here.")
        qr_label.setAlignment(Qt.AlignCenter)
        link = QLabel(f'<a href="{url}" style="color:#1fd47a;">{url}</a>')
        link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        link.setWordWrap(True)
        link.setAlignment(Qt.AlignCenter)
        steps = QLabel(
            "1. Same Wi-Fi on both devices.\n"
            "2. Point the iPhone Camera at the QR code, tap the link.\n"
            "3. Download any file — it lands in Files \u2192 Downloads.\n"
            "4. To get it into VLC: open Files, long-press the file,\n"
            "   Share \u2192 VLC.\n\n"
            "Export more clips while this is open, then reload the page\n"
            "on the phone to see them. Keep this window open meanwhile."
        )
        steps.setStyleSheet("color:#9699a3; line-height:1.5;")
        close = QPushButton("Done")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        for w in (title, qr_label, link, steps, close):
            layout.addWidget(w)

    def closeEvent(self, ev):
        self.server.stop()
        ev.accept()

    def done(self, result):
        self.server.stop()
        super().done(result)

# Pick a folder to share, with a live preview of the audio files inside,
# so you never have to check contents through the file explorer first.
class ShareFolderDialog(QDialog):

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send folder to phone")
        self.setMinimumSize(620, 360)
        self.folder_list = QListWidget()
        for label, path in folders:
            self._add_folder(label, path)
        self.folder_list.currentItemChanged.connect(self._refresh_files)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.NoSelection)
        self.file_list.setToolTip("Audio files that will be offered to the phone.")
        browse = QPushButton("Other folder...")
        browse.clicked.connect(self._browse)
        send = QPushButton("Send this folder")
        send.setObjectName("primary")
        send.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        left = QVBoxLayout()
        left.addWidget(QLabel("Folder"))
        left.addWidget(self.folder_list, 1)
        left.addWidget(browse)
        right = QVBoxLayout()
        right.addWidget(QLabel("Audio files inside"))
        right.addWidget(self.file_list, 1)
        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addLayout(right, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(send)
        root = QVBoxLayout(self)
        root.addLayout(body, 1)
        root.addLayout(buttons)
        self.folder_list.setCurrentRow(0)

    def _add_folder(self, label, path):
        count = len(list_audio(path))
        item = QListWidgetItem(f"{label}   ({count} audio file(s))")
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        self.folder_list.addItem(item)
        return item

    def _refresh_files(self, *_):
        self.file_list.clear()
        path = self.chosen()
        if not path:
            return
        names = list_audio(path)
        if not names:
            self.file_list.addItem("(no audio files in this folder)")
            return
        for name in names:
            self.file_list.addItem(
                f"{name}   ({pretty_size(os.path.join(path, name))})")

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Choose folder",
                                                self.chosen() or "")
        if path:
            self.folder_list.setCurrentItem(
                self._add_folder(os.path.basename(path) or path, path))

    def chosen(self):
        item = self.folder_list.currentItem()
        return item.data(Qt.UserRole) if item else None