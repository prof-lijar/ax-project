import sys
from copy import deepcopy
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.workflow_llm import credential_destination
from app.config import load
from app.gui import main_window
from app.gui.i18n import translate
from app.models import State
from app.utils.windows import credential_name, get_token, set_token


def test_credential_writer_passes_unicode_and_reader_decodes(monkeypatch):
    stored = {}

    def write(item, flags):
        assert isinstance(item["CredentialBlob"], str)
        assert flags == 0
        stored[item["TargetName"]] = item["CredentialBlob"].encode("utf-16-le")

    monkeypatch.setitem(
        sys.modules,
        "win32cred",
        SimpleNamespace(
            CRED_TYPE_GENERIC=1,
            CRED_PERSIST_LOCAL_MACHINE=2,
            CredWrite=write,
            CredRead=lambda name, kind: {"CredentialBlob": stored[name]},
        ),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    destination = credential_destination("https://llm.test/v1")
    set_token(destination, "synthetic-key-한글")
    assert get_token(destination, "OPENAI_API_KEY") == "synthetic-key-한글"


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows Credential Manager")
def test_native_credential_roundtrip_and_replacement(monkeypatch):
    import win32cred

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    destination = "synthetic-settings-test:" + str(uuid4())
    try:
        for token in ("synthetic-key-한글", "replacement-key"):
            set_token(destination, token)
            assert get_token(destination, "OPENAI_API_KEY") == token
    finally:
        # Delete only the uniquely named synthetic credential created by this test.
        try:
            win32cred.CredDelete(credential_name(destination), win32cred.CRED_TYPE_GENERIC)
        except Exception as error:
            if getattr(error, "winerror", None) != 1168:
                raise


@pytest.mark.parametrize(
    "failure", [None, "upload", "llm", "bizgo", "operations", "startup", "file"]
)
def test_settings_save_stages_and_secret_redaction(config, tmp_path, monkeypatch, failure):
    config.language = "en"
    new = deepcopy(config)
    if failure:
        new.language = "ko"
    new.chat_id = "updated-chat"
    new.llm_url = "https://llm.test/v1"
    new.llm_model = "vision"
    new.llm_supports_vision = True
    new.operations_url = "https://nexgent.test"
    new.operations_username = "admin"
    new.launch_at_signin = failure == "startup"
    secret = "synthetic-never-log-this"
    dialog = SimpleNamespace(
        result_config=new,
        token=secret,
        llm_token=secret,
        bizgo_token=secret,
        operations_password=secret,
        exec=lambda: main_window.QDialog.Accepted,
    )
    logs, errors, writes, startup = [], [], [], []
    window = SimpleNamespace(
        ui=SimpleNamespace(text=partial(translate, config.language)),
        pending_action=None,
        monitor=SimpleNamespace(state=State.STOPPED),
        config=config,
        config_path=tmp_path / "config.json",
        log=logs.append,
        refresh_storage_mode=lambda: None,
        refresh_target_label=lambda: None,
    )
    monkeypatch.setattr(main_window, "SettingsDialog", lambda *a: dialog)
    monkeypatch.setattr(
        main_window.QMessageBox, "critical", lambda _, title, msg: errors.append(msg)
    )

    def fail():
        raise PermissionError(13, secret)

    def write(destination, token):
        kind = (
            "operations"
            if destination.startswith("operations:")
            else "bizgo"
            if destination.startswith("bizgo:")
            else "llm"
            if destination.startswith("llm:")
            else "upload"
        )
        if failure == kind:
            fail()
        writes.append((destination, token))

    def signin(enabled):
        startup.append(enabled)
        if failure == "startup":
            fail()

    monkeypatch.setattr(main_window, "set_token", write)
    monkeypatch.setattr(main_window, "configure_startup", signin)
    if failure == "file":
        monkeypatch.setattr(main_window, "save", lambda *a: fail())
    main_window.MainWindow.settings(window)
    assert secret not in " ".join(logs + errors)
    if failure:
        label = {
            "upload": "upload API token",
            "llm": "LLM API key",
            "bizgo": "Bizgo API key",
            "operations": "Nexgent password",
            "startup": "launch at sign-in",
            "file": "configuration file",
        }[failure]
        assert len(errors) == 1 and label in errors[0] and "OS error 13" in errors[0]
        assert config.language == "en"
        assert config.chat_id == "test-chat" and not window.config_path.exists()
    else:
        assert not errors and not startup  # Disabled startup needs no registry access.
        assert config.chat_id == load(window.config_path).chat_id == "updated-chat"
        assert len(writes) == 4
        assert writes[1][0] == credential_destination(new.llm_url)
        assert secret not in window.config_path.read_text()
