import cv2
import numpy as np


def gray(image):
    return cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 0)


def difference(a, b, pixel_threshold=20):
    if a.shape != b.shape:
        return 1.0
    return float(np.count_nonzero(cv2.absdiff(a, b) > pixel_threshold) / a.size)


class ChangeDetector:
    def __init__(self, config):
        self.config = config
        self.baseline = None
        self.candidate = None
        self.first_change = self.stable_since = None

    def ready(self, image, now):
        current = gray(image)
        if self.baseline is None or not self.config.change_detection:
            return True
        if (
            difference(self.baseline, current, self.config.pixel_threshold)
            < self.config.difference_threshold
        ):
            self.candidate = self.first_change = self.stable_since = None
            return False
        if self.first_change is None:
            self.first_change = self.stable_since = now
            self.candidate = current
        elif (
            difference(self.candidate, current, self.config.pixel_threshold)
            >= self.config.difference_threshold
        ):
            self.candidate, self.stable_since = current, now
        return (
            now - self.stable_since >= self.config.debounce_seconds
            or now - self.first_change >= self.config.max_debounce_seconds
        )

    def accept(self, image):
        # Call only AFTER durable enqueue succeeds.
        self.baseline = gray(image)
        self.candidate = self.first_change = self.stable_since = None


def displacement(before, after):
    """Estimate vertical content translation; return (pixels, confidence).

    Match the central strip at multiple vertical offsets, ignoring side chrome.
    Textureless images deliberately have no movement confidence.
    """
    a, b = gray(before), gray(after)
    if a.shape != b.shape or min(a.shape) < 32:
        return 0, 0.0
    h, w = a.shape
    strip = a[h // 3 : 2 * h // 3, w // 10 : 9 * w // 10]
    if float(strip.std()) < 3:
        return 0, 0.0
    scores = cv2.matchTemplate(b[:, w // 10 : 9 * w // 10], strip, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, location = cv2.minMaxLoc(scores)
    return location[1] - h // 3, float(confidence)
