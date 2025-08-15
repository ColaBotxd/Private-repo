# main.py — ProjectX First Run (with memory-ready gating + auto-Enter)

import tkinter as tk
from tkinter import ttk, filedialog
import json, os, time, secrets, psutil, threading, random, string
from statistics import mean

from core.launcher.user_manager import create_windows_user
from core.launcher.user_cleanup import delete_windows_user
from core.launcher.username_generator import generate_session_username
from core.launcher.session_cache import set_username
from core.launcher.user_launcher import run_as_user

from core.input import safe_keyboard as sk
from core.input.safe_keyboard import set_target_pid
from core.movement.path_runner import run_path, set_test_mode
from core.safety.watchdog import BotWatchdog
from utils.logger import start_logger, start_dev_logger, log, dev, stop as stop_logs
from utils.positioning import (
    get_current_position, get_current_heading,
    set_ocr_heartbeat, attach_live_ocr, attach_memory
)

# Optional OCR (kept, but you can ignore it)
try:
    from ocr.live_ocr import LiveOCR
except Exception:
    LiveOCR = None

# Memory reader
from memory.reader import load_settings as load_mem_settings, MemoryReader

CONFIG_PATH   = "config/session_test.json"
MEM_CFG_PATH  = "config/memory_settings.json"
OCR_CFG_PATH  = "config/ocr_settings.json"   # only used if Live via OCR is selected

# ----------------------- helpers -----------------------

def generate_win_password(length: int = 12) -> str:
    # ≤14 chars, alnum only → avoids NET USER prompt
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(max(8, min(14, length))))

def load_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default

cfg     = load_json(CONFIG_PATH); cfg.setdefault('launch_config', {})
ocr_cfg = load_json(OCR_CFG_PATH, default={"poll_hz": 10, "coords_region": {}, "heading_region": {}, "expect_degrees": True})

root = tk.Tk(); root.title("ProjectX - First Run"); root.geometry("760x640")

title = ttk.Label(root, text="ProjectX - First Run", font=("Segoe UI", 16)); title.pack(pady=8)

# Input source selector
mode_frame = ttk.Frame(root); mode_frame.pack(fill='x', padx=10)
ttk.Label(mode_frame, text="Input Source:").pack(side='left', padx=(0,6))
source_var = tk.StringVar(value=cfg.get('input_source', "Test Mode"))
source_dd = ttk.Combobox(mode_frame, textvariable=source_var,
                         values=["Test Mode","Live via Memory","Live via OCR"],
                         state="readonly", width=18)
source_dd.pack(side='left')

