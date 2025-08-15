import math
import time
from utils.logger import log, dev
from core.input.safe_keyboard import safe_hold
from utils import positioning as pos

# Tunables
MOVE_SPEED_YDS = 7.0      # forward speed (yd/s)
TURN_SPEED_DPS = 200.0    # turn rate (deg/s)
DIST_EPSILON = 0.75       # yds: consider waypoint reached
HEADING_EPSILON = 5.0     # deg: consider facing good enough
MAX_STEP_TIME = 1.0       # s: break long moves/turns into small chunks (better logs/interruptibility)

def _angle_to(from_deg: float, to_deg: float) -> float:
    """Shortest signed angle (to - from) in degrees, range [-180,180]."""
    d = (to_deg - from_deg + 180.0) % 360.0 - 180.0
    return d

def _bearing_deg(from_xy, to_xy) -> float:
    """Compass bearing (0=east, 90=north)."""
    dx = to_xy[0] - from_xy[0]
    dy = to_xy[1] - from_xy[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return pos.get_current_heading()
    return (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0

def _turn(delta_deg: float):
    """Turn left(+)/right(-) by delta using A/D with simulated heading updates in Test Mode."""
    if abs(delta_deg) < 1e-3:
        return
    key = 'a' if delta_deg > 0 else 'd'
    dur = abs(delta_deg) / TURN_SPEED_DPS
    # Step small chunks so Stop can interrupt and sim heading updates are smooth
    remaining = dur
    while remaining > 1e-6:
        step = min(remaining, MAX_STEP_TIME)
        safe_hold(key, step)
        # update simulated heading (left is +)
        pos.rotate_simulated_by(math.copysign(step * TURN_SPEED_DPS, +1 if key == 'a' else -1))
        remaining -= step
    dev(f"Turn {key.upper()} for {dur:.2f}s (Δ={delta_deg:+.1f}°)")

def _walk(distance_yds: float):
    """Walk forward given distance, stepping in small chunks; updates simulated position."""
    if distance_yds <= 0:
        return
    dur = distance_yds / MOVE_SPEED_YDS
    remaining = dur
    while remaining > 1e-6:
        step = min(remaining, MAX_STEP_TIME)
        safe_hold('w', step)
        pos.advance_simulated_by(MOVE_SPEED_YDS * step)
        remaining -= step
    dev(f"Walk W for {dur:.2f}s (dist {distance_yds:.2f}y)")

def move_to_waypoint(target_xy):
    """Stop-turn-go toward a single waypoint with simulated odometry in Test Mode."""
    while True:
        cur = pos.get_current_position()
        hdg = pos.get_current_heading()
        dx = target_xy[0] - cur[0]
        dy = target_xy[1] - cur[1]
        dist = math.hypot(dx, dy)

        if dist <= DIST_EPSILON:
            log(f"✔ Reached waypoint ({target_xy[0]:.1f}, {target_xy[1]:.1f})")
            return

        bearing = _bearing_deg(cur, target_xy)
        delta = _angle_to(hdg, bearing)

        # Face target first
        if abs(delta) > HEADING_EPSILON:
            _turn(delta)
            continue  # re-evaluate distance/heading

        # Move forward some, then re-evaluate
        step_dist = min(dist, MOVE_SPEED_YDS * MAX_STEP_TIME)  # 1s worth of travel or remaining
        _walk(step_dist)
        # loop continues, using updated simulated pos/hdg
