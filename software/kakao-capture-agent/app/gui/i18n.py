"""Translate interface text before inserting chat names, paths and other user data."""

from app.gui.korean import KOREAN


def translate(language, source, **values):
    template = KOREAN.get(source, source) if language == "ko" else source
    return template.format(**values) if values else template
