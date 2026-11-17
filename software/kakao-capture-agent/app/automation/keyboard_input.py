"""Native Enter input with the complete Win32 INPUT union and checked insertion."""

import ctypes

from app.models import AgentError


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_int32),
        ("dy", ctypes.c_int32),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_uint32),
        ("wParamL", ctypes.c_uint16),
        ("wParamH", ctypes.c_uint16),
    ]


class InputValue(ctypes.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", ctypes.c_uint32), ("value", InputValue)]


def press_enter(user, check):
    # Scan-code Return (0x1C), down then up, in one OS input batch.
    events = (Input * 2)()
    for event, flags in zip(events, (0x0008, 0x0008 | 0x0002)):
        event.type = 1  # INPUT_KEYBOARD
        event.ki = KeyboardInput(0, 0x1C, flags, 0, 0)
    user.SendInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(Input), ctypes.c_int]
    user.SendInput.restype = ctypes.c_uint32
    check()  # Cancellation, foreground, composer focus, and modifier checks immediately before input.
    inserted = user.SendInput(2, events, ctypes.sizeof(Input))
    if inserted != 2:
        if inserted == 1:
            user.SendInput(1, ctypes.byref(events[1]), ctypes.sizeof(Input))
            raise AgentError(
                "Enter was only partially inserted; delivery uncertain, no automatic retry"
            )
        raise AgentError("Windows rejected the Enter keypress; text remains in the message box")
