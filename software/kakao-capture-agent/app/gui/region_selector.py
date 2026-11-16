from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.models import Region


class RegionSelector(QWidget):
    """One logical overlay per monitor; drag positions are sampled in native pixels.

    Polling GetCursorPos on Windows avoids multiplying mixed-DPI global Qt origins.
    A shared selection allows the drag to extend across monitors.
    """

    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen, cursor, shared):
        super().__init__()
        self.cursor, self.shared, self.display = cursor, shared, screen
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(screen.geometry())
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.shared["start"] = self.shared["end"] = self.cursor()
            self.shared["qt_start"] = self.shared["qt_end"] = event.globalPosition().toPoint()
            self.update_all()

    def mouseMoveEvent(self, event):
        if self.shared.get("start"):
            self.shared["end"] = self.cursor()
            self.shared["qt_end"] = event.globalPosition().toPoint()
            self.update_all()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or "start" not in self.shared:
            return
        a, b = self.shared["start"], self.cursor()
        self.selected.emit(
            Region(min(a[0], b[0]), min(a[1], b[1]), abs(a[0] - b[0]), abs(a[1] - b[1]))
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()

    def update_all(self):
        for overlay in self.shared["overlays"]:
            overlay.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 65))
        painter.setPen(QPen(QColor("#00e5ff"), 2))
        if "qt_start" in self.shared:
            rect = QRect(
                self.mapFromGlobal(self.shared["qt_start"]),
                self.mapFromGlobal(self.shared["qt_end"]),
            ).normalized()
            painter.drawRect(rect)
        painter.drawText(24, 40, "Drag over the conversation messages. Esc cancels.")
