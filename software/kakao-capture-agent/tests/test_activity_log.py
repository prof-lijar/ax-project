import threading
from dataclasses import replace

from app.config import Config
from app.gui.activity_log import ActivityLog
from app.gui.main_window import Signals
from app.storage.chat_paths import chat_queue_key
from tests.test_multi_chat import targets


def test_live_tabs_update_from_worker_even_when_hidden_and_names_duplicate(qt_app):
    config = Config()
    config.select_agent_chats([replace(t, title="같은 대화 <group>") for t in targets()])
    views = ActivityLog(config)
    signals = Signals()
    signals.chat_activity.connect(views.log_chat)
    keys = [chat_queue_key(c) for c in config.agent_configs()]
    try:
        assert views.count() == 4
        assert [views.tabText(i) for i in range(1, 4)] == [
            f"{i}. 같은 대화 <group>" for i in range(1, 4)
        ]
        views.setCurrentIndex(0)  # All three chat panes are hidden.

        def emit():
            for index, key in enumerate(keys):
                signals.chat_activity.emit(key, f"Only chat {index}: <b>literal</b>")

        worker = threading.Thread(target=emit)
        worker.start()
        worker.join()
        qt_app.processEvents()
        assert views.currentIndex() == 0
        for index, key in enumerate(keys):
            text = views.chat_logs[key].toPlainText()
            assert f"Only chat {index}: <b>literal</b>" in text
            assert text.count("Only chat") == 1
        assert views.all_log.toPlainText() == ""  # Global stream is routed independently.
    finally:
        views.deleteLater()


def test_reselection_keeps_identity_history_and_rejects_removed_chat_events(qt_app):
    config = Config()
    config.select_agent_chats(targets())
    views = ActivityLog(config)
    keys = [chat_queue_key(c) for c in config.agent_configs()]
    try:
        views.log_chat(keys[1], "Second chat history")
        original = views.chat_logs[keys[1]]
        views.setCurrentWidget(original)
        config.select_agent_chats(targets()[1:])
        views.refresh_chats(config)
        assert views.count() == 3
        assert views.currentWidget() is original
        assert "Second chat history" in original.toPlainText()
        views.log_chat(keys[0], "Late event must not move to the new first chat")
        assert "Late event" not in original.toPlainText()
        assert keys[0] not in views.chat_logs
        config.agent_chats = []
        config.target = None
        views.refresh_chats(config)
        assert views.count() == 1 and not views.chat_logs
    finally:
        views.deleteLater()


def test_each_live_log_is_bounded_and_does_not_pull_reader_to_bottom(qt_app):
    config = Config()
    config.select_agent_chats(targets())
    views = ActivityLog(config)
    key = chat_queue_key(config.agent_configs()[0])
    views.resize(600, 300)
    views.show()
    views.setCurrentWidget(views.chat_logs[key])
    try:
        for i in range(310):
            views.log_chat(key, f"event {i}")
        qt_app.processEvents()
        view = views.chat_logs[key]
        assert view.document().blockCount() == 300
        assert "event 0\n" not in view.toPlainText()
        scroll = view.verticalScrollBar()
        assert scroll.maximum() > 0
        scroll.setValue(0)
        views.log_chat(key, "Latest event while reading history")
        qt_app.processEvents()
        assert scroll.value() == 0
        assert view.document().blockCount() == 300
    finally:
        views.close()
        views.deleteLater()
