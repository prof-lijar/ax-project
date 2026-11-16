from dataclasses import asdict

import cv2
import numpy as np

from app.models import AgentError, TargetUnavailable


class ScreenCapture:
    def __init__(self, desktop):
        self.desktop = desktop

    def grab(self):
        import mss

        before = self.desktop.validate()
        # Construct inside the worker thread; works with older MSS backends too.
        with mss.mss() as capture:
            image = np.asarray(capture.grab(asdict(before)))[:, :, :3].copy()
        after = self.desktop.validate()
        if before != after:
            raise TargetUnavailable("Target moved during capture; frame discarded")
        if image.shape[:2] != (before.height, before.width):
            raise AgentError("Capture dimensions did not match the selected region")
        return image, before


def encode_png(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise AgentError("PNG encoding failed")
    return encoded.tobytes()
