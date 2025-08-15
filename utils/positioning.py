# utils/positioning.py
# Test-mode sim + Live attachment (OCR or Memory) + heartbeat

import time
from typing import Tuple, Optional

# --- heartbeat (used by watchdog) ---
_LAST_OCR_HEARTBEAT = 0.0
def set_ocr_heartbeat(ts: float | None = None):
    global _LAST_OCR_HEARTBEAT
    _LAST_OCR_HEARTBEAT = ts if ts is not None else time.time()

def get_last_ocr_time() -> float:
    return _LAST_OCR_HEARTBEAT

# --- Test-mode simulation state ---
_TEST_MODE = False
_sim_x = 0.0
_sim_y = 0.0
_sim_hdg = 90.0  # deg

def set_test_mode(v: bool):
    global _TEST_MODE
    _TEST_MODE = bool(v)

def reset_simulated_position(x: float, y: float, hdg_deg: float = 90.0):
    global _sim_x, _sim_y, _sim_hdg
    _sim_x, _sim_y, _sim_hdg = float(x), float(y), float(hdg_deg)

def advance_simulated_by(distance: float):
    import math
    global _sim_x, _sim_y
    r = math.radians(_sim_hdg)
    _sim_x += math.cos(r) * distance
    _sim_y += math.sin(r) * distance

def rotate_simulated_by(delta_deg: float):
    global _sim_hdg
    _sim_hdg = (_sim_hdg + delta_deg) % 360.0

# --- Live sources (attach exactly one) ---
_OCR = None   # object with .get() -> (pos, hdg, ts)
_MEM = None   # object with .sample() -> (pos, hdg, ts)

def attach_live_ocr(ocr_instance):
    """Inject a Live OCR instance (see ocr/live_ocr.py)."""
    global _OCR, _MEM
    _OCR = ocr_instance
    _MEM = None

def attach_memory(mem_reader):
    """Inject a MemoryReader instance (see memory/reader.py)."""
    global _MEM, _OCR
    _MEM = mem_reader
    _OCR = None

# --- Public getters ---
def get_current_position() -> Tuple[float, float]:
    if _TEST_MODE:
        return (_sim_x, _sim_y)
    if _MEM is not None:
        pos, _, ts = _MEM.sample()
        if pos is None:
            raise RuntimeError("Memory: position not ready")
        set_ocr_heartbeat(ts)
        return pos
    if _OCR is not None:
        pos, hdg, ts = _OCR.get()
        if pos is None:
            raise RuntimeError("OCR: position not ready")
        set_ocr_heartbeat(ts)
        return pos
    raise RuntimeError("No live source attached (neither Memory nor OCR)")

def get_current_heading() -> float:
    if _TEST_MODE:
        return _sim_hdg
    if _MEM is not None:
        _pos, hdg, ts = _MEM.sample()
        if hdg is None:
            raise RuntimeError("Memory: heading not ready")
        set_ocr_heartbeat(ts)
        return hdg
    if _OCR is not None:
        _pos, hdg, ts = _OCR.get()
        if hdg is None:
            raise RuntimeError("OCR: heading not ready")
        set_ocr_heartbeat(ts)
        return hdg
    raise RuntimeError("No live source attached (neither Memory nor OCR)")
