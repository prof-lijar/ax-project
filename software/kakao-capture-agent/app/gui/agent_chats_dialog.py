"""Choose exact conversation windows for single-chat and multi-chat actions."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.gui.theme import apply_theme, label
from app.models import AgentError


class AgentChatsDialog(QDialog):
    def __init__(self, candidates, selected, parent=None, *, maximum=3, foreground_target=None):
        super().__init__(parent)
        self.candidates = []
        self.maximum = maximum
        self.foreground_target = foreground_target
        self.setWindowTitle("Select Window" if maximum == 1 else "Select Agent Chats")
        self.resize(700, 470)
        apply_theme(self)
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                "Choose the conversation window"
                if maximum == 1
                else "Choose 1–3 conversation windows",
                "heading",
            )
        )
        layout.addWidget(
            label(
                "Choose a window from the list or click Pick chat. VoyagerI will minimize for five seconds. "
                "Click inside the intended chat’s typing area during that time."
            )
        )
        self.windows = QListWidget()
        self.windows.setAccessibleName("Conversations")
        for target in candidates:
            self.add_target(target, target in selected)
        layout.addWidget(self.windows)
        self.pick = QPushButton("Pick chat")
        self.pick.setEnabled(foreground_target is not None)
        self.pick.clicked.connect(self.start_pick)
        layout.addWidget(self.pick)
        self.pick_timer = QTimer(self)
        self.pick_timer.setSingleShot(True)
        self.pick_timer.timeout.connect(self.finish_pick)
        self.summary = label("")
        layout.addWidget(self.summary)
        layout.addWidget(
            label(
                "Confirm the conversation you intend VoyagerI to use."
                if maximum == 1
                else "Confirm only conversations you intend to monitor. Preview, history and test tools use the first checked chat."
            )
        )
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(
            "Use selected chat" if maximum == 1 else "Use selected chats"
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.windows.itemChanged.connect(self.update_count)
        self.update_count()

    def add_target(self, target, checked):
        item = QListWidgetItem(
            f"{target.title} — {target.executable} (PID {target.pid}, window {target.hwnd:#x})"
        )
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.candidates.append(target)
        self.windows.addItem(item)
        return item

    def start_pick(self):
        self.pick.setEnabled(False)
        owner = self.parentWidget()
        if owner:
            self.owner_state = owner.windowState()
            owner.showMinimized()
        self.showMinimized()
        self.pick_timer.start(5000)

    def finish_pick(self):
        try:
            target = self.foreground_target()
            if target in self.candidates:
                item = self.windows.item(self.candidates.index(target))
            else:
                item = self.add_target(target, False)
            item.setCheckState(Qt.Checked)
            self.windows.setCurrentItem(item)
            self.update_count(item)
        except AgentError as error:
            self.summary.setText(str(error))
        except Exception:
            self.summary.setText(
                "Could not identify the active chat. Click Pick chat and try again."
            )
        finally:
            self.restore_owner()
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.pick.setEnabled(True)

    def restore_owner(self):
        if hasattr(self, "owner_state"):
            self.parentWidget().setWindowState(self.owner_state)
            del self.owner_state

    def done(self, result):
        self.pick_timer.stop()
        self.restore_owner()
        super().done(result)

    def selected_targets(self):
        return [
            target
            for index, target in enumerate(self.candidates)
            if self.windows.item(index).checkState() == Qt.Checked
        ]

    def update_count(self, item=None):
        if self.maximum == 1 and item is not None and item.checkState() == Qt.Checked:
            for i in range(self.windows.count()):
                other = self.windows.item(i)
                if other is not item and other.checkState() == Qt.Checked:
                    other.setCheckState(Qt.Unchecked)
        count = len(self.selected_targets())
        self.summary.setText(f"{count} selected")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(1 <= count <= self.maximum)

    def accept(self):
        if 1 <= len(self.selected_targets()) <= self.maximum:
            super().accept()