def save_config(c):
    os.makedirs("config", exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(c, f, indent=2)

def on_source_change(*_):
    cfg['input_source'] = source_var.get()
    save_config(cfg)
source_dd.bind("<<ComboboxSelected>>", on_source_change)

# Paths
path_frame = ttk.Frame(root); path_frame.pack(fill='x', padx=10, pady=(6,0))
game_path_var = tk.StringVar(value=cfg['launch_config'].get('game_exe',''))
test_app_var = tk.StringVar(value=cfg['launch_config'].get('test_app_exe','C:/Windows/System32/notepad.exe'))
ttk.Label(path_frame, text="Game EXE:").grid(row=0, column=0, sticky='w')
ttk.Entry(path_frame, textvariable=game_path_var, width=70).grid(row=0, column=1, sticky='we', padx=4)
def pick_game():
    p = filedialog.askopenfilename(title="Select Game EXE", filetypes=[("Executable","*.exe")])
    if p:
        game_path_var.set(p); cfg['launch_config']['game_exe'] = p; save_config(cfg)
ttk.Button(path_frame, text="Select...", command=pick_game).grid(row=0, column=2)

ttk.Label(path_frame, text="Test App:").grid(row=1, column=0, sticky='w')
ttk.Entry(path_frame, textvariable=test_app_var, width=70).grid(row=1, column=1, sticky='we', padx=4)
def pick_test():
    p = filedialog.askopenfilename(title="Select placeholder EXE (Test Mode)", initialfile="notepad.exe", filetypes=[("Executable","*.exe")])
    if p:
        test_app_var.set(p); cfg['launch_config']['test_app_exe'] = p; save_config(cfg)
ttk.Button(path_frame, text="Select...", command=pick_test).grid(row=1, column=2)

status = ttk.Label(root, text="Ready.", font=("Segoe UI", 10)); status.pack(pady=4)

tabs = ttk.Notebook(root); tabs.pack(fill='both', expand=True, padx=8, pady=8)
log_tab = ttk.Frame(tabs); tabs.add(log_tab, text="Log")
test_tab = ttk.Frame(tabs); tabs.add(test_tab, text="Testing / Monitoring")

log_box = tk.Text(log_tab, height=22, width=94, font=("Consolas", 9), state="disabled", relief="solid", bd=1); log_box.pack(fill='both', expand=True)
def gui_log_push(line: str):
    log_box.config(state="normal"); log_box.insert(tk.END, line + "\n"); log_box.see(tk.END); log_box.config(state="disabled")

test_box = tk.Text(test_tab, height=22, width=94, font=("Consolas", 9), state="disabled", relief="solid", bd=1, fg="#0a0"); test_box.pack(fill='both', expand=True)
def test_push(line: str):
    test_box.config(state="normal"); test_box.insert(tk.END, line + "\n"); test_box.see(tk.END); test_box.config(state="disabled")

btn_frame = ttk.Frame(root); btn_frame.pack(pady=6)
start_btn = ttk.Button(btn_frame, text="Start", width=18); stop_btn = ttk.Button(btn_frame, text="Stop", width=18)
start_btn.grid(row=0, column=0, padx=8); stop_btn.grid(row=0, column=1, padx=8)

username = password = None
watchdog = None
target_pid = None
_live_ocr = None
_mem_reader = None

# ---------- heartbeat for watchdog ----------
LAST_OCR_TS = 0.0
def _touch_ocr():
    import time as _t
    global LAST_OCR_TS
    LAST_OCR_TS = _t.time()
    set_ocr_heartbeat(LAST_OCR_TS)
# -------------------------------------------

def append_log(msg: str):
    log(msg); gui_log_push(msg)

def append_test(msg: str):
    dev(msg); test_push(msg)

def check_processes_for_user(user_name: str, exe_name: str):
    exes = set()
    for p in psutil.process_iter(['pid','name','username']):
        try:
            if p.info['username'] and p.info['username'].endswith(user_name):
                exes.add((p.info['name'] or "").lower())
        except Exception:
            continue
    want = [exe_name.lower(), 'battle.net.exe']
    return all(w in exes for w in want), exes

# --------- pre-run: wait for in-world via memory + auto-Enter --------------

def _samples_stable(samples, max_span_yards=3.0, min_span_time=1.8):
    """Return True if samples ([(t,(x,y),hdg),...]) are close and recent enough."""
    if not samples:
        return False
    if (samples[-1][0] - samples[0][0]) < min_span_time:
        return False
    # distance between first and last <= 3y (standing in place while world is loaded)
    x0,y0 = samples[0][1]
    x1,y1 = samples[-1][1]
    dist = ((x1-x0)**2 + (y1-y0)**2)**0.5
    return dist <= max_span_yards

def await_in_world_via_memory(get_sample, press_enter_func, timeout=180, poll_dt=0.2) -> bool:
    """
    Waits until memory reader returns stable (x,y,hdg) for a few seconds.
    Sends Enter every ~5s to pass character select / loading screens.
    get_sample: function -> (pos, hdg, ts)
    press_enter_func: function to tap Enter
    """
    append_log("⏳ Waiting for character to load (memory)…")
    t0 = time.time()
    last_enter = 0.0
    window = []  # list of (ts, (x,y), hdg)

    while time.time() - t0 < timeout:
        pos, hdg, ts = get_sample()
        now = time.time()

        # Periodically press Enter to pass char select
        if now - last_enter >= 5.0:
            try:
                press_enter_func()
                append_log("↩ Sent Enter (char select / loading).")
            except Exception:
                pass
            last_enter = now

        # Accept only fresh samples
        if pos and (hdg is not None) and (now - ts <= 1.0):
            window.append((ts, pos, hdg))
            # keep ~4 seconds of history
            window = [s for s in window if now - s[0] <= 4.0]
            if len(window) >= 8 and _samples_stable(window):
                append_log("🟢 Memory looks stable — character seems in world.")
                return True

        time.sleep(poll_dt)

    append_log("❌ Timed out waiting for in-world (memory).")
    return False

# ---------------------------------------------------------------------------

def start_bot():
    global username, password, watchdog, target_pid, _live_ocr, _mem_reader

    src = source_var.get()
    is_test = (src == "Test Mode")

    session_log = start_logger(
        log_dir="logs",
        mode=("test" if is_test else "live"),
        path_profile=cfg.get("path_profile", "profiles/valley_of_trials.json"),
        game_exe=cfg.get("launch_config", {}).get("game_exe", "unknown"),
        test_app_exe=cfg.get("launch_config", {}).get("test_app_exe", "unknown"),
    )
    append_log(f"Session log -> {session_log}")

    if is_test:
        dev_log = start_dev_logger(enabled=True, log_dir="logs")
        append_test(f"Developer log -> {dev_log}")

    username = generate_session_username()
    password = generate_win_password(12)
    set_username(username)
    append_log(f"▶️ Starting with user: {username}")

    if not create_windows_user(username, password):
        append_log("❌ Failed to create Windows user."); return

    exe = test_app_var.get() if is_test else game_path_var.get()
    if not exe or not os.path.isfile(exe):
        append_log("❌ Executable path invalid. Use 'Select...' to choose the correct EXE."); return

    run_as_user(username, password, exe)
    append_log(f"🚀 Launched: {exe}")

    # Find PID
    time.sleep(1.0)
    pid = None
    for p in psutil.process_iter(['pid','name','username']):
        try:
            if p.info['username'] and p.info['username'].endswith(username) and (p.info['name'] or "").lower() == os.path.basename(exe).lower():
                pid = p.info['pid']; break
        except Exception:
            pass
    if not pid:
        append_log("❌ Could not locate launched process PID."); stop_bot(); return

    set_target_pid(pid); target_pid = pid
    append_log(f"✅ Target PID: {pid}")

    # Attach live source if needed
    if src == "Live via Memory":
        try:
            settings = load_mem_settings(MEM_CFG_PATH)
            _mem_reader = MemoryReader(settings)
            _mem_reader.start()
            attach_memory(_mem_reader)
            append_log("🧠 Memory reader started.")
        except Exception as e:
            append_log(f"❌ Failed to start Memory reader: {e}")
            stop_bot(); return

        # PRE-RUN GATE: wait until character is in world (stable memory) while auto-pressing Enter
        ok = await_in_world_via_memory(
            get_sample=lambda: _mem_reader.sample(),
            press_enter_func=lambda: sk.safe_tap('enter'),
            timeout=180, poll_dt=0.2
        )
        if not ok:
            stop_bot(); return

    if src == "Live via OCR" and LiveOCR is not None:
        try:
            _live_ocr = LiveOCR(
                coords_region=ocr_cfg["coords_region"],
                heading_region=ocr_cfg["heading_region"],
                poll_hz=int(ocr_cfg.get("poll_hz", 10)),
                expect_degrees=bool(ocr_cfg.get("expect_degrees", True)),
            )
            _live_ocr.start()
            attach_live_ocr(_live_ocr)
            append_log("🧠 Live OCR started.")
        except Exception as e:
            append_log(f"❌ Failed to start Live OCR: {e}")
            stop_bot(); return

    # Readiness loop (now memory/OCR should already be good)
    ready_ticks = 0; start_wait = time.time()
    while True:
        if is_test:
            set_ocr_heartbeat(time.time()); ready = True
        else:
            try:
                pos = get_current_position()
                hd  = get_current_heading()
                ready = isinstance(pos, tuple) and isinstance(hd, (int, float))
                if ready: set_ocr_heartbeat(time.time())
            except Exception:
                ready = False

        if ready:
            ready_ticks += 1; append_log(f"In-world readiness tick {ready_ticks}/3")
            if ready_ticks >= 3: break

        if time.time() - start_wait > 60:
            append_log("❌ In-world readiness timed out."); stop_bot(); return
        time.sleep(0.5)

    # Distance guard
    try:
        with open(cfg.get('path_profile', 'profiles/valley_of_trials.json'), 'r', encoding='utf-8') as f:
            path = json.load(f)
        first = (path[0]['x'], path[0]['y'])
    except Exception as e:
        append_log(f"❌ Failed to load path: {e}"); stop_bot(); return

    cur = first if is_test else get_current_position()
    dist = ((cur[0]-first[0])**2 + (cur[1]-first[1])**2) ** 0.5
    append_log(f"Distance to start: {dist:.2f} yards")
    if dist > 30.0 and not is_test:
        append_log("🚨 Too far from path start (30y). Aborting."); stop_bot(); return

    # Movement mode & input bypass
    set_test_mode(is_test)
    sk.set_input_test_mode(is_test)

    # Watchdog ONLY in Live modes
    if not is_test:
        global LAST_OCR_TS
        watchdog = BotWatchdog(stop_callback=stop_bot, last_ocr_time_func=lambda: LAST_OCR_TS)
        watchdog.start()

    delay = random.uniform(1.0, 5.0); append_log(f"⏳ Adaptive start delay: {delay:.2f}s"); time.sleep(delay)

    try:
        append_log("🗺️  Starting path...")
        if is_test: append_log("=== TEST MODE ACTION STREAM ===")
        run_path(cfg.get('path_profile', 'profiles/valley_of_trials.json'))
        append_log("✅ Path complete.")
    except Exception as e:
        append_log(f"❌ Path run failed: {e}")
    finally:
        stop_bot()

def stop_bot():
    global username, watchdog, target_pid, _live_ocr, _mem_reader
    # stop inputs
    try: sk.set_input_test_mode(False)
    except Exception: pass

    # stop watchdog
    try:
        if watchdog: watchdog.stop()
    except Exception: pass

    # stop live sources
    try:
        if _live_ocr: _live_ocr.stop()
    except Exception: pass
    try:
        if _mem_reader: _mem_reader.stop()
    except Exception: pass

    # kill launched process
    try:
        if target_pid:
            p = psutil.Process(target_pid)
            for c in p.children(recursive=True):
                try: c.kill()
                except Exception: pass
            try: p.kill()
            except Exception: pass
            append_log(f"🛑 Killed target PID {target_pid}.")
    except Exception as e:
        append_log(f"⚠️ Could not kill target PID: {e}")

    # delete session user
    if username:
        append_log(f"🧹 Deleting user: {username}")
        try:
            delete_windows_user(username)
            append_log("✅ User deleted.")
        except Exception as e:
            append_log(f"⚠️ Failed to delete user: {e}")

    # close logs/UI
    try: stop_logs()
    except Exception: pass
    try: status.config(text="Stopped.")
    except Exception: pass
    try: root.after(100, root.destroy)
    except Exception: pass

# ---------- GUI buttons ----------
def on_start():
    status.config(text="Running...")
    start_btn.config(state="disabled"); stop_btn.config(state="normal")
    threading.Thread(target=start_bot, daemon=True).start()

def on_stop():
    stop_bot()
    start_btn.config(state="normal"); stop_btn.config(state="disabled")

start_btn.config(command=on_start); stop_btn.config(command=on_stop)
stop_btn.config(state="normal")

root.mainloop()
