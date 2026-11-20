import ctypes
import logging
import threading
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextCursor
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.api.incoming_llm import RUN_AGENT_GREETING
from app.config import save
from app.gui.settings_dialog import SettingsDialog
from app.gui.theme import CapturePreview, apply_theme, card, label
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
        self.resize(1080, 860)
        self.setMinimumSize(820, 640)
        apply_theme(self)
        body = QWidget()
        body.setObjectName("workspace")
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)

        header = QHBoxLayout()
        brand = QLabel("K")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignCenter)
        brand.setFixedSize(48, 48)
        header.addWidget(brand)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("KakaoTalk Capture Agent", "title"))
        titles.addWidget(label("Capture conversations. Keep work moving."))
        header.addLayout(titles, 1)
        self.setup_buttons = []
        settings = QPushButton("Settings")
        settings.clicked.connect(self.settings)
        self.setup_buttons.append(settings)
        header.addWidget(settings)
        self.stop_button = self.command_button("Stop", "stop", "stop")
        self.stop_button.setToolTip("Stop capture and replies · Ctrl+Shift+F12")
        header.addWidget(self.stop_button)
        layout.addLayout(header)

        status_row = QHBoxLayout()
        self.state_label = label("Stopped")
        self.state_label.setObjectName("state")
        status_row.addWidget(self.state_label)
        self.status_detail = label("Select a conversation to get started.")
        status_row.addWidget(self.status_detail, 1)
        layout.addLayout(status_row)

        target, target_layout = card("Conversation")
        target_row = QHBoxLayout()
        self.target_label = label(
            f"Target: {config.target.title}" if config.target else "No conversation selected",
            "heading",
        )
        target_row.addWidget(self.target_label, 1)
        select = QPushButton("Select Window")
        select.clicked.connect(self.select_window)
        self.setup_buttons.append(select)
        target_row.addWidget(select)
        target_layout.addLayout(target_row)
        layout.addWidget(target)

        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Workspace sections")
        layout.addWidget(self.tabs, 1)
        overview = self.add_tab("Overview")
        columns = QHBoxLayout()
        columns.setSpacing(16)
        overview.addLayout(columns, 1)
        preview_card, preview_layout = card(
            "Conversation preview", "The latest captured message area."
        )
        self.preview_tabs = QTabWidget()
        self.preview_tabs.setAccessibleName("Capture preview format")
        self.preview_label = CapturePreview()
        self.preview_tabs.addTab(self.preview_label, "Screenshot")
        preview_layout.addWidget(self.preview_tabs, 1)
        preview_layout.addWidget(self.command_button("Preview", "preview"))
        columns.addWidget(preview_card, 5)

        actions = QVBoxLayout()
        actions.setSpacing(14)
        columns.addLayout(actions, 4)
        auto_card, auto_layout = card(
            "Run your agent",
            "Watch new messages, extract text, and reply automatically in capture order.",
        )
        self.auto_catch_button = self.command_button("Run Agent (auto)", "auto_catch", "primary")
        auto_layout.addWidget(self.auto_catch_button)
        auto_layout.addWidget(
            label(
                "Sends a startup greeting, then replies until stopped. "
                "Each send replaces the chat’s draft. Keep the latest messages visible."
            )
        )
        self.auto_catch_button.setToolTip(f"Startup greeting: {RUN_AGENT_GREETING}")
        actions.addWidget(auto_card)
        device_card, device_layout = card("Device operations")
        self.device_workflow_button = self.command_button(
            "기기위치조정/전원연결", "device_workflow"
        )
        device_layout.addWidget(self.device_workflow_button)
        device_layout.addWidget(
            label(
                "이름 / 주소 / 작업을 보내주세요. 운영시트 처리 후 Bizgo 알림과 "
                "카카오톡 답장을 보냅니다. Stop을 누를 때까지 대기합니다."
            )
        )
        actions.addWidget(device_card)
        text_page = QWidget()
        text_layout = QVBoxLayout(text_page)
        text_layout.setContentsMargins(0, 8, 0, 0)
        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setAccessibleName("Latest extracted incoming text")
        self.text_preview.setPlaceholderText(
            "Text extracted from incoming captures will appear here."
        )
        self.text_preview.setMinimumHeight(80)
        text_layout.addWidget(self.text_preview, 1)
        self.review_text_button = QPushButton("Review Replies")
        self.review_text_button.clicked.connect(self.review_text_replies)
        text_layout.addWidget(self.review_text_button)
        self.preview_tabs.addTab(text_page, "Incoming text")
        actions.addStretch()
        signals.text_preview.connect(self.text_preview.setPlainText)
        signals.setup_ready.connect(self.persist)

        capture = self.add_tab("Capture")
        live_card, live = card("Live capture", "Collect screenshots at a regular interval.")
        row = QHBoxLayout()
        interval_label = label("Capture interval")
        row.addWidget(interval_label)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setSuffix(" sec")
        self.interval.setValue(config.capture_interval_seconds)
        self.interval.valueChanged.connect(self.interval_changed)
        interval_label.setBuddy(self.interval)
        row.addWidget(self.interval)
        self.change = QCheckBox("Detect visual changes")
        self.change.setChecked(config.change_detection)
        self.change.toggled.connect(self.change_changed)
        row.addWidget(self.change)
        row.addStretch()
        live.addLayout(row)
        live.addWidget(self.command_button("Start / Resume", "start", "primary"))
        live.addWidget(
            label(
                "The app minimizes before capture. Bring the selected chat forward within 3 seconds."
            )
        )
        capture.addWidget(live_card)
        history_card, history = card(
            "History & navigation", "Collect earlier messages or verify the latest position."
        )
        for commands in [
            [("Capture History", "history"), ("Cancel History", "cancel_history")],
            [
                ("Scroll Up", "up"),
                ("Scroll Down", "down"),
                ("Confirm Latest Position", "confirm_bottom"),
            ],
        ]:
            row = QHBoxLayout()
            for title, command in commands:
                row.addWidget(self.command_button(title, command))
            history.addLayout(row)
        capture.addWidget(history_card)
        local_card, local = card(
            "Local screenshots", "Save one PNG without assigning it to the upload API."
        )
        self.save_local_button = self.command_button("Save Capture Locally", "save_local")
        local.addWidget(self.save_local_button)
        open_folder = QPushButton("Open Captures Folder")
        open_folder.clicked.connect(self.open_captures_folder)
        local.addWidget(open_folder)
        self.capture_folder_label = label(f"PNG folder: {self.queue.images}")
        self.capture_folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        local.addWidget(self.capture_folder_label)
        capture.addWidget(local_card)
        capture.addStretch()

        tests = self.add_tab("Test tools")
        reply_card, reply = card(
            "Send a test reply", "Replaces the selected chat’s draft and sends your message once."
        )
        self.test_reply_edit = QPlainTextEdit(config.test_reply_text)
        self.test_reply_edit.setAccessibleName("Test reply message")
        self.test_reply_edit.setMaximumHeight(90)
        self.test_reply_edit.setPlaceholderText("Enter a message (up to 2,000 characters)")
        reply.addWidget(self.test_reply_edit)
        self.send_test_button = self.command_button("Send Test Reply", "send_test")
        reply.addWidget(self.send_test_button)
        tests.addWidget(reply_card)
        workflow_card, workflow = card(
            "Workflow checks",
            "These actions use configured services, including in local-only capture mode.",
        )
        self.test_workflow_button = self.command_button("Test Workflow", "test_workflow")
        workflow.addWidget(self.test_workflow_button)
        workflow.addWidget(
            label(
                "Capture → vision LLM → one [test] simulation reply. Includes Bizgo when enabled."
            )
        )
        self.incoming_test_button = self.command_button(
            "Test Workflow 2: Reply to Next Message", "incoming_test"
        )
        workflow.addWidget(self.incoming_test_button)
        workflow.addWidget(
            label("Wait for a new visible message, reply once with [AI], then stop. No Bizgo step.")
        )
        tests.addWidget(workflow_card)
        bizgo_card, bizgo = card("Phone notification")
        self.bizgo_test_button = self.command_button("Send Bizgo Sample", "bizgo_test")
        bizgo.addWidget(self.bizgo_test_button)
        self.bizgo_status = label("")
        bizgo.addWidget(self.bizgo_status)
        tests.addWidget(bizgo_card)
        tests.addStretch()

        uploads = self.add_tab("Storage / uploads")
        queue_card, queue_layout = card("Capture queue", "Saved captures and their upload status.")
        self.api_status = label("API: idle")
        queue_layout.addWidget(self.api_status)
        self.queue_label = label("Queue: loading", "heading")
        queue_layout.addWidget(self.queue_label)
        self.storage_bar = QProgressBar()
        self.storage_bar.setRange(0, 100)
        self.storage_bar.setValue(0)
        self.storage_bar.setTextVisible(False)
        self.storage_bar.setAccessibleName("Storage budget used")
        queue_layout.addWidget(self.storage_bar)
        row = QHBoxLayout()
        retry = QPushButton("Retry Failed Uploads")
        retry.clicked.connect(self.retry)
        row.addWidget(retry)
        bind = QPushButton("Assign Local Captures to API")
        bind.clicked.connect(self.bind_local)
        row.addWidget(bind)
        queue_layout.addLayout(row)
        queue_layout.addWidget(
            label(
                "Local captures stay on this computer until you explicitly assign them to an API."
            )
        )
        uploads.addWidget(queue_card)
        uploads.addStretch()
        self.refresh_storage_mode()

        activity = self.add_tab("Activity")
        activity_card, activity_layout = card(
            "Activity log", "Recent capture, reply, and upload events. Times use your local clock."
        )
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setAccessibleName("Activity log")
        self.logs.setPlaceholderText("Activity will appear here as you use the agent.")
        self.logs.document().setMaximumBlockCount(300)
        activity_layout.addWidget(self.logs, 1)
        activity.addWidget(activity_card, 1)
        layout.addWidget(
            label("Emergency stop  ·  Ctrl+Shift+F12  ·  Mouse corner fail-safe for input")
        )
        signals.status.connect(self.update_status)
        signals.preview.connect(self.update_preview)
        signals.activity.connect(self.log)
        signals.upload.connect(self.upload_status)
        signals.stats.connect(self.show_stats)
        self.hotkey = EmergencyHotkey(lambda: self.action("stop"))
        QApplication.instance().installNativeEventFilter(self.hotkey)
        if not self.hotkey.registered:
            self.log("Emergency hotkey unavailable; Stop and mouse fail-safe remain available")
        self.update_status(self.monitor.state.value, "")

    def command_button(self, title, command, role=None):
        button = QPushButton(title)
        if role:
            button.setProperty("role", role)
        button.clicked.connect(lambda checked=False: self.action(command))
        return button

    def add_tab(self, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("workspace")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 16, 10, 0)
        layout.setSpacing(14)
        scroll.setWidget(body)
        self.tabs.addTab(scroll, title)
        return layout

    def log(self, message):
        # Treat log messages as text even when services include angle brackets.
        cursor = QTextCursor(self.logs.document())
        cursor.movePosition(QTextCursor.End)
        if not self.logs.document().isEmpty():
            cursor.insertBlock()
        cursor.insertText(time.strftime("[%H:%M:%S] ") + message)
        self.logs.setTextCursor(cursor)
        self.logs.ensureCursorVisible()
        logging.getLogger("kakao").info(message)

    def update_status(self, state, reason):
        self.state_label.setText(state.replace("_", " ").capitalize())
        self.state_label.setProperty(
            "tone",
            "paused"
            if state == State.PAUSED.value
            else "idle"
            if state == State.STOPPED.value
            else "active",
        )
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.status_detail.setText(
            reason
            or (
                "Choose an action when you’re ready."
                if self.config.target
                else "Select a conversation to get started."
            )
        )
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
        self.device_workflow_button.setEnabled(self.auto_catch_button.isEnabled())
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
        if not self.config.bizgo_recipient or not self.config.bizgo_sender:
            self.bizgo_status.setText(
                "Bizgo: set sender, recipient, and API key in Settings for phone notifications"
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
        self.preview_label.show_png(png)

    def upload_status(self, message):
        if self.config.local_only:
            self.refresh_storage_mode()
        else:
            self.api_status.setText("API: " + message)
        self.log(message)

    def show_stats(self, stats):
        if "error" in stats:
            self.storage_bar.setEnabled(False)
            self.queue_label.setText("Queue storage unavailable")
            return
        used = stats["bytes"] / self.config.storage_limit_bytes
        self.storage_bar.setEnabled(True)
        self.storage_bar.setValue(min(100, round(used * 100)))
        self.storage_bar.setToolTip(f"{used:.0%} of storage budget used")
        self.storage_bar.setProperty("warning", used >= 0.8)
        self.storage_bar.style().unpolish(self.storage_bar)
        self.storage_bar.style().polish(self.storage_bar)
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
            if getattr(dialog, "operations_password", ""):
                from app.api.operations_client import credential_destination

                stage = "saving the Nexgent password in Windows Credential Manager"
                set_token(
                    credential_destination(new.operations_url, new.operations_username),
                    dialog.operations_password,
                )
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
        automatic_reply = command in (
            "send_test",
            "test_workflow",
            "incoming_test",
            "auto_catch",
            "device_workflow",
        )
        sending = automatic_reply or command == "bizgo_test"
        if sending and self.monitor.state == State.INITIALIZING:
            return
        if command != "bizgo_test":
            if (
                command in ("auto_catch", "device_workflow")
                and self.monitor.state == State.AUTO_CATCHING
            ):
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
        if command in ("test_workflow", "incoming_test", "auto_catch", "device_workflow"):
            from app.api.workflow_llm import LLMSettings

            try:
                LLMSettings.resolve(self.config)
            except AgentError as error:
                QMessageBox.warning(self, "LLM settings required", str(error))
                return
        if command == "device_workflow":
            from app.api.bizgo_client import create_bizgo
            from app.api.operations_client import create_operations

            try:
                create_operations(self.config)
                create_bizgo(self.config, self.queue.event, force=True)
            except AgentError as error:
                QMessageBox.warning(self, "운영시트 / Bizgo settings required", str(error))
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
        if command in ("auto_catch", "device_workflow"):
            self.tabs.setCurrentIndex(0)
            self.preview_tabs.setCurrentIndex(0)
            self.preview_label.clear()
            self.preview_label.setText("Preparing Run Agent (auto) screenshot preview")
            self.text_preview.clear()
            self.text_preview.show()
        if command == "preview":
            self.tabs.setCurrentIndex(0)
            self.preview_tabs.setCurrentIndex(0)
        self.pending_action = command
        self.action_generation += 1
        generation = self.action_generation
        self.send_test_button.setEnabled(False)
        self.test_reply_edit.setEnabled(False)
        self.test_workflow_button.setEnabled(False)
        self.bizgo_test_button.setEnabled(False)
        self.incoming_test_button.setEnabled(False)
        self.auto_catch_button.setEnabled(False)
        self.device_workflow_button.setEnabled(False)
        self.log(
            (
                "Sending one Bizgo sandbox sample (no phone delivery)"
                if self.config.bizgo_sandbox
                else "Sending one Bizgo production sample to the configured recipient"
            )
            if command == "bizgo_test"
            else "Starting 기기위치조정/전원연결: incoming request → 운영시트에이젠트 → Bizgo test notification → KakaoTalk reply. Ctrl+Shift+F12 cancels"
            if command == "device_workflow"
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
                self.device_workflow_button.setEnabled(True)
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
        if not self.can_review_replies(self.monitor.state.value) or not self.config.target:
            return
        if (
            QMessageBox.question(
                self,
                "Review set-aside captures",
                "Inspect the selected KakaoTalk chat first. Mark its set-aside captures as handled "
                "without sending them again? Other queued captures will be retained. "
                "Run Agent (auto) can process other captures without resolving these items.",
            )
            == QMessageBox.Yes
        ):
            key = self.monitor.auto_catch.queue_key()
            self.queue_action(
                lambda: self.monitor.auto_catch.jobs.resolve_review(key),
                "Set-aside captures marked handled; pending captures retained",
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
