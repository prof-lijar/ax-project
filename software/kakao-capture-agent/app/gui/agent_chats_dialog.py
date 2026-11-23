"""Explicitly select up to three conversations for the existing continuous workflows."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from app.gui.theme import apply_theme, label


class AgentChatsDialog(QDialog):
    def __init__(self, candidates, selected, parent=None):
        super().__init__(parent)
        self.candidates = candidates
        self.setWindowTitle("Select Agent Chats")
        self.resize(700, 440)
        apply_theme(self)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Choose 1–3 KakaoTalk conversation windows", "heading"))
        layout.addWidget(
            label(
                "Run Agent (auto) and 기기위치조정/전원연결 run the same workflow in each checked chat. "
                "The agent switches windows automatically. Keep their latest messages visible."
            )
        )
        self.windows = QListWidget()
        self.windows.setAccessibleName("Agent conversations")
        for target in candidates:
            item = QListWidgetItem(f"{target.title} — {target.executable} (PID {target.pid})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if target in selected else Qt.Unchecked)
            self.windows.addItem(item)
        layout.addWidget(self.windows)
        self.summary = label("")
        layout.addWidget(self.summary)
        layout.addWidget(
            label(
                "Confirm only conversations you intend the agent to capture and reply to. "
                "Preview, history and test tools use the first checked conversation."
            )
        )
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Use selected chats")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.windows.itemChanged.connect(self.update_count)
        self.update_count()

    def selected_targets(self):
        return [
            target
            for index, target in enumerate(self.candidates)
            if self.windows.item(index).checkState() == Qt.Checked
        ]

    def update_count(self, *_):
        count = len(self.selected_targets())
        self.summary.setText(f"{count} selected · choose between 1 and 3")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(1 <= count <= 3)

    def accept(self):
        if 1 <= len(self.selected_targets()) <= 3:
            super().accept()
