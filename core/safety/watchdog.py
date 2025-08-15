import threading
import time
import keyboard as kb
from core.input.safe_keyboard import safe_release

PANIC_KEY = "pause"
WATCHDOG_TIMEOUT = 3.0

class BotWatchdog:
    def __init__(self, stop_callback, last_ocr_time_func):
        self.stop_callback = stop_callback
        self.last_ocr_time_func = last_ocr_time_func
        self.running = True

    def start(self):
        threading.Thread(target=self._panic_listener, daemon=True).start()
        threading.Thread(target=self._ocr_monitor, daemon=True).start()

    def _panic_listener(self):
        while self.running:
            if kb.is_pressed(PANIC_KEY):
                safe_release('w')
                safe_release('a')
                safe_release('d')
                self.stop_callback()
                self.running = False
            time.sleep(0.1)

    def _ocr_monitor(self):
        while self.running:
            if time.time() - self.last_ocr_time_func() > WATCHDOG_TIMEOUT:
                self.stop_callback()
                self.running = False
            time.sleep(0.5)

    def stop(self):
        self.running = False
