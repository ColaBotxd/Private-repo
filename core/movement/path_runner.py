import json
import time
from utils.logger import log, dev
from utils import positioning as pos
from core.movement.navigation import move_to_waypoint

_TEST_MODE = False

def set_test_mode(v: bool):
    global _TEST_MODE
    _TEST_MODE = bool(v)
    pos.set_test_mode(_TEST_MODE)

def run_path(path_file: str):
    # load path
    with open(path_file, 'r', encoding='utf-8') as f:
        waypoints = json.load(f)
    if not waypoints or len(waypoints) < 2:
        raise ValueError("Path must contain at least 2 waypoints")

    # initialize simulated pose at first waypoint (facing east) for Test Mode
    if _TEST_MODE:
        start = waypoints[0]
        pos.reset_simulated_position(start['x'], start['y'], hdg_deg=0.0)  # 0° = east
        dev(f"[TEST] Sim start at ({start['x']:.1f},{start['y']:.1f}) hdg=0.0")

    # iterate waypoints
    for i in range(1, len(waypoints)):
        a = waypoints[i - 1]
        b = waypoints[i]
        log(f"➡ Waypoint {i}/{len(waypoints)-1} -> ({b['x']:.1f}, {b['y']:.1f})")
        move_to_waypoint((b['x'], b['y']))
        # optional small pause at points
        time.sleep(0.1)
