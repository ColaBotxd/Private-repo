import time
import win32gui
import win32process
from core.input import keyboard

TARGET_PID = None
_TEST_MODE = False

def set_target_pid(pid: int):
    """Set the PID of the target process for key sending."""
    global TARGET_PID
    TARGET_PID = pid

def set_input_test_mode(v: bool):
    """
    Enable/disable Test Mode for input.
    When True, foreground checks are bypassed.
    """
    global _TEST_MODE
    _TEST_MODE = bool(v)

def _is_target_foreground() -> bool:
    """Check if the target PID is currently the foreground window."""
    if _TEST_MODE:
        return True
    if TARGET_PID is None:
        return False
    hwnd = win32gui.GetForegroundWindow()
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return pid == TARGET_PID

def safe_press(key: str):
    if _is_target_foreground():
        keyboard.press_key(key)

def safe_release(key: str):
    if _is_target_foreground():
        keyboard.release_key(key)

def safe_hold(key: str, duration: float):
    """
    Hold a key for the given duration if allowed.
    In Test Mode, clamp the duration to 1.0s max so Notepad doesn't get minute-long holds.
    """
    if _is_target_foreground():
        hold_time = min(duration, 1.0) if _TEST_MODE else duration
        keyboard.press_key(key)
        time.sleep(max(0.0, hold_time))
        keyboard.release_key(key)
