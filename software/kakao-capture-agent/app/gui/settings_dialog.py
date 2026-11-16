from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
)


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture and API settings")
        self.result_config = deepcopy(config)
        self.token = ""
        form = QFormLayout(self)
        self.controls = {}
        for name, label in [("chat_id", "Chat identifier"), ("api_url", "Upload URL")]:
            control = QLineEdit(getattr(config, name))
            form.addRow(label, control)
            self.controls[name] = control
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.secret.setPlaceholderText("Leave blank to keep the saved token")
        form.addRow("Bearer token", self.secret)
        for name, label, low, high, decimals in [
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
        form.addRow(buttons)

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
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return
        self.token = self.secret.text().strip()
        super().accept()
