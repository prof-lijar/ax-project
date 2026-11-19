"""Interpret composer readback without changing reply text verification."""


def composer_is_empty(text):
    # KakaoTalk may expose this input placeholder through native text readback.
    return text.strip() in ("", "메시지 입력")
