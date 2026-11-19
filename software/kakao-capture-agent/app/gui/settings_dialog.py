from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.models import AgentError


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture and API settings")
        self.result_config = deepcopy(config)
        self.token = ""
        self.llm_token = ""
        self.bizgo_token = ""
        self.resize(650, 700)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        layout.addWidget(scroll)
        form = QFormLayout(body)
        self.controls = {}
        for name, label in [("chat_id", "Chat identifier"), ("api_url", "Upload URL")]:
            control = QLineEdit(getattr(config, name))
            if name == "chat_id":
                control.setPlaceholderText("Optional label; generated automatically when blank")
                control.setToolTip(
                    "A label attached to captures; generated automatically if blank, not a KakaoTalk ID."
                )
            form.addRow(label, control)
            self.controls[name] = control
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.secret.setPlaceholderText("Leave blank to keep the saved token")
        form.addRow("Bearer token", self.secret)
        for name, label, placeholder in [
            ("auto_reply_suffix", "Auto Catch reply suffix", "(자동 응답)"),
            ("llm_url", "LLM base URL", "http://192.168.0.17:8000/v1"),
            ("llm_model", "Vision LLM model", "Use your server's image-capable model name"),
        ]:
            control = QLineEdit(getattr(config, name))
            control.setPlaceholderText(placeholder)
            form.addRow(label, control)
            self.controls[name] = control
        self.llm_secret = QLineEdit()
        self.llm_secret.setEchoMode(QLineEdit.Password)
        self.llm_secret.setPlaceholderText(
            "Leave blank to keep saved key; OPENAI_API_KEY also supported"
        )
        form.addRow("LLM API key", self.llm_secret)
        for name, label in [
            ("bizgo_sender", "Bizgo registered sender number"),
            ("bizgo_recipient", "Bizgo recipient phone number"),
        ]:
            control = QLineEdit(getattr(config, name))
            control.setPlaceholderText("e.g. 01012345678")
            form.addRow(label, control)
            self.controls[name] = control
        self.bizgo_secret = QLineEdit()
        self.bizgo_secret.setEchoMode(QLineEdit.Password)
        self.bizgo_secret.setPlaceholderText(
            "Leave blank to keep saved key; BIZGO_API_KEY also supported"
        )
        form.addRow("Bizgo API key", self.bizgo_secret)
        for name, label, low, high, decimals in [
            ("bizgo_timeout_seconds", "Bizgo request timeout (seconds)", 5, 120, 0),
            ("llm_timeout_seconds", "LLM operation timeout (seconds)", 5, 300, 0),
            ("auto_catch_interval_seconds", "Auto Catch polling interval (seconds)", 0.25, 5, 2),
            ("auto_reply_cooldown_seconds", "Auto Catch pause between replies (seconds)", 1, 60, 1),
            ("incoming_wait_timeout_seconds", "Workflow 2 waiting limit (seconds)", 30, 3600, 0),
            (
                "incoming_difference_threshold",
                "Incoming-message changed pixel fraction",
                0.0001,
                1,
                4,
            ),
            ("difference_threshold", "Changed pixel fraction", 0.0001, 1, 4),
            ("debounce_seconds", "Debounce (seconds)", 0, 10, 1),
            ("scroll_step", "Maximum wheel notches per step", 1, 10, 0),
            ("scroll_delay_ms", "Scroll settle time (ms)", 200, 10000, 0),
            ("max_scroll_steps", "History/restore step limit", 1, 500, 0),
            ("overlap_target_percent", "Minimum overlap (%)", 10, 90, 0),
            ("recovery_seconds", "Bottom recovery interval (seconds)", 5, 3600, 0),
            ("uploaded_retention_hours", "Uploaded image retention (hours)", 0, 8760, 0),
        ]:
            control = QDoubleSpinBox() if decimals else QSpinBox()
            if decimals:
                control.setDecimals(decimals)
            control.setRange(low, high)
            control.setValue(getattr(config, name))
            form.addRow(label, control)
            self.controls[name] = control
        self.storage = QDoubleSpinBox()
        self.storage.setRange(0.01, 1024)
        self.storage.setValue(config.storage_limit_bytes / 1024**3)
        form.addRow("Storage budget (GiB)", self.storage)
        for name, label in [
            ("bizgo_enabled", "Enable Bizgo SMS/LMS after the KakaoTalk workflow reply"),
            ("bizgo_sandbox", "Bizgo sandbox: test requests only, no real phone delivery"),
            ("llm_supports_vision", "Enable image input for this vision-capable LLM"),
            ("llm_allow_http", "Allow unencrypted LLM HTTP on trusted LAN/localhost"),
            ("local_only", "Local-only mode: save PNGs and pause uploads"),
            ("allow_local_http", "Allow loopback HTTP mock API"),
            ("auto_resume", "Resume after verified temporary interruption"),
            ("launch_at_signin", "Launch when I sign in"),
            ("auto_start_monitoring", "Start monitoring on sign-in launch"),
        ]:
            control = QCheckBox()
            control.setChecked(getattr(config, name))
            form.addRow(label, control)
            self.controls[name] = control
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        for name, control in self.controls.items():
            value = (
                control.isChecked()
                if isinstance(control, QCheckBox)
                else control.text().strip()
                if isinstance(control, QLineEdit)
                else control.value()
            )
            setattr(self.result_config, name, value)
        self.result_config.storage_limit_bytes = int(self.storage.value() * 1024**3)
        try:
            self.result_config.validate()
            if self.secret.text() and not self.result_config.api_url:
                raise ValueError("Enter an API URL before saving a token")
            if self.llm_secret.text().strip():
                from app.api.workflow_llm import LLMSettings

                LLMSettings.resolve(self.result_config)
        except (ValueError, AgentError) as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return
        self.token = self.secret.text().strip()
        self.llm_token = self.llm_secret.text().strip()
        self.bizgo_token = self.bizgo_secret.text().strip()
        super().accept()
