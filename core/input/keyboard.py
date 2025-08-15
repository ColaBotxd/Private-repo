# Windows key sending via keybd_event (simple & reliable for Test Mode)
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)

KEYEVENTF_KEYUP = 0x0002

# Minimal VK map for our use; extend as needed
VK_MAP = {
    'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44,
    'space': 0x20,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12,
}

# add letters 0-9 if you ever need them
for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    VK_MAP[ch.lower()] = ord(ch)
for d in "0123456789":
    VK_MAP[d] = ord(d)

def _vk(key: str) -> int:
    k = (key or "").lower().strip()
    if k not in VK_MAP:
        raise ValueError(f"Unknown key '{key}'")
    return VK_MAP[k]

def press_key(key: str):
    vk = _vk(key)
    user32.keybd_event(vk, 0, 0, 0)

def release_key(key: str):
    vk = _vk(key)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
