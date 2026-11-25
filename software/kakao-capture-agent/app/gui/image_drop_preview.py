"""Saved-capture preview that accepts one local image file from the desktop."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal

from app.gui.theme import CapturePreview


class ImageDropPreview(CapturePreview):
    file_dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.prompt = "Drop a capture image here\nor choose a file above."
        self.setText(self.prompt)
        self.setToolTip("Drop one PNG, JPEG or BMP file here (up to 20 MiB)")

    def dropped_path(self, event):
        if not self.isEnabled() or not event.possibleActions() & Qt.CopyAction:
            return None
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = urls[0].toLocalFile()
        if Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            return None
        return path

    def dragEnterEvent(self, event):
        if self.dropped_path(event) is None:
            event.ignore()
        else:
            event.setDropAction(Qt.CopyAction)
            event.accept()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        path = self.dropped_path(event)
        if path is None:
            event.ignore()
            return
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.file_dropped.emit(path)
