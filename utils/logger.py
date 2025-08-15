import os
import time
import threading
from datetime import datetime

_LOG_DIR = "logs"
_session_fp = None
_dev_fp = None
_lock = threading.Lock()
_started = False
_dev_enabled = False
_session_path = None
_dev_path = None

_run_meta = {
    "mode": "unknown",
    "path_profile": "unknown",
    "game_exe": "unknown",
    "test_app_exe": "unknown",
}

def _ts():
    return datetime.now().strftime("[%H:%M:%S]")

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def _open_file(path):
    return open(path, "a", encoding="utf-8")

def start_logger(log_dir="logs", mode="unknown",
                 path_profile="unknown", game_exe="unknown",
                 test_app_exe="unknown") -> str:
    global _LOG_DIR, _session_fp, _started, _session_path, _run_meta
    with _lock:
        if _started:
            return _session_path
        _LOG_DIR = log_dir or "logs"
        _ensure_dir(_LOG_DIR)
        stamp = datetime.now().strftime("session_%Y-%m-%d_%H-%M-%S")
        _session_path = os.path.join(_LOG_DIR, f"{stamp}.log")
        _session_fp = _open_file(_session_path)
        _run_meta.update({
            "mode": mode,
            "path_profile": path_profile,
            "game_exe": game_exe,
            "test_app_exe": test_app_exe,
        })
        _session_fp.write(f"{_ts()} === ProjectX Session Start ===\n")
        _session_fp.flush()
        _started = True
        return _session_path

def start_dev_logger(enabled=False, log_dir="logs") -> str | None:
    global _dev_enabled, _dev_path, _dev_fp
    with _lock:
        _dev_enabled = bool(enabled)
        if not _dev_enabled:
            return None
        _ensure_dir(log_dir)
        stamp = datetime.now().strftime("dev_%Y-%m-%d_%H-%M-%S")
        _dev_path = os.path.join(log_dir, f"{stamp}.log")
        _dev_fp = _open_file(_dev_path)
        _dev_fp.write(f"{_ts()} === ProjectX Developer Log (Test Mode) ===\n")
        _dev_fp.flush()
        return _dev_path

def log(message: str):
    line = f"{_ts()} {message}"
    print(line)
    with _lock:
        if _session_fp:
            _session_fp.write(line + "\n")
            _session_fp.flush()

def dev(message: str):
    if not _dev_enabled:
        return
    line = f"{_ts()} {message}"
    print(line)
    with _lock:
        if _dev_fp:
            _dev_fp.write(line + "\n")
            _dev_fp.flush()

def log_ocr_tick(pos, heading):
    if pos is None or heading is None:
        log("OCR: invalid reading")
    else:
        log(f"OCR pos=({pos[0]:.2f},{pos[1]:.2f}) heading={heading:.1f}°")

def stop():
    global _session_fp, _dev_fp, _started
    with _lock:
        if _session_fp:
            _session_fp.write(f"{_ts()} === ProjectX Session End ===\n")
            _session_fp.flush()
            _session_fp.close()
            _session_fp = None
        if _dev_fp:
            _dev_fp.write(f"{_ts()} === Developer Log End ===\n")
            _dev_fp.flush()
            _dev_fp.close()
            _dev_fp = None
        _started = False
