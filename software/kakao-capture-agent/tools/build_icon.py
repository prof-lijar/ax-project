"""Package the approved logo as a multi-resolution Windows ICO (no artwork changes)."""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

ASSETS = Path(__file__).resolve().parents[1] / "app" / "assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def build():
    source = QImage(str(ASSETS / "voyageri.png"))
    if source.isNull() or source.width() != source.height():
        raise ValueError("Expected a square PNG logo")
    source = source.convertToFormat(QImage.Format_ARGB32)
    frames = []
    for size in SIZES:
        frame = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        if not frame.save(buffer, "PNG"):
            raise RuntimeError("Could not encode icon frame")
        buffer.close()
        frames.append(bytes(data))
    offset = 6 + 16 * len(SIZES)
    entries = []
    for size, data in zip(SIZES, frames):
        entries.append(
            struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        )
        offset += len(data)
    target = ASSETS / "voyageri.ico"
    target.write_bytes(struct.pack("<HHH", 0, 1, len(SIZES)) + b"".join(entries) + b"".join(frames))
    print(f"Created {target.name}: {len(SIZES)} sizes (16–256 px)")


if __name__ == "__main__":
    build()
