"""Prepare full screenshots for vision without changing stored capture evidence."""

import base64
import struct

from app.models import AgentError

MAX_IMAGE_BYTES = 20 * 1024**2
MAX_SOURCE_PIXELS = 16_000_000


def vision_image_url(png):
    """Double both dimensions once, using ordinary interpolation and lossless PNG."""
    if len(png) > MAX_IMAGE_BYTES:
        raise AgentError("Workflow image exceeds 20 MiB; make the chat window smaller")
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise AgentError("Cannot decode workflow screenshot as PNG")
    width, height = struct.unpack(">II", png[16:24])
    if not width or not height or width * height > MAX_SOURCE_PIXELS:
        raise AgentError(
            "Workflow screenshot exceeds the supported dimensions; make the chat window smaller"
        )
    # Response parsing also imports this module; only OCR needs native image libraries.
    import cv2
    import numpy as np

    from app.capture.screen_capture import encode_png

    try:
        frame = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[:2] != (height, width):
            raise AgentError("Cannot decode workflow screenshot as PNG")
        enlarged = cv2.resize(frame, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        prepared = encode_png(enlarged)
    except cv2.error as error:
        raise AgentError("Cannot enlarge workflow screenshot for vision") from error
    if len(prepared) > MAX_IMAGE_BYTES:
        raise AgentError("Enlarged workflow image exceeds 20 MiB; make the chat window smaller")
    return "data:image/png;base64," + base64.b64encode(prepared).decode("ascii")
