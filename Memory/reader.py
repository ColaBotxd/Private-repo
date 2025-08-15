# memory/reader.py
import json
import math
import threading
import time
from typing import Optional, Tuple, List, Union

import psutil

from .win_mem import ProcessHandle

Num = Union[int, str]

def _to_int(val: Num) -> int:
    # Accept "0x1234", "1234", or int
    if isinstance(val, int):
        return val
    s = str(val).strip()
    return int(s, 0)

class PointerSpec:
    def __init__(self, module: str, offsets: List[Num]):
        self.module = module
        self.offsets = [_to_int(x) for x in offsets]

class MemorySettings:
    def __init__(self, cfg: dict):
        self.process_name: str = cfg.get("process_name", "Wow.exe")
        self.module_hint: str  = cfg.get("module_hint", "Wow.exe")
        self.poll_hz: int      = int(cfg.get("poll_hz", 10))

        tcfg = cfg.get("types", {}) or {}
        self.pos_type: str     = str(tcfg.get("position", "float")).lower()
        self.hdg_degrees: bool = bool(tcfg.get("heading_degrees", True))

        self.ptr_x = PointerSpec(cfg["position_x_ptr"]["module"], cfg["position_x_ptr"]["offsets"])
        self.ptr_y = PointerSpec(cfg["position_y_ptr"]["module"], cfg["position_y_ptr"]["offsets"])
        self.ptr_h = PointerSpec(cfg["heading_ptr"]["module"],    cfg["heading_ptr"]["offsets"])

class MemoryReader:
    def __init__(self, settings: MemorySettings):
        self.s = settings
        self._lock = threading.Lock()
        self._pos: Optional[Tuple[float,float]] = None
        self._hdg: Optional[float] = None
        self._last_ts: float = 0.0
        self._running = False
        self._th: Optional[threading.Thread] = None

        self._ph: Optional[ProcessHandle] = None
        self._mod_bases: dict[str,int] = {}
        self._last_pos: Optional[Tuple[float,float]] = None
        self._last_hdg: Optional[float] = None

    # ---------- lifecycle ----------
    def start(self):
        if self._running: return
        self._running = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self):
        self._running = False

    # ---------- public getters ----------
    def sample(self) -> Tuple[Optional[Tuple[float,float]], Optional[float], float]:
        with self._lock:
            return self._pos, self._hdg, self._last_ts

    # ---------- internals ----------
    def _loop(self):
        # Burst-then-sleep pattern to reduce constant handle activity
        target_hz = max(2, int(self.s.poll_hz))
        burst_n = min(5, target_hz)      # up to 5 reads in a burst
        idle_dt = max(0.03, 1.0/target_hz) * 1.2

        while self._running:
            try:
                if not self._ph:
                    self._attach()
                    self._refresh_module_bases()

                for _ in range(burst_n):
                    self._tick_once()
                    time.sleep(max(0.01, 1.0/target_hz / burst_n))
            except Exception:
                try:
                    if self._ph: self._ph.close()
                except Exception:
                    pass
                self._ph = None
                self._mod_bases.clear()
                time.sleep(0.2)
            time.sleep(idle_dt)

    def _tick_once(self):
        assert self._ph is not None
        x = self._read_value(self.s.ptr_x)
        y = self._read_value(self.s.ptr_y)
        h = self._read_value(self.s.ptr_h)
        if x is None or y is None or h is None:
            return

        if not self.s.hdg_degrees:
            h = (h * 180.0 / math.pi)

        # Simple coherence: finite, reasonable deltas
        if math.isnan(x) or math.isnan(y) or math.isnan(h):
            return

        if self._last_pos is not None:
            dx = x - self._last_pos[0]
            dy = y - self._last_pos[1]
            if abs(dx) > 2000 or abs(dy) > 2000:
                # reject wild teleports from a bad pointer read
                return

        with self._lock:
            self._pos = (x, y)
            self._hdg = h % 360.0
            self._last_ts = time.time()
            self._last_pos = self._pos
            self._last_hdg = self._hdg

    def _attach(self):
        pid = self._find_pid_by_name(self.s.process_name)
        if pid is None:
            raise RuntimeError(f"Process '{self.s.process_name}' not found")
        self._ph = ProcessHandle(pid)

    def _find_pid_by_name(self, name: str) -> Optional[int]:
        for p in psutil.process_iter(['pid','name']):
            try:
                if (p.info['name'] or '').lower() == name.lower():
                    return int(p.info['pid'])
            except Exception:
                continue
        return None

    def _refresh_module_bases(self):
        if self._mod_bases:
            return
        assert self._ph is not None
        for base, nm, _sz in self._ph.list_modules():
            self._mod_bases[nm] = base

    def _module_base(self, name_hint: str) -> int:
        if name_hint in self._mod_bases:
            return self._mod_bases[name_hint]
        for k,v in self._mod_bases.items():
            if k.lower() == name_hint.lower():
                return v
        raise RuntimeError(f"Module '{name_hint}' not found in target process")

    def _read_value(self, spec: PointerSpec) -> Optional[float]:
        assert self._ph is not None
        base = self._module_base(spec.module)
        addr = self._ph.resolve_ptr_chain(base, spec.offsets)
        if self.s.pos_type == "double":
            return float(self._ph.read_double(addr))
        else:
            return float(self._ph.read_float(addr))

# -------- convenience ----------
def load_settings(path: str) -> MemorySettings:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return MemorySettings(cfg)
