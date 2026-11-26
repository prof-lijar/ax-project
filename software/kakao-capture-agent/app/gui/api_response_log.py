"""Bounded, selectable raw workflow responses; credentials are never supplied here."""

import json
import time

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class ApiResponseLog(QWidget):
    limit = 50

    def __init__(self, ui):
        super().__init__()
        self.responses = []
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.selector = QComboBox()
        ui.bind(self.selector.setAccessibleName, "API response history")
        row.addWidget(self.selector, 1)
        copy = ui.button("Copy JSON")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.body.toPlainText()))
        row.addWidget(copy)
        clear = ui.button("Clear")
        clear.clicked.connect(self.clear)
        row.addWidget(clear)
        layout.addLayout(row)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        ui.bind(self.body.setAccessibleName, "API response JSON")
        ui.bind(self.body.setPlaceholderText, "AX768 responses will appear here, including HTTP and validation failures.")
        layout.addWidget(self.body, 1)
        self.selector.currentIndexChanged.connect(self.show_response)

    @Slot(object)
    def append_response(self, event):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        # Store complete JSON documents, not a line-truncated text log.
        text = json.dumps({"received_at": timestamp, **event}, ensure_ascii=False, indent=2)
        following = self.selector.currentIndex() == self.selector.count() - 1
        self.selector.blockSignals(True)
        self.responses.append(text)
        self.selector.addItem(f"{timestamp} · {event.get('chat', '')} · HTTP {event.get('http_status', '?')}")
        if len(self.responses) > self.limit:
            self.responses.pop(0)
            self.selector.removeItem(0)
        if following:
            self.selector.setCurrentIndex(self.selector.count() - 1)
        self.selector.blockSignals(False)
        self.show_response(self.selector.currentIndex())

    def show_response(self, index):
        self.body.setPlainText(self.responses[index] if 0 <= index < len(self.responses) else "")

    def clear(self):
        self.responses.clear()
        self.selector.clear()
        self.body.clear()
