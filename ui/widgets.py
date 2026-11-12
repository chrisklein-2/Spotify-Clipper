from PySide6.QtWidgets import QFrame, QPushButton

def sep():
    """Thin vertical separator line."""
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setFrameShadow(QFrame.Plain)
    return f


def abtn(action, primary=False, min_w=0):
    """QPushButton wired to a QAction."""
    b = QPushButton(action.text())
    tip = action.text()
    if not action.shortcut().isEmpty():
        tip += f"   [{action.shortcut().toString()}]"
    b.setToolTip(tip)
    b.setEnabled(action.isEnabled())
    b.clicked.connect(action.trigger)
    action.changed.connect(lambda a=action, b=b: b.setEnabled(a.isEnabled()))
    if primary:
        b.setObjectName("primary")
    if min_w:
        b.setMinimumWidth(min_w)
    return b

