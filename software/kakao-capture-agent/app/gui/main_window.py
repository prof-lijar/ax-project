import ctypes
import logging
import threading
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.api.incoming_llm import RUN_AGENT_GREETING
from app.config import save
from app.gui.settings_dialog import SettingsDialog
from app.models import AgentError, State
from app.utils.windows import configure_startup, set_token


class Signals(QObject):
    status = Signal(str, str)
    preview = Signal(bytes)
    activity = Signal(str)
    upload = Signal(str)
    stats = Signal(object)
    text_preview = Signal(str)
    setup_ready = Signal()


class EmergencyHotkey(QAbstractNativeEventFilter):
    def __init__(self, stop):
        super().__init__()
        self.stop = stop
        self.registered = bool(
            ctypes.windll.user32.RegisterHotKey(None, 0xCA01, 0x4000 | 0x0002 | 0x0004, 0x7B)
        )

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam == 0xCA01:
            self.stop()
            return True, 0
        return False, 0

    def close(self):
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, 0xCA01)


class MainWindow(QMainWindow):
    def __init__(self, config, config_path, desktop, monitor, uploader, queue, signals):
        super().__init__()
        self.config, self.config_path, self.desktop = config, config_path, desktop
        self.monitor, self.uploader, self.queue, self.signals = monitor, uploader, queue, signals
        self.closing = False
        self.pending_action = None
        self.control_threads = []
        self.action_generation = 0
        self.setWindowTitle("KakaoTalk Capture Agent")
        self.resize(680, 800)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(body)
        self.setCentralWidget(scroll_area)
        self.state_label = QLabel("STOPPED")
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)
        self.target_label = QLabel(
            f"Target: {config.target.title}" if config.target else "Target: not selected"
        )
        self.target_label.setTextFormat(Qt.PlainText)
        self.target_label.setWordWrap(True)
        layout.addWidget(self.target_label)
        self.setup_buttons = []
        row = QHBoxLayout()
        for title, action in [
            ("Select Window", self.select_window),
            ("Settings", self.settings),
        ]:
            button = QPushButton(title)
            button.clicked.connect(action)
            self.setup_buttons.append(button)
            row.addWidget(button)
        layout.addLayout(row)
        self.preview_label = QLabel(
            "Select a chat window; the conversation area is detected automatically"
        )
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(220)
        layout.addWidget(self.preview_label)
        row = QHBoxLayout()
        row.addWidget(QLabel("Capture interval (seconds)"))
        self.interval = QDoubleSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setValue(config.capture_interval_seconds)
        self.interval.valueChanged.connect(self.interval_changed)
        row.addWidget(self.interval)
        self.change = QCheckBox("Detect visual changes")
        self.change.setChecked(config.change_detection)
        self.change.toggled.connect(self.change_changed)
        row.addWidget(self.change)
        layout.addLayout(row)
        row = QHBoxLayout()
        for title, command in [
            ("Start / Resume", "start"),
            ("Stop", "stop"),
            ("Capture History", "history"),
            ("Cancel History", "cancel_history"),
        ]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, c=command: self.action(c))
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        for title, command in [
            ("Preview", "preview"),
            ("Scroll Up", "up"),
            ("Scroll Down", "down"),
            ("Confirm Latest Position", "confirm_bottom"),
        ]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, c=command: self.action(c))
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.save_local_button = QPushButton("Save Capture Locally")
        self.save_local_button.clicked.connect(lambda: self.action("save_local"))
        row.addWidget(self.save_local_button)
        open_folder = QPushButton("Open Captures Folder")
        open_folder.clicked.connect(self.open_captures_folder)
        row.addWidget(open_folder)
        layout.addLayout(row)
        self.capture_folder_label = QLabel(f"PNG folder: {self.queue.images}")
        self.capture_folder_label.setWordWrap(True)
        self.capture_folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.capture_folder_label)
        row = QHBoxLayout()
        layout.addWidget(QLabel("Test reply message"))
        self.test_reply_edit = QPlainTextEdit(config.test_reply_text)
        self.test_reply_edit.setMaximumHeight(80)
        self.test_reply_edit.setPlaceholderText(
            "Enter the message to send (up to 2,000 characters)"
        )
        layout.addWidget(self.test_reply_edit)
        self.send_test_button = QPushButton("Send Test Reply")
        self.send_test_button.clicked.connect(lambda: self.action("send_test"))
        row.addWidget(self.send_test_button)
        self.test_workflow_button = QPushButton("Test Workflow")
        self.test_workflow_button.clicked.connect(lambda: self.action("test_workflow"))
        row.addWidget(self.test_workflow_button)
        self.bizgo_test_button = QPushButton("Send Bizgo Sample")
        self.bizgo_test_button.clicked.connect(lambda: self.action("bizgo_test"))
        row.addWidget(self.bizgo_test_button)
        layout.addLayout(row)
        hint = QLabel(
            "Send Test Reply stops capture, focuses the selected chat, replaces its message-box contents with your entered message, and sends once."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        workflow_hint = QLabel(
            "Test Workflow saves the current region, sends it to your configured vision LLM, "
            "then automatically sends one [test] simulation summary and extracted text to this chat. "
            "When enabled, Bizgo sends a phone-message copy afterward. "
            "This explicit action uses configured services even in local-only capture mode."
        )
        workflow_hint.setWordWrap(True)
        layout.addWidget(workflow_hint)
        self.auto_catch_button = QPushButton("Run Agent (auto)")
        self.auto_catch_button.clicked.connect(lambda: self.action("auto_catch"))
        layout.addWidget(self.auto_catch_button)
        auto_hint = QLabel(
            f"Start by sending {RUN_AGENT_GREETING} once. "
            "Watch display changes → capture → extract text → process with the LLM → reply. "
            "New captures queue while earlier work is processing; replies are sent in capture order. "
            "Keep the selected chat open at the latest messages. "
            "Stop / Ctrl+Shift+F12 ends Run Agent (auto)."
        )
        auto_hint.setWordWrap(True)
        layout.addWidget(auto_hint)
        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setPlaceholderText(
            "Latest incoming text extracted from a queued capture appears here"
        )
        self.text_preview.setMaximumHeight(130)
        self.text_preview.hide()
        signals.text_preview.connect(self.text_preview.setPlainText)
        signals.setup_ready.connect(self.persist)
        layout.addWidget(self.text_preview)
        self.review_text_button = QPushButton("Review Replies")
        self.review_text_button.clicked.connect(self.review_text_replies)
        layout.addWidget(self.review_text_button)
        self.incoming_test_button = QPushButton("Test Workflow 2: Reply to Next Message")
        self.incoming_test_button.clicked.connect(lambda: self.action("incoming_test"))
        layout.addWidget(self.incoming_test_button)
        incoming_hint = QLabel(
            "Open the latest messages first. Workflow 2 watches the visible region, sends changed "
            "frames to the vision LLM, replies once with [AI], then stops. Keep this chat visible. "
            "No Bizgo step. Stop or Ctrl+Shift+F12 cancels."
        )
        incoming_hint.setWordWrap(True)
        layout.addWidget(incoming_hint)
        self.bizgo_status = QLabel()
        self.bizgo_status.setWordWrap(True)
        layout.addWidget(self.bizgo_status)
        self.api_status = QLabel("API: idle")
        self.refresh_storage_mode()
        self.api_status.setWordWrap(True)
        self.queue_label = QLabel("Queue: loading")
        self.queue_label.setWordWrap(True)
        layout.addWidget(self.api_status)
        layout.addWidget(self.queue_label)
        row = QHBoxLayout()
        retry = QPushButton("Retry Failed Uploads")
        retry.clicked.connect(self.retry)
        row.addWidget(retry)
        bind = QPushButton("Assign Local Captures to API")
        bind.clicked.connect(self.bind_local)
        row.addWidget(bind)
        layout.addLayout(row)
        layout.addWidget(
            QLabel("Emergency stop: Ctrl+Shift+F12 or move the pointer to a primary-screen corner")
        )
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(300)
        layout.addWidget(self.logs)
        signals.status.connect(self.update_status)
        signals.preview.connect(self.update_preview)
        signals.activity.connect(self.log)
        signals.upload.connect(self.upload_status)
        signals.stats.connect(self.show_stats)
        self.hotkey = EmergencyHotkey(lambda: self.action("stop"))
        QApplication.instance().installNativeEventFilter(self.hotkey)
        if not self.hotkey.registered:
            self.log("Emergency hotkey unavailable; Stop and mouse fail-safe remain available")

    def log(self, message):
        self.logs.append(time.strftime("[%H:%M:%S] ") + message)
        logging.getLogger("kakao").info(message)

    def update_status(self, state, reason):
        self.state_label.setText(state + (": " + reason if reason else ""))
        stopped = state == State.STOPPED.value
        for button in self.setup_buttons:
            button.setEnabled(stopped)
        self.interval.setEnabled(stopped)
        self.change.setEnabled(stopped)
        self.save_local_button.setEnabled(state in (State.STOPPED.value, State.PAUSED.value))
        self.send_test_button.setEnabled(
            state != State.INITIALIZING.value and not self.pending_action and not self.closing
        )
        self.test_reply_edit.setEnabled(self.send_test_button.isEnabled())
        self.test_workflow_button.setEnabled(self.send_test_button.isEnabled())
        self.bizgo_test_button.setEnabled(self.send_test_button.isEnabled())
        self.auto_catch_button.setEnabled(
            self.send_test_button.isEnabled() and state != State.AUTO_CATCHING.value
        )
        self.review_text_button.setEnabled(self.can_review_replies(state))
        self.incoming_test_button.setEnabled(
            self.send_test_button.isEnabled() and state != State.WAITING_FOR_MESSAGE.value
        )

    def open_captures_folder(self):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.queue.images.resolve()))):
            QMessageBox.warning(
                self, "Captures folder", f"Open this folder manually:\n{self.queue.images}"
            )

    def refresh_storage_mode(self):
        if not self.config.bizgo_enabled:
            self.bizgo_status.setText(
                "Bizgo: disabled — enable in Settings to add the final phone-message step"
            )
        else:
            from app.api.bizgo_client import phone_number

            recipient = phone_number(self.config.bizgo_recipient)
            mode = (
                "SANDBOX — no phone delivery"
                if self.config.bizgo_sandbox
                else "PRODUCTION — sends a real phone message"
            )
            self.bizgo_status.setText(f"Bizgo: {mode} | Recipient: ******{recipient[-4:]}")
        self.api_status.setText(
            "API: paused — local-only mode (an upload already in progress may finish)"
            if self.config.local_only
            else "API: not configured — captures saved locally"
            if not self.config.api_url
            else "API: idle"
        )

    def update_preview(self, png):
        image = QPixmap()
        image.loadFromData(png, "PNG")
        self.preview_label.setPixmap(
            image.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def upload_status(self, message):
        if self.config.local_only:
            self.refresh_storage_mode()
        else:
            self.api_status.setText("API: " + message)
        self.log(message)

    def show_stats(self, stats):
        if "error" in stats:
            self.queue_label.setText("Queue storage unavailable")
            return
        used = stats["bytes"] / self.config.storage_limit_bytes
        last = (
            time.strftime("%H:%M:%S", time.localtime(stats["last_upload"]))
            if stats["last_upload"]
            else "never"
        )
        self.queue_label.setText(
            f"Pending: {stats.get('pending', 0)} | Failed: {stats.get('failed', 0)} | "
            f"Local (unassigned): {stats['unassigned']} | Other API: {stats['other_destination']}\n"
            f"Storage: {used:.0%} | Last upload: {last}"
            + (" | STORAGE WARNING" if used >= 0.8 else "")
        )

    def persist(self):
        try:
            save(self.config_path, self.config)
        except Exception:
            QMessageBox.critical(
                self, "Configuration", "Could not save configuration; check local storage"
            )

    def interval_changed(self, value):
        self.config.capture_interval_seconds = value
        self.persist()

    def change_changed(self, value):
        self.config.change_detection = value
        self.persist()

    def select_window(self):
        if self.pending_action or self.monitor.state != State.STOPPED:
            return
        candidates = self.desktop.candidates()
        labels = [
            f"{i + 1}. {t.title} — {t.executable} (PID {t.pid})" for i, t in enumerate(candidates)
        ]
        if not labels:
            QMessageBox.warning(self, "Target", "No accessible windows found")
            return
        label, ok = QInputDialog.getItem(
            self,
            "Select conversation",
            "Choose the authorized KakaoTalk conversation",
            labels,
            0,
            False,
        )
        if not ok:
            return
        if (
            QMessageBox.question(
                self,
                "Confirm target",
                "Confirm this is the intended KakaoTalk conversation and you have authorization to collect it.",
            )
            != QMessageBox.Yes
        ):
            return
        self.config.target = candidates[labels.index(label)]
        self.config.selection = None
        self.monitor.scroller.calibrated = False
        self.target_label.setText(f"Target: {self.config.target.title}")
        self.queue.event("target", "Operator selected target window")
        self.persist()

    def settings(self):
        if self.pending_action or self.monitor.state != State.STOPPED:
            return
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() != QDialog.Accepted:
            return
        stage = "validating settings"
        try:
            new = dialog.result_config
            new.validate()
            if dialog.token:
                stage = "saving the upload API token in Windows Credential Manager"
                set_token(new.api_url, dialog.token)
            if dialog.llm_token:
                from app.api.workflow_llm import LLMSettings, credential_destination

                stage = "saving the LLM API key in Windows Credential Manager"
                set_token(credential_destination(LLMSettings.resolve(new).url), dialog.llm_token)
            if dialog.bizgo_token:
                from app.api.bizgo_client import BIZGO_CREDENTIAL

                stage = "saving the Bizgo API key in Windows Credential Manager"
                set_token(BIZGO_CREDENTIAL, dialog.bizgo_token)
            # Do not access the Run registry key for ordinary settings saves when
            # sign-in launch was and remains disabled. Refresh the EXE path if enabled.
            if new.launch_at_signin or self.config.launch_at_signin:
                stage = "updating launch at sign-in"
                configure_startup(new.launch_at_signin)
            stage = "writing the configuration file"
            save(self.config_path, new)
            # Workers share this object; settings are only editable while capture is stopped.
            self.config.__dict__.update(new.__dict__)
            self.refresh_storage_mode()
            self.log("Settings saved; queued captures keep their original destinations")
        except Exception as error:
            # Exception text may contain the submitted credential. Log only a
            # fixed stage, exception class, and numeric OS error code.
            code = getattr(error, "winerror", None) or getattr(error, "errno", None)
            diagnostic = type(error).__name__
            if type(code) is int:
                diagnostic += f", OS error {code}"
            message = (
                f"Settings save failed while {stage} ({diagnostic}). "
                "Settings were not applied. Keys saved before this step may already have changed. "
                "Reopen Settings and retry."
            )
            self.log(message)
            QMessageBox.critical(self, "Settings", message)

    def action(self, command):
        if command == "stop":
            self.action_generation += 1
            self.pending_action = None
            self.monitor.command("stop")
            return
        if command == "cancel_history":
            self.monitor.command(command)
            return
        if self.pending_action:
            return
        automatic_reply = command in ("send_test", "test_workflow", "incoming_test", "auto_catch")
        sending = automatic_reply or command == "bizgo_test"
        if sending and self.monitor.state == State.INITIALIZING:
            return
        if command != "bizgo_test":
            if command == "auto_catch" and self.monitor.state == State.AUTO_CATCHING:
                return
            if not self.config.target:
                self.select_window()
                if not self.config.target:
                    return
        if command == "bizgo_test":
            from app.api.bizgo_client import BizgoSettings

            try:
                BizgoSettings.resolve(self.config)
            except AgentError as error:
                QMessageBox.warning(self, "Bizgo settings required", str(error))
                return
        if command == "send_test":
            text = self.test_reply_edit.toPlainText()
            if (
                not text.strip()
                or len(text) > 2000
                or any(ord(c) < 32 and c not in "\r\n\t" for c in text)
            ):
                QMessageBox.warning(
                    self,
                    "Test reply",
                    "Enter a message of 1–2,000 characters without unsupported control characters",
                )
                return
            self.config.test_reply_text = text
            self.persist()
        if command == "incoming_test" and self.monitor.state == State.WAITING_FOR_MESSAGE:
            return
        if command in ("test_workflow", "incoming_test", "auto_catch"):
            from app.api.workflow_llm import LLMSettings

            try:
                LLMSettings.resolve(self.config)
            except AgentError as error:
                QMessageBox.warning(self, "LLM settings required", str(error))
                return
        if (
            command == "confirm_bottom"
            and QMessageBox.question(
                self,
                "Confirm latest position",
                "Confirm you have manually positioned the selected chat at its latest messages. Automatic recovery will still require verification.",
            )
            != QMessageBox.Yes
        ):
            return
        if command in (
            "start",
            "confirm_bottom",
            "up",
            "down",
            "preview",
            "save_local",
        ) and self.monitor.state not in (State.STOPPED, State.PAUSED):
            return
        if command == "history" and self.monitor.state != State.LIVE_MONITORING:
            return
        if sending:
            # Serialize sending after capture/navigation has stopped; no manual Stop step.
            self.monitor.command("stop")
        if command != "history":
            self.monitor.suspend_recovery()
        if command == "auto_catch":
            self.preview_label.clear()
            self.preview_label.setText("Preparing Run Agent (auto) screenshot preview")
            self.text_preview.clear()
            self.text_preview.show()
        self.pending_action = command
        self.action_generation += 1
        generation = self.action_generation
        self.send_test_button.setEnabled(False)
        self.test_reply_edit.setEnabled(False)
        self.test_workflow_button.setEnabled(False)
        self.bizgo_test_button.setEnabled(False)
        self.incoming_test_button.setEnabled(False)
        self.auto_catch_button.setEnabled(False)
        self.log(
            (
                "Sending one Bizgo sandbox sample (no phone delivery)"
                if self.config.bizgo_sandbox
                else "Sending one Bizgo production sample to the configured recipient"
            )
            if command == "bizgo_test"
            else "Starting Run Agent (auto): watch display changes, capture, extract text, process with the LLM, and reply in queue order. Ctrl+Shift+F12 cancels"
            if command == "auto_catch"
            else "Arming Workflow 2: wait for a new incoming message, reply once with [AI], then stop. Ctrl+Shift+F12 cancels"
            if command == "incoming_test"
            else "Starting one test workflow: capture, LLM extraction/summary, and automatic reply. Ctrl+Shift+F12 cancels"
            if command == "test_workflow"
            else "Sending test reply automatically: existing message-box contents will be replaced. Ctrl+Shift+F12 cancels"
            if command == "send_test"
            else "Action starts in 3 seconds. Bring the selected conversation to the foreground"
        )
        if automatic_reply:
            try:
                accepted = self.desktop.request_target_activation()
            except Exception as error:
                self.pending_action = None
                self.send_test_button.setEnabled(True)
                self.test_workflow_button.setEnabled(True)
                self.bizgo_test_button.setEnabled(True)
                self.incoming_test_button.setEnabled(True)
                self.auto_catch_button.setEnabled(True)
                reason = (
                    str(error)
                    if isinstance(error, AgentError)
                    else "Cannot verify target for activation"
                )
                self.log(reason + "; no reply sent")
                self.update_status(State.STOPPED.value, reason)
                return
            if not accepted:
                self.log(
                    "Windows did not accept the foreground request; the worker will recheck before any input"
                )
        if command != "bizgo_test":
            self.showMinimized()

        def execute():
            if (
                self.pending_action == command
                and generation == self.action_generation
                and not self.closing
            ):
                self.pending_action = None
                self.monitor.command(command)

        QTimer.singleShot(
            0 if command == "bizgo_test" else 250 if automatic_reply else 3000, execute
        )

    def retry(self):
        self.queue_action(
            self.uploader.retry,
            "Failed uploads reset",
            "Could not reset failed jobs; check local storage",
        )

    def can_review_replies(self, state):
        return (
            state in (State.STOPPED.value, State.PAUSED.value)
            and self.monitor.stop_input.is_set()
            and not self.monitor.auto_catch.active
            and not self.monitor.recoverable
            and not self.monitor.auto_focus_recovery
            and not self.pending_action
            and not self.closing
        )

    def review_text_replies(self):
        from app.automation.text_auto_catch import chat_queue_key

        if not self.can_review_replies(self.monitor.state.value) or not self.config.target:
            return
        if (
            QMessageBox.question(
                self,
                "Review uncertain replies",
                "Inspect the selected KakaoTalk chat first. Mark its uncertain reply attempts as handled "
                "without sending them again? Other queued captures will be retained. "
                "Start Run Agent (auto) afterward to process the remaining queue.",
            )
            == QMessageBox.Yes
        ):
            key = chat_queue_key(self.config)
            self.queue_action(
                lambda: self.monitor.auto_catch.jobs.resolve_review(key),
                "Uncertain replies marked handled; pending captures retained",
                "Could not update reply review; check local storage",
            )

    def queue_action(self, action, success, failure):
        # SQLite may wait for another transaction; never do that on Qt's event loop.
        if self.closing:
            return
        self.control_threads = [thread for thread in self.control_threads if thread.is_alive()]
        if self.control_threads:
            self.log("A queue action is already running")
            return

        def run():
            try:
                action()
                self.signals.activity.emit(success)
            except Exception:
                self.signals.activity.emit(failure)

        thread = threading.Thread(target=run, name="queue-control", daemon=False)
        self.control_threads.append(thread)
        thread.start()

    def bind_local(self):
        if not self.config.api_url:
            QMessageBox.warning(self, "API required", "Configure an upload URL first")
            return
        if (
            QMessageBox.question(
                self,
                "Assign captures",
                f"Assign all local captures, including manually saved screenshots, to:\n{self.config.api_url}\nThey can upload when local-only mode is off, using this endpoint's credential. Uploaded-image retention then applies.",
            )
            == QMessageBox.Yes
        ):
            destination, local_http = self.config.api_url, self.config.allow_local_http
            self.queue_action(
                lambda: self.queue.bind_local(destination, local_http),
                "Local captures assigned to the selected API",
                "Could not assign captures; check local storage",
            )

    def closeEvent(self, event):
        if (
            self.closing
            and not self.monitor.is_alive()
            and not self.uploader.is_alive()
            and not any(t.is_alive() for t in self.control_threads)
        ):
            self.hotkey.close()
            QApplication.instance().removeNativeEventFilter(self.hotkey)
            event.accept()
            return
        event.ignore()
        if self.closing:
            return
        self.closing = True
        self.pending_action = None
        self.monitor.command("stop")
        self.monitor.shutdown.set()
        self.uploader.shutdown.set()
        self.setEnabled(False)
        self.log("Shutting down; waiting for the current upload to finish")
        self.close_timer = QTimer(self)
        self.close_timer.timeout.connect(self.close)
        self.close_timer.start(200)
