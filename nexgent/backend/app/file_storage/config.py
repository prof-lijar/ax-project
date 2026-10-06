from dataclasses import dataclass
import os
import re


@dataclass(frozen=True)
class StorageSettings:
    deployment: str = "default"
    max_file_bytes: int = 25 * 1024 * 1024
    max_batch_bytes: int = 100 * 1024 * 1024
    max_files: int = 20


def load_storage_settings() -> StorageSettings:
    deployment = os.getenv("FILE_STORAGE_DEPLOYMENT", os.getenv("AX_CHAT_DEPLOYMENT", "default"))
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", deployment):
        raise ValueError("FILE_STORAGE_DEPLOYMENT must be 1–64 letters, digits, underscores or hyphens")
    limits = [int(os.getenv(key, str(default))) for key, default in (
        ("FILE_STORAGE_MAX_FILE_BYTES", 25 * 1024 * 1024),
        ("FILE_STORAGE_MAX_BATCH_BYTES", 100 * 1024 * 1024),
        ("FILE_STORAGE_MAX_FILES", 20),
    )]
    if any(value <= 0 for value in limits):
        raise ValueError("File storage limits must be positive")
    return StorageSettings(deployment, *limits)
