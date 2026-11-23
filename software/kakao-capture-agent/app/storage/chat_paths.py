"""Stable chat identities and readable, Windows-safe capture directories."""

import hashlib
import json
import re
import unicodedata

from app.models import AgentError


def chat_queue_key(config):
    # Keep the existing identity format so pending queues and receipts survive upgrades.
    target = config.target
    identity = {
        "chat_id": config.chat_id,
        "title": getattr(target, "title", ""),
        "executable": getattr(target, "executable", ""),
        "class_name": getattr(target, "window_class", ""),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def chat_folder_name(config):
    if config.target is None:
        return None  # Legacy/programmatic captures without a selected window.
    title = unicodedata.normalize("NFC", config.target.title)
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", title).strip(" .")
    # Bound UTF-16 length on Windows, including astral characters and emoji.
    title = title.encode("utf-16-le")[:120].decode("utf-16-le", errors="ignore").rstrip(" .")
    title = title or "Chat"
    if title.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        title = "_" + title
    return title + "--" + chat_queue_key(config)[:12]


def chat_directory(root, folder):
    if folder is None:
        return root
    if (
        not isinstance(folder, str)
        or not re.fullmatch(r'[^<>:"/\\|?*\x00-\x1f\x7f]+--[0-9a-f]{12}', folder)
        or folder.startswith((".", " "))
    ):
        raise AgentError("Invalid chat capture folder; review required")
    path = root / folder
    if path.resolve() != root.resolve() / folder:
        raise AgentError("Chat capture folder was redirected; review required")
    return path


def capture_directories(root):
    """Legacy flat files and recognized chat folders; exclude other queue trees."""
    yield root
    for path in root.iterdir():
        if path.is_dir():
            try:
                directory = chat_directory(root, path.name)
            except AgentError:
                continue
            yield directory
