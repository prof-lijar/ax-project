"""Bounded decoding of an operator-selected capture; no desktop access."""

from pathlib import Path

import cv2
import numpy as np

from app.capture.screen_capture import encode_png
from app.models import AgentError

MAX_IMAGE_BYTES = 20 * 1024**2
MAX_IMAGE_PIXELS = 16_000_000


def normalize_capture_image(data):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage, QImageReader

    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise AgentError("Choose a PNG, JPEG or BMP capture no larger than 20 MiB")
    source = QBuffer()
    source.setData(QByteArray(data))
    source.open(QIODevice.ReadOnly)
    reader = QImageReader(source)
    reader.setDecideFormatFromContent(True)
    if bytes(reader.format()).lower() not in (b"png", b"jpeg", b"jpg", b"bmp"):
        raise AgentError("Unsupported image; choose a PNG, JPEG or BMP capture")
    size = reader.size()
    if size.width() < 32 or size.height() < 32 or size.width() * size.height() > MAX_IMAGE_PIXELS:
        raise AgentError("Capture must be at least 32 × 32 pixels and at most 16 megapixels")
    image = reader.read()
    if image.isNull():
        raise AgentError("Cannot decode this capture; choose a complete, valid image")
    # Canonical pixel encoding drops file metadata and is stable across repeated
    # imports, so the previewed image and its durable API receipts share one key.
    image = image.convertToFormat(QImage.Format_RGBA8888)
    pixels = (
        np.frombuffer(image.constBits(), dtype=np.uint8)
        .reshape(image.height(), image.bytesPerLine())[:, : image.width() * 4]
        .reshape(image.height(), image.width(), 4)
    )
    png = encode_png(cv2.cvtColor(pixels, cv2.COLOR_RGBA2BGRA))
    if len(png) > MAX_IMAGE_BYTES:
        raise AgentError("Capture exceeds 20 MiB as PNG; crop or resize it before testing")
    return png


def load_capture_image(path):
    try:
        with Path(path).open("rb") as file:
            data = file.read(MAX_IMAGE_BYTES + 1)
    except OSError:
        raise AgentError("Cannot read the selected capture image") from None
    return normalize_capture_image(data)
