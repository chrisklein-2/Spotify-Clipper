"""
theme.py - dark palette, stylesheet and the waveform colours.
"""

from PySide6.QtGui import QColor, QPalette

BG = "#0e0e11"
PANEL = "#17171c"
PANEL_HI = "#1f1f27"
BORDER = "#2b2b35"
TEXT = "#e7e7ec"
TEXT_DIM = "#9699a3"
ACCENT = "#1fd47a"
ACCENT_DIM = "#15935a"
DANGER = "#e05c5c"

COL_BG = QColor("#0b0b0e")
COL_RULER = QColor("#15151b")
COL_RULER_LINE = QColor("#2b2b35")
COL_DEL_BG = QColor("#070709")
COL_WAVE_KEEP = QColor("#1fd47a")
COL_WAVE_KEEP_SOFT = QColor("#0f7a47")
COL_WAVE_DEL = QColor("#3a3a45")
COL_SEL = QColor(74, 134, 255, 55)
COL_SEL_EDGE = QColor("#78a8ff")
COL_MARK = QColor("#ffd24a")
COL_PLAYHEAD = QColor("#ffffff")
COL_FADE = QColor(255, 160, 64, 200)
COL_TEXT = QColor(TEXT_DIM)
COL_TEXT_BRIGHT = QColor(TEXT)

QSS = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 12px;
}}
QMenuBar {{
    background: {PANEL};
    border-bottom: 1px solid {BORDER};
    padding: 2px 0;
}}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {PANEL_HI}; }}
QGroupBox {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {TEXT_DIM};
    font-weight: 600;
}}
QLabel {{ background: transparent; }}
QLabel#hint {{ color: {TEXT_DIM}; padding: 3px 2px; font-size: 11px; }}
QPushButton {{
    background: {PANEL_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 10px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #262630; border-color: #3a3a46; }}
QPushButton:pressed {{ background: #121218; }}
QPushButton:disabled {{ color: #5a5a66; background: #14141a; border-color: #21212a; }}
QPushButton#primary {{
    background: {ACCENT_DIM};
    border: 1px solid {ACCENT};
    color: #04140c;
    font-weight: 700;
}}
QPushButton#primary:hover {{ background: {ACCENT}; }}
QPushButton#record {{ border: 1px solid #6b2b2b; }}
QPushButton#record:checked {{ background: {DANGER}; color: #1a0606; font-weight: 700; }}
QPushButton#collapse {{
    background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 3px; padding: 0; color: {TEXT_DIM}; font-size: 10px;
}}
QPushButton#collapse:hover {{ background: {PANEL_HI}; color: {ACCENT}; }}
QPushButton#tiny {{ padding: 4px 7px; font-weight: 700; }}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{
    background: {PANEL_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: {ACCENT_DIM};
}}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {PANEL_HI};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
    outline: 0;
}}
QCheckBox {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {PANEL_HI};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox:disabled {{ color: #5a5a66; }}
QListWidget {{
    background: {PANEL_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: 0;
    font-size: 11px;
}}
QListWidget::item {{ padding: 3px 6px; }}
QListWidget::item:selected {{ background: {ACCENT_DIM}; color: #04140c; }}
QStatusBar {{
    background: {PANEL}; color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
    font-family: Consolas, monospace; font-size: 11px;
}}
QToolTip {{
    background: #23232c; color: {TEXT};
    border: 1px solid {BORDER}; padding: 5px;
}}
QMenu {{ background: {PANEL_HI}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; color: #04140c; }}
QMenu::item:disabled {{ color: #5a5a66; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QProgressBar {{
    background: {PANEL_HI}; border: 1px solid {BORDER};
    border-radius: 6px; height: 14px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT_DIM}; border-radius: 5px; }}
QTextBrowser {{ background: {PANEL_HI}; border: 1px solid {BORDER}; border-radius: 6px; }}
QScrollBar:horizontal {{
    background: {PANEL}; height: 14px; border: 1px solid {BORDER};
    border-radius: 7px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #3c3c4a; border-radius: 6px; min-width: 30px; margin: 1px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: #33333f; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QFrame[frameShape="5"] {{ color: {BORDER}; }}
"""


# Apply the Fusion style, a dark palette and the stylesheet to the app.
def apply_dark_theme(app):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(PANEL_HI))
    pal.setColor(QPalette.AlternateBase, QColor(PANEL))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(PANEL_HI))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT_DIM))
    pal.setColor(QPalette.HighlightedText, QColor("#04140c"))
    pal.setColor(QPalette.ToolTipBase, QColor(PANEL_HI))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#5a5a66"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5a5a66"))
    app.setPalette(pal)
    app.setStyleSheet(QSS)