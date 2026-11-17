import hashlib
import os
import subprocess
import sys
from pathlib import Path


def credential_name(destination):
    return "KakaoCaptureAgent/" + hashlib.sha256(destination.encode()).hexdigest()


def get_token(destination, environment_variable="KAKAO_CAPTURE_API_TOKEN"):
    override = os.environ.get(environment_variable)
    if override:
        return override
    import win32cred

    try:
        item = win32cred.CredRead(credential_name(destination), win32cred.CRED_TYPE_GENERIC)
    except Exception:
        return ""
    blob = item["CredentialBlob"]
    return blob.decode("utf-16-le") if isinstance(blob, bytes) else blob


def set_token(destination, token):
    import win32cred

    win32cred.CredWrite(
        {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": credential_name(destination),
            "UserName": "capture-agent",
            "CredentialBlob": token.encode("utf-16-le"),
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        },
        0,
    )


def secure_directory(path):
    import ntsecuritycon
    import win32api
    import win32con
    import win32security

    path.mkdir(parents=True, exist_ok=True)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    acl = win32security.ACL()
    for sid in (user, system):
        acl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS, 3, ntsecuritycon.FILE_ALL_ACCESS, sid
        )
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None,
        None,
        acl,
        None,
    )


def configure_startup(enabled):
    import winreg

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            args = [sys.executable]
            if not getattr(sys, "frozen", False):
                args.append(str(Path(__file__).resolve().parents[1] / "main.py"))
            args.append("--startup")
            winreg.SetValueEx(
                key, "KakaoCaptureAgent", 0, winreg.REG_SZ, subprocess.list2cmdline(args)
            )
        else:
            try:
                winreg.DeleteValue(key, "KakaoCaptureAgent")
            except FileNotFoundError:
                pass


def single_instance():
    import win32api
    import win32event

    handle = win32event.CreateMutex(None, False, r"Local\KakaoCaptureAgent")
    if win32api.GetLastError() == 183:
        handle.Close()
        raise RuntimeError("KakaoTalk Capture Agent is already running in this session")
    return handle
