import os
import json
import struct
import select
import glob
from dataclasses import dataclass
from enum import IntEnum

# evdev input_event: struct { i64 tv_sec, i64 tv_usec, u16 type, u16 code, i32 value }
EVDEV_FMT = "qqHHi"
EVDEV_SIZE = struct.calcsize(EVDEV_FMT)
EV_KEY = 1

class Action(IntEnum):
    NONE   = 0
    LEFT   = 1
    RIGHT  = 2
    UP     = 3
    DOWN   = 4
    ATTACK = 5
    JUMP   = 6

@dataclass
class ActionEvent:
    player: int
    action: Action

# SDL keycode → Linux evdev keycode
SDL_TO_EVDEV = {
    1073741906: 103,  # UP
    1073741905: 108,  # DOWN
    1073741904: 105,  # LEFT
    1073741903: 106,  # RIGHT
    1073742050: 56,   # LALT
    1073742048: 29,   # LCTRL
    1073742053: 54,   # RSHIFT
    1073742052: 97,   # RCTRL
    97: 30,  98: 48,  99: 46,  100: 32, 101: 18, 102: 33, 103: 34,
    104: 35, 105: 23, 106: 36, 107: 37, 108: 38, 109: 50, 110: 49,
    111: 24, 112: 25, 113: 16, 114: 19, 115: 31, 116: 20, 117: 22,
    118: 47, 119: 17, 120: 45, 121: 21, 122: 44,
}

ACTION_NAMES = {"UP": Action.UP, "DOWN": Action.DOWN, "LEFT": Action.LEFT,
                "RIGHT": Action.RIGHT, "ATTACK": Action.ATTACK, "JUMP": Action.JUMP}

# Calibration combo: P1J P2J P3J P4J P4A P3A P2A P1A
COMBO = [
    (1, Action.JUMP),  (2, Action.JUMP),  (3, Action.JUMP),  (4, Action.JUMP),
    (4, Action.ATTACK),(3, Action.ATTACK),(2, Action.ATTACK),(1, Action.ATTACK),
]

def load_controllers(path: str) -> dict[int, tuple[int, Action]]:
    """Returns evdev_code -> (player, Action)"""
    mapping: dict[int, tuple[int, Action]] = {}
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return mapping

    for p in data.get("players", []):
        player_num = p["player"]
        for action_name, info in p.get("inputs", {}).items():
            if info.get("type") != "key":
                continue
            sdl_key = info["key"]
            evdev_code = SDL_TO_EVDEV.get(sdl_key, sdl_key)
            action = ACTION_NAMES.get(action_name)
            if action is not None:
                mapping[evdev_code] = (player_num, action)
    return mapping

def open_input_devices() -> list[int]:
    fds = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            fds.append(fd)
        except OSError:
            pass
    return fds

def poll_input(fds: list[int], ctrl: dict[int, tuple[int, Action]],
               timeout_ms: int) -> list[ActionEvent]:
    if not fds:
        return []
    events = []
    try:
        ready, _, _ = select.select(fds, [], [], timeout_ms / 1000.0)
    except Exception:
        return []
    for fd in ready:
        while True:
            try:
                data = os.read(fd, EVDEV_SIZE)
            except BlockingIOError:
                break
            except OSError:
                break
            if len(data) < EVDEV_SIZE:
                break
            _, _, ev_type, code, value = struct.unpack(EVDEV_FMT, data)
            if ev_type == EV_KEY and value == 1:  # key down only
                if code in ctrl:
                    player, action = ctrl[code]
                    events.append(ActionEvent(player=player, action=action))
    return events

def advance_combo(idx: int, ev: ActionEvent) -> tuple[int, bool]:
    """Returns (new_idx, completed). Only ATTACK/JUMP advance combo."""
    if ev.action not in (Action.ATTACK, Action.JUMP):
        return idx, False
    expected_player, expected_action = COMBO[idx]
    if ev.player == expected_player and ev.action == expected_action:
        idx += 1
        if idx >= len(COMBO):
            return 0, True
        return idx, False
    else:
        return 0, False
