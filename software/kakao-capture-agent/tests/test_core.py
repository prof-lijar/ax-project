import json

import numpy as np
import pytest

from app.capture.change_detector import ChangeDetector, displacement
from app.config import load, save, validate_endpoint
from app.models import (
    TRANSITIONS,
    Region,
    ReselectionRequired,
    Selection,
    State,
    covered_by_monitors,
)


def test_region_negative_origins_and_monitor_gap():
    monitors = [Region(-1920, 0, 1920, 1080), Region(0, 0, 1920, 1080)]
    assert covered_by_monitors(Region(-40, 20, 80, 100), monitors)
    assert not covered_by_monitors(Region(-40, -1, 80, 100), monitors)
    assert not covered_by_monitors(
        Region(-40, 20, 80, 100), [monitors[0], Region(20, 0, 1920, 1080)]
    )


def test_relative_region_tracks_movement_and_rejects_dpi_resize():
    selected = Selection(Region(10, 20, 80, 100), 300, 300, 144)
    monitors = [Region(-1920, 0, 3840, 1080)]
    assert selected.resolve(Region(-500, 50, 300, 300), 144, monitors) == Region(-490, 70, 80, 100)
    with pytest.raises(ReselectionRequired):
        selected.resolve(Region(-500, 50, 300, 300), 96, monitors)
    with pytest.raises(ReselectionRequired):
        selected.resolve(Region(-500, 50, 301, 300), 144, monitors)


def test_configuration_round_trip_and_validation(tmp_path, config):
    config.selection = Selection(Region(10, 20, 80, 100), 300, 300, 144)
    path = tmp_path / "config.json"
    save(path, config)
    assert load(path) == config
    assert "token" not in path.read_text()
    data = json.loads(path.read_text())
    data["capture_interval_seconds"] = 0
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load(path)


@pytest.mark.parametrize(
    "url,local",
    [
        ("http://example.com/captures", True),
        ("https://user:password@example.com", False),
        ("http://localhost/api", True),
        ("http://127.0.0.1/api", False),
        ("file:///tmp/capture", True),
    ],
)
def test_endpoint_rejects_unsafe_transport(url, local):
    with pytest.raises(ValueError):
        validate_endpoint(url, local)


def test_identical_and_negligible_changes(config):
    detector = ChangeDetector(config)
    black = np.zeros((100, 100, 3), dtype=np.uint8)
    assert detector.ready(black, 0)
    detector.accept(black)
    assert not detector.ready(black, 1)
    small = black.copy()
    small[0, 0] = 255
    assert not detector.ready(small, 2)
    assert detector.ready(np.full_like(black, 255), 3)


def test_changes_accumulate_against_accepted_frame(config):
    config.difference_threshold = 0.1
    config.pixel_threshold = 5
    detector = ChangeDetector(config)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    detector.accept(frame)
    frame[:5] = 255
    assert not detector.ready(frame, 1)
    frame[:20] = 255
    assert detector.ready(frame, 2)


def test_debounce_has_maximum_latency(config):
    config.debounce_seconds = 0.5
    detector = ChangeDetector(config)
    black = np.zeros((100, 100, 3), dtype=np.uint8)
    detector.accept(black)
    assert not detector.ready(black + 50, 0)
    assert not detector.ready(black + 100, 0.4)
    assert not detector.ready(black + 150, 0.8)
    assert detector.ready(black + 200, 1.1)


def test_displacement_and_textureless_rejection():
    image = np.random.default_rng(0).integers(0, 256, (300, 100, 3), dtype=np.uint8)
    dy, confidence = displacement(image, np.roll(image, 30, axis=0))
    assert dy == 30 and confidence > 0.9
    assert displacement(np.zeros_like(image), np.zeros_like(image)) == (0, 0.0)


def test_state_machine_has_no_direct_history_resume():
    assert State.LIVE_MONITORING not in TRANSITIONS[State.HISTORY_SCANNING]
    assert State.RESTORING_POSITION in TRANSITIONS[State.HISTORY_SCANNING]
    assert State.INITIALIZING in TRANSITIONS[State.PAUSED]


@pytest.mark.parametrize("text", [None, "", " ", "x" * 2001, "bad\x01text"])
def test_invalid_test_reply_configuration(text, config):
    config.test_reply_text = text
    with pytest.raises(ValueError, match="Test reply"):
        config.validate()


def test_legacy_config_defaults_to_korean(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"version": 1, "chat_id": "existing-chat"}')
    config = load(path)
    assert config.language == "ko"
    assert config.chat_id == "existing-chat"
    config.language = "en"
    save(path, config)
    assert load(path).language == "en"
