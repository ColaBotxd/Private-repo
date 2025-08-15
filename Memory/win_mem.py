# memory/win_mem.py
# Read-only Win32 process memory helpers (no injection). Requires admin for cross-session reads.

import ctypes
import ctypes.wintypes as wt
from typing import Optional, List, Tuple

# --- Win32 constants ---
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ           = 0x0010

class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", wt.LPVOID),
        ("SizeOfImage", wt.DWORD),
        ("EntryPoint",  wt.LPVOID),
    ]

# Kernel32 / Psapi
k32  = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("Psapi", use_last_error=True)

OpenProcess       = k32.OpenProcess
OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
OpenProcess.restype  = wt.HANDLE

CloseHandle       = k32.CloseHandle
CloseHandle.argtypes = [wt.HANDLE]
CloseHandle.restype  = wt.BOOL

ReadProcessMemory = k32.ReadProcessMemory
ReadProcessMemory.argtypes = [wt.HANDLE, wt.LPCVOID, wt.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
ReadProcessMemory.restype  = wt.BOOL

EnumProcessModulesEx = psapi.EnumProcessModulesEx
EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
EnumProcessModulesEx.restype  = wt.BOOL

GetModuleBaseNameW = psapi.GetModuleBaseNameW
GetModuleBaseNameW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
GetModuleBaseNameW.restype  = wt.DWORD

GetModuleInformation = psapi.GetModuleInformation
GetModuleInformation.argtypes = [wt.HANDLE, wt.HMODULE, ctypes.POINTER(MODULEINFO), wt.DWORD]
GetModuleInformation.restype  = wt.BOOL

LIST_MODULES_ALL = 0x03

# --- Process handle wrapper ---
class ProcessHandle:
    def __init__(self, pid: int):
        self.pid = int(pid)
        self.h   = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, self.pid)
        if not self.h:
            raise OSError(f"OpenProcess failed for PID {pid} (err={ctypes.get_last_error()})")

    def close(self):
        if self.h:
            CloseHandle(self.h)
            self.h = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # --- Modules ---
    def list_modules(self) -> List[Tuple[int, str, int]]:
        """Return [(base_address, module_name, size), ...]"""
        arr_len = 512
        needed  = wt.DWORD(0)
        while True:
            buf = (wt.HMODULE * arr_len)()
            ok = EnumProcessModulesEx(self.h, buf, ctypes.sizeof(buf), ctypes.byref(needed), LIST_MODULES_ALL)
            if not ok:
                raise OSError("EnumProcessModulesEx failed")
            if needed.value <= ctypes.sizeof(buf):
                count = needed.value // ctypes.sizeof(wt.HMODULE)
                mods = []
                for i in range(count):
                    hmod = buf[i]
                    name_buf = ctypes.create_unicode_buffer(260)
                    GetModuleBaseNameW(self.h, hmod, name_buf, 260)
                    mi = MODULEINFO()
                    GetModuleInformation(self.h, hmod, ctypes.byref(mi), ctypes.sizeof(mi))
                    base = ctypes.cast(mi.lpBaseOfDll, ctypes.c_size_t).value
                    size = int(mi.SizeOfImage)
                    mods.append((base, name_buf.value, size))
                return mods
            arr_len *= 2

    def find_module_base(self, name_hint: str) -> Optional[int]:
        name_hint_low = (name_hint or "").lower()
        for base, nm, _sz in self.list_modules():
            if nm.lower() == name_hint_low:
                return base
        return None

    # --- Reads ---
    def _read(self, addr: int, size: int) -> bytes:
        buf = (ctypes.c_ubyte * size)()
        read = ctypes.c_size_t(0)
        ok = ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
        if not ok or read.value != size:
            raise OSError(f"RPM failed at 0x{addr:016X} size={size} (err={ctypes.get_last_error()})")
        return bytes(buf)

    def read_uint64(self, addr: int) -> int:
        return int.from_bytes(self._read(addr, 8), "little", signed=False)

    def read_uint32(self, addr: int) -> int:
        return int.from_bytes(self._read(addr, 4), "little", signed=False)

    def read_float(self, addr: int) -> float:
        import struct
        return struct.unpack("<f", self._read(addr, 4))[0]

    def read_double(self, addr: int) -> float:
        import struct
        return struct.unpack("<d", self._read(addr, 8))[0]

    def resolve_ptr_chain(self, base_addr: int, offsets: list[int]) -> int:
        """64-bit style: (((base+o0)->)+o1 ... ) final address of value"""
        addr = base_addr + int(offsets[0])
        for off in offsets[1:-1]:
            ptr = self.read_uint64(addr)
            addr = ptr + int(off)
        return addr + int(offsets[-1])
