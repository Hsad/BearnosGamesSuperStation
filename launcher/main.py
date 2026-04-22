#!/usr/bin/env python3
import time
import sys
import os
import subprocess

# Add launcher dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from games import scan_games, CALIBRATE_GAME, GAMES_DIR
from input_handler import (
    load_controllers, open_input_devices, poll_input, advance_combo,
    Action, ActionEvent
)
from renderer_gl import (
    get_terminal_size, term_enter_alt_screen, term_leave_alt_screen,
    render, render_boot, render_launching, render_screensaver, flicker_tick,
    clear_scene_cache, warm_next_scene_cache
)
from launch_game import launch_game
from game_creator import run_game_creator

ARCADE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROLLERS_JSON = os.path.join(ARCADE_DIR, "config", "controllers.json")
RESCAN_INTERVAL = 5.0
SCREENSAVER_TIMEOUT = 60.0
DISPLAY_OFF_TIMEOUT = 300.0  # 5 minutes after last input
WAKE_REQUIRED_DURATION = 5.0  # seconds of inputs needed to wake display
WAKE_GAP_TOLERANCE = 2.0      # reset wake attempt if no input for this long
DEV_MODE = os.environ.get("ARCADE_DEV") == "1"

def _source_mtimes() -> dict[str, float]:
    result = {}
    for f in os.listdir(LAUNCHER_DIR):
        if f.endswith(".py"):
            path = os.path.join(LAUNCHER_DIR, f)
            result[path] = os.stat(path).st_mtime
    return result

class App:
    def __init__(self):
        self.term_rows, self.term_cols = get_terminal_size()
        self._games = []
        self._calibrate_unlocked = False
        self.selected = 0
        self.combo_idx = 0
        self.last_refresh = 0.0
        self.ctrl = load_controllers(CONTROLLERS_JSON)
        self.fds = open_input_devices()
        self.state = "MENU"  # MENU | LAUNCHING
        self.last_input_time = time.monotonic()
        self.screensaver_active = False
        self.display_off = False
        self.wake_attempt_start: float | None = None
        self.last_wake_input_time: float | None = None

    def game_list(self):
        if self._calibrate_unlocked:
            return [CALIBRATE_GAME] + self._games
        return self._games

    def rescan(self):
        self._games = scan_games(GAMES_DIR)
        count = len(self.game_list())
        if count > 0 and self.selected >= count:
            self.selected = 0
        self.last_refresh = time.monotonic()

    def handle_event(self, ev: ActionEvent):
        self.last_input_time = time.monotonic()
        if self.screensaver_active:
            now = time.monotonic()
            if self.wake_attempt_start is None:
                self.wake_attempt_start = now
            self.last_wake_input_time = now
            return
        if self.state != "MENU":
            return

        if ev.action == Action.ATTACK:
            games = self.game_list()
            if games:
                game = games[self.selected]
                self.state = "LAUNCHING"
                if game.is_creator:
                    run_game_creator(self)
                else:
                    render_launching(self)
                    launch_game(self)
                while poll_input(self.fds, self.ctrl, timeout_ms=0):  # drain stale button events
                    pass
                self.state = "MENU"
                self.last_input_time = time.monotonic()
                self.term_rows, self.term_cols = get_terminal_size()
            return

        if ev.action == Action.LEFT:
            count = len(self.game_list())
            if count > 0:
                self.selected = (self.selected - 1) % count
            return

        if ev.action == Action.RIGHT:
            count = len(self.game_list())
            if count > 0:
                self.selected = (self.selected + 1) % count
            return

    def check_combo(self, ev: ActionEvent):
        if self._calibrate_unlocked:
            return
        # Only track combo when on game index 0 (first real game slot)
        real_selected = self.selected
        if self._calibrate_unlocked:
            real_selected = max(0, self.selected - 1)
        if real_selected != 0:
            self.combo_idx = 0
            return
        self.combo_idx, done = advance_combo(self.combo_idx, ev)
        if done:
            self._calibrate_unlocked = True
            self.selected = 0  # calibrate is now index 0

def _display_power(on: bool) -> None:
    devnull = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    # ddcutil talks to the monitor over DDC/I2C, bypasses DRM master restriction
    vcp_val = "1" if on else "4"
    if subprocess.call(["ddcutil", "setvcp", "D6", vcp_val], **devnull) == 0:
        return
    # fallback for older Pi / fkms setups
    subprocess.call(["vcgencmd", "display_power", "1" if on else "0"], **devnull)


def main():
    app = App()
    app.rescan()
    term_enter_alt_screen()
    app.term_rows, app.term_cols = get_terminal_size()
    mtimes = _source_mtimes() if DEV_MODE else {}
    try:
        render_boot(app)
        while True:
            now = time.monotonic()
            if now - app.last_refresh >= RESCAN_INTERVAL:
                old_count = len(app.game_list())
                app.rescan()
                new_count = len(app.game_list())
                if new_count != old_count:
                    clear_scene_cache()
                    render(app)

            if app.screensaver_active and app.wake_attempt_start is not None:
                if now - app.last_wake_input_time > WAKE_GAP_TOLERANCE:
                    app.wake_attempt_start = None
                    app.last_wake_input_time = None
                elif now - app.wake_attempt_start >= WAKE_REQUIRED_DURATION:
                    was_display_off = app.display_off
                    app.display_off = False
                    app.screensaver_active = False
                    app.wake_attempt_start = None
                    app.last_wake_input_time = None
                    if was_display_off:
                        _display_power(True)
                    render_boot(app, monitor_was_off=was_display_off)
                    app.last_input_time = time.monotonic()
                    while poll_input(app.fds, app.ctrl, timeout_ms=0):  # drain held buttons
                        pass

            if app.state == "MENU" and not app.display_off:
                idle = now - app.last_input_time
                if idle >= DISPLAY_OFF_TIMEOUT:
                    app.display_off = True
                    app.screensaver_active = True
                    _display_power(False)
                elif idle >= SCREENSAVER_TIMEOUT and not app.screensaver_active:
                    app.screensaver_active = True
                    render_screensaver()

            if app.state == "MENU" and not app.screensaver_active and not app.display_off:
                warm_next_scene_cache(app)

            flicker_tick()
            events = poll_input(app.fds, app.ctrl, timeout_ms=100)
            if events:
                for ev in events:
                    app.check_combo(ev)
                    app.handle_event(ev)
                if not app.screensaver_active:
                    render(app)

            if DEV_MODE and _source_mtimes() != mtimes:
                term_leave_alt_screen()
                os.execv(sys.executable, [sys.executable] + sys.argv)
    except KeyboardInterrupt:
        pass
    finally:
        term_leave_alt_screen()
        for fd in app.fds:
            try:
                os.close(fd)
            except Exception:
                pass

if __name__ == "__main__":
    main()
