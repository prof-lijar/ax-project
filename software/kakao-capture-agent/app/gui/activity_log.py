"""Live, bounded activity views keyed by durable chat identity."""

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTabWidget, QTextEdit

from app.gui.i18n import translate
from app.storage.chat_paths import chat_queue_key


class ActivityLog(QTabWidget):
    def __init__(self, config):
        super().__init__()
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideRight)
        self.all_log = self.new_log()
        self.addTab(self.all_log, "All activity")
        self.chat_logs = {}
        self.refresh_chats(config)

    @staticmethod
    def new_log():
        view = QTextEdit()
        view.setReadOnly(True)
        view.document().setMaximumBlockCount(300)
        return view

    def refresh_chats(self, config):
        def t(source, **values):
            return translate(config.language, source, **values)

        self.setAccessibleName(t("Activity views by chat"))
        self.all_log.setAccessibleName(t("All activity"))
        self.all_log.setPlaceholderText(t("Activity will appear here as you use the agent."))
        self.setTabText(0, t("All activity"))
        current = self.currentWidget()
        selected = {
            chat_queue_key(chat): chat.target.title
            for chat in config.agent_configs()
            if chat.target is not None
        }
        while self.count() > 1:
            self.removeTab(1)
        for key in list(self.chat_logs):
            if key not in selected:
                self.chat_logs.pop(key).deleteLater()
        for index, (key, title) in enumerate(selected.items(), 1):
            if key not in self.chat_logs:
                self.chat_logs[key] = self.new_log()
            view = self.chat_logs[key]
            view.setAccessibleName(t("Chat {index}: {title} activity", index=index, title=title))
            view.setPlaceholderText(t("Live activity will appear here when this chat runs."))
            tab = self.addTab(view, f"{index}. {title}")
            self.setTabToolTip(tab, t("Chat {index}: {title}", index=index, title=title))
        if current is self.all_log or current in self.chat_logs.values():
            self.setCurrentWidget(current)

    @staticmethod
    def append(view, message):
        # Keep service text literal; preserve the reader's position in older logs.
        scroll = view.verticalScrollBar()
        following = scroll.value() >= scroll.maximum()
        position = scroll.value()
        cursor = QTextCursor(view.document())
        cursor.movePosition(QTextCursor.End)
        if not view.document().isEmpty():
            cursor.insertBlock()
        cursor.insertText(time.strftime("[%H:%M:%S] ") + message)
        scroll.setValue(scroll.maximum() if following else position)

    def log_chat(self, key, message):
        # A late event from a removed selection must not enter another chat's log.
        if key in self.chat_logs:
            self.append(self.chat_logs[key], message)
