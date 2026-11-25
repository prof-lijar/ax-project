from copy import deepcopy
from functools import partial

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.branding import APP_NAME, application_icon
from app.gui.i18n import translate
from app.gui.theme import apply_theme, card
from app.gui.theme import label as ui_label
from app.models import AgentError


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.text_for = partial(translate, config.language)
        t = self.text_for
        self.setWindowTitle(f"{t('Settings')} · {APP_NAME}")
        self.setWindowIcon(application_icon())
        self.result_config = deepcopy(config)
        self.token = ""
        self.llm_token = ""
        self.bizgo_token = ""
        self.operations_password = ""
        self.resize(780, 740)
        self.setMinimumSize(660, 520)
        apply_theme(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(ui_label(t("Settings"), "title"))
        layout.addWidget(
            ui_label(t("Configure capture, connected services, and startup behavior."))
        )
        language_row = QFormLayout()
        self.language = QComboBox()
        self.language.addItem("한국어", "ko")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(config.language))
        self.language.setAccessibleName(t("Language"))
        language_row.addRow(t("Language"), self.language)
        layout.addLayout(language_row)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName(t("Settings categories"))
        layout.addWidget(self.tabs, 1)
        self.forms = {}
        for title, description in [
            ("Capture", "Capture sensitivity, history navigation, and local storage."),
            ("AI replies", "Vision model connection and automatic reply timing."),
            ("Nexgent", "Connect the operations workflow to your Nexgent administrator account."),
            (
                "Bizgo",
                "Configure phone notifications. Sandbox requests do not deliver real messages.",
            ),
            ("Uploads", "Optional API destination for captured images."),
            ("Startup", "Choose what happens at sign-in and after interruptions."),
        ]:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            body = QWidget()
            body.setObjectName("workspace")
            page = QVBoxLayout(body)
            page.setContentsMargins(0, 14, 8, 0)
            section, section_layout = card(t(title), t(description))
            form = QFormLayout()
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            form.setHorizontalSpacing(18)
            form.setVerticalSpacing(16)
            section_layout.addLayout(form)
            page.addWidget(section)
            page.addStretch()
            scroll.setWidget(body)
            self.tabs.addTab(scroll, t(title))
            self.forms[title] = form
        self.controls = {}
        for name, label in [("chat_id", "Chat identifier"), ("api_url", "Upload URL")]:
            control = QLineEdit(getattr(config, name))
            if name == "chat_id":
                control.setPlaceholderText(t("Optional label; generated automatically when blank"))
                control.setToolTip(
                    t(
                        "A label attached to captures; generated automatically if blank, not a KakaoTalk ID."
                    )
                )
            self.add_control(name, label, control)
            self.controls[name] = control
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.secret.setPlaceholderText(t("Leave blank to keep the saved token"))
        self.add_control("api_token", "Bearer token", self.secret)
        for name, label, placeholder in [
            ("auto_reply_suffix", "Run Agent (auto) reply suffix", "(자동 응답)"),
            ("llm_url", "LLM base URL", "http://192.168.0.17:8000/v1"),
            ("llm_model", "Vision LLM model", "Use your server's image-capable model name"),
        ]:
            control = QLineEdit(getattr(config, name))
            control.setPlaceholderText(t(placeholder))
            self.add_control(name, label, control)
            self.controls[name] = control
        self.llm_secret = QLineEdit()
        self.llm_secret.setEchoMode(QLineEdit.Password)
        self.llm_secret.setPlaceholderText(
            t("Leave blank to keep saved key; OPENAI_API_KEY also supported")
        )
        self.add_control("llm_token", "LLM API key", self.llm_secret)
        for name, label, placeholder in [
            (
                "operations_url",
                "AX768 server or workbench URL",
                "http://192.168.0.18:5173/agents/ax768",
            ),
            ("operations_username", "Nexgent administrator username", ""),
        ]:
            control = QLineEdit(getattr(config, name))
            control.setPlaceholderText(t(placeholder))
            self.add_control(name, label, control)
            self.controls[name] = control
        self.operations_secret = QLineEdit()
        self.operations_secret.setEchoMode(QLineEdit.Password)
        self.operations_secret.setPlaceholderText(
            t("Leave blank to keep saved password; OPERATIONS_PASSWORD also supported")
        )
        self.add_control("operations_password", "Nexgent password", self.operations_secret)
        for name, label in [
            ("bizgo_sender", "Bizgo registered sender number"),
            ("bizgo_recipient", "Sample / Test Workflow recipient"),
            ("bizgo_test_recipients", "Installation test numbers (comma-separated)"),
        ]:
            control = QLineEdit(getattr(config, name))
            control.setPlaceholderText(t("e.g. 01012345678"))
            self.add_control(name, label, control)
            self.controls[name] = control
        self.bizgo_secret = QLineEdit()
        self.bizgo_secret.setEchoMode(QLineEdit.Password)
        self.bizgo_secret.setPlaceholderText(
            t("Leave blank to keep saved key; BIZGO_API_KEY also supported")
        )
        self.add_control("bizgo_token", "Bizgo API key", self.bizgo_secret)
        for name, label, low, high, decimals in [
            ("operations_timeout_seconds", "Operations workflow timeout (seconds)", 30, 900, 0),
            ("bizgo_timeout_seconds", "Bizgo request timeout (seconds)", 5, 120, 0),
            ("llm_timeout_seconds", "LLM operation timeout (seconds)", 5, 300, 0),
            (
                "auto_catch_interval_seconds",
                "Run Agent (auto) polling interval (seconds)",
                0.25,
                5,
                2,
            ),
            (
                "auto_reply_cooldown_seconds",
                "Run Agent (auto) pause between replies (seconds)",
                1,
                60,
                1,
            ),
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
            self.add_control(name, label, control)
            self.controls[name] = control
        self.storage = QDoubleSpinBox()
        self.storage.setRange(0.01, 1024)
        self.storage.setValue(config.storage_limit_bytes / 1024**3)
        self.add_control("storage_limit_bytes", "Storage budget (GiB)", self.storage)
        for name, label in [
            ("operations_allow_http", "Allow Nexgent HTTP on trusted LAN/localhost"),
            ("bizgo_enabled", "Send Bizgo SMS/LMS after Test Workflow"),
            (
                "bizgo_installation_test",
                "Send installation and guardian-addition guides to test numbers only",
            ),
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
            self.add_control(name, label, control)
            self.controls[name] = control
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setProperty("role", "primary")
        buttons.button(QDialogButtonBox.Save).setText(t("Save settings"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_control(self, name, title, control):
        if name.startswith("operations_"):
            category = "Nexgent"
        elif name.startswith("bizgo_"):
            category = "Bizgo"
        elif name.startswith(("llm_", "auto_reply_", "auto_catch_", "incoming_")):
            category = "AI replies"
        elif name in ("api_url", "api_token", "allow_local_http", "local_only"):
            category = "Uploads"
        elif name in ("auto_resume", "launch_at_signin", "auto_start_monitoring"):
            category = "Startup"
        else:
            category = "Capture"
        title = self.text_for(title)
        control.setAccessibleName(title)
        if isinstance(control, (QSpinBox, QDoubleSpinBox)):
            control.setMinimumWidth(100)
        if isinstance(control, QCheckBox):
            # Wrapping labels keep long service descriptions within the dialog.
            caption = ui_label(title, "body")
            caption.setBuddy(control)
            self.forms[category].addRow(caption, control)
        else:
            self.forms[category].addRow(title, control)

    def accept(self):
        self.result_config.language = self.language.currentData()
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
            if self.operations_secret.text():
                from app.api.operations_client import OperationsSettings

                OperationsSettings.resolve(self.result_config)
        except (ValueError, AgentError) as error:
            QMessageBox.warning(self, self.text_for("Invalid settings"), self.text_for(str(error)))
            return
        self.token = self.secret.text().strip()
        self.llm_token = self.llm_secret.text().strip()
        self.bizgo_token = self.bizgo_secret.text().strip()
        self.operations_password = self.operations_secret.text()
        super().accept()
