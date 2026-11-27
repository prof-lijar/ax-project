import base64
import struct

import cv2
import numpy as np
import pytest

from app.api import vision_image
from app.capture.screen_capture import encode_png
from app.models import AgentError


def test_enlargement_preserves_full_frame_and_source_bytes():
    frame = np.zeros((63, 37, 3), dtype=np.uint8)
    frame[:31, :18] = (255, 0, 0)
    frame[:31, 18:] = (0, 255, 0)
    frame[31:, :18] = (0, 0, 255)
    frame[31:, 18:] = (255, 255, 255)
    png = encode_png(frame)
    original = bytes(png)
    url = vision_image.vision_image_url(png)
    prefix, data = url.split(",")
    assert prefix == "data:image/png;base64"
    enlarged = cv2.imdecode(np.frombuffer(base64.b64decode(data), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert enlarged.shape == (126, 74, 3)
    for y, x in ((8, 8), (8, 28), (50, 8), (50, 28)):
        np.testing.assert_array_equal(enlarged[y * 2, x * 2], frame[y, x])
    assert png == original


@pytest.mark.parametrize("png", [b"", b"not png", b"\x89PNG\r\n\x1a\n" + b"\0" * 24])
def test_invalid_image_is_rejected(png):
    with pytest.raises(AgentError, match="decode"):
        vision_image.vision_image_url(png)


def test_oversized_dimensions_rejected_before_decode(monkeypatch):
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 100000, 100000)
    monkeypatch.setattr(cv2, "imdecode", lambda *args: pytest.fail("must reject before decoding"))
    with pytest.raises(AgentError, match="dimensions"):
        vision_image.vision_image_url(png)


def test_enlarged_payload_limit_is_checked(frame, monkeypatch):
    png = encode_png(frame)
    monkeypatch.setattr(vision_image, "MAX_IMAGE_BYTES", len(png) + 1)
    with pytest.raises(AgentError, match="Enlarged workflow image"):
        vision_image.vision_image_url(png)
