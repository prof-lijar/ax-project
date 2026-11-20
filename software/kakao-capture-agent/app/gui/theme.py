"""Shared desktop presentation; no capture or workflow behavior lives here."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

STYLESHEET = """
QWidget { color: #243041; font-size: 13px; }
QMainWindow, QDialog, QWidget#workspace { background: #f4f5f7; }
QLabel { background: transparent; }
QLabel[role="title"] { font-size: 25px; font-weight: 700; color: #182230; }
QLabel[role="heading"] { font-size: 16px; font-weight: 600; color: #182230; }
QLabel[role="muted"] { color: #606b7a; }
QLabel#brand { background: transparent; }
QLabel#state { background: #e7ebf0; border-radius: 10px; padding: 7px 13px;
    font-weight: 600; }
QLabel#state[tone="active"] { background: #def3e7; color: #17623b; }
QLabel#state[tone="paused"] { background: #fff0ce; color: #805510; }
QFrame#card { background: white; border: 1px solid #e0e4ea; border-radius: 12px; }
QLabel#preview { background: #eef1f5; color: #606b7a; border: 1px dashed #c9d1dc;
    border-radius: 10px; padding: 10px; }
QPushButton { background: white; border: 1px solid #cdd4dd; border-radius: 7px;
    padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #f1f4f8; border-color: #9daabb; }
QPushButton:pressed { background: #e4e9ef; }
QPushButton[role="primary"] { background: #fee500; border-color: #e7d000; color: #302b20; }
QPushButton[role="primary"]:hover { background: #f4d900; }
QPushButton[role="primary"]:pressed { background: #e5ca00; }
QPushButton[role="stop"] { background: #fff1f0; color: #ac3535; border-color: #edc7c4; }
QPushButton[role="stop"]:hover { background: #ffe1df; }
QPushButton:disabled { background: #f0f2f5; color: #8b94a1; border-color: #e0e4ea; }
QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QTabBar::tab:focus { border: 2px solid #7387a5; }
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {
    background: white; border: 1px solid #cdd4dd; border-radius: 7px;
    padding: 7px; selection-background-color: #f5df67; selection-color: #243041; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QPlainTextEdit:disabled { background: #f0f2f5; color: #8b94a1; }
QCheckBox { spacing: 8px; padding: 5px 0; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: transparent; color: #606b7a; padding: 12px 18px;
    border-bottom: 3px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: #182230; border-bottom-color: #ddc600; }
QTabBar::tab:hover { background: #e9edf2; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #bdc6d2; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: #eef1f5; border: 0; border-radius: 4px; max-height: 8px; }
QProgressBar::chunk { background: #8b9db4; border-radius: 4px; }
QProgressBar[warning="true"]::chunk { background: #bc7a19; }
QToolTip { background: #243041; color: white; border: 0; padding: 7px; }
"""


def apply_theme(widget):
    widget.setFont(QFont("Segoe UI", 10))
    widget.setStyleSheet(STYLESHEET)


def label(text, role="muted"):
    item = QLabel(text)
    item.setTextFormat(Qt.PlainText)
    item.setWordWrap(True)
    item.setProperty("role", role)
    return item


def card(title, description=""):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    layout.addWidget(label(title, "heading"))
    if description:
        layout.addWidget(label(description))
    return frame, layout


class CapturePreview(QLabel):
    """Retain the original image so resizing never stretches or crops a capture."""

    def __init__(self):
        super().__init__(
            "Your conversation preview\n\nSelect a chat window, then choose Preview.\n"
            "The message area is detected automatically."
        )
        self.source = QPixmap()
        self.setObjectName("preview")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumSize(200, 220)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.setAccessibleName("Conversation screenshot preview")

    def show_png(self, png):
        image = QPixmap()
        if image.loadFromData(png, "PNG"):
            self.source = image
            self._fit()

    def clear(self):
        self.source = QPixmap()
        super().clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        if not self.source.isNull():
            self.setPixmap(
                self.source.scaled(
                    self.contentsRect().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
