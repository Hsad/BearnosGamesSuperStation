#!/usr/bin/env python3
import time
import sys
import os
import subprocess
from datetime import datetime

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
    clear_scene_cache, warm_next_scene_cache, set_boot_volume
)
from launch_game import launch_game
from game_creator import run_game_creator
from game_editor import run_game_editor

ARCADE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROLLERS_JSON = os.path.join(ARCADE_DIR, "config", "controllers.json")
RESCAN_INTERVAL = 5.0
SCREENSAVER_TIMEOUT = 30.0
DISPLAY_OFF_TIMEOUT = 300.0  # 5 minutes after last input
WAKE_DURATION_MAX = 1.0   # wake hold required immediately after screensaver starts
WAKE_DURATION_MIN = 0.1   # floor after 6.5 hours of screensaver
WAKE_DECAY_PER_HR = 2.0   # seconds shed per hour
WAKE_GAP_TOLERANCE = 2.0  # reset wake attempt if no input for this long
HIDE_CHORD_WINDOW = 0.5       # P1-DOWN + P2-UP must arrive within this many seconds
DISPLAY_WAKE_DELAY = 7.0      # seconds after display power-on before showing boot (screen warm-up)
NIGHT_START_HOUR = 20         # 8pm: enter "always-awake" mode
NIGHT_END_HOUR = 6            # 6am: resume daytime sleep-on-idle
DEV_MODE = os.environ.get("ARCADE_DEV") == "1"

def _is_night_mode() -> bool:
    h = datetime.now().hour
    if NIGHT_START_HOUR <= NIGHT_END_HOUR:
        return NIGHT_START_HOUR <= h < NIGHT_END_HOUR
    return h >= NIGHT_START_HOUR or h < NIGHT_END_HOUR

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
        self.screensaver_start_time: float | None = None
        self.display_off = False
        self.display_power_on_time: float | None = None
        self.wake_attempt_start: float | None = None
        self.last_wake_input_time: float | None = None
        self._recent_actions: dict[tuple[int, Action], float] = {}
        self._was_night = False

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
                elif game.game_dev_status == "coming_soon":
                    run_game_editor(self, game)
                else:
                    render_launching(self)
                    launch_game(self)
                while poll_input(self.fds, self.ctrl, timeout_ms=0):  # drain stale button events
                    pass
                self.state = "MENU"
                self.last_input_time = time.monotonic()
                self.term_rows, self.term_cols = get_terminal_size()
            return

        if ev.action == Action.JUMP:
            games = self.game_list()
            if games:
                game = games[self.selected]
                if game.generated:
                    self.state = "LAUNCHING"
                    run_game_editor(self, game)
                    while poll_input(self.fds, self.ctrl, timeout_ms=0):
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

    def wake_duration(self) -> float:
        if self.screensaver_start_time is None:
            return WAKE_DURATION_MAX
        hours = (time.monotonic() - self.screensaver_start_time) / 3600
        return max(WAKE_DURATION_MIN, WAKE_DURATION_MAX - hours * WAKE_DECAY_PER_HR)

    def check_hide_chord(self, ev: ActionEvent) -> bool:
        """Returns True when P1-DOWN + P2-UP are pressed within HIDE_CHORD_WINDOW."""
        now = time.monotonic()
        key = (ev.player, ev.action)
        self._recent_actions[key] = now
        self._recent_actions = {k: t for k, t in self._recent_actions.items()
                                 if now - t <= HIDE_CHORD_WINDOW}
        if (self._recent_actions.get((1, Action.DOWN)) is not None and
                self._recent_actions.get((2, Action.UP)) is not None):
            self._recent_actions.clear()
            return True
        return False


def _display_power(on: bool) -> None:
    devnull = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    # ddcutil talks to the monitor over DDC/I2C, bypasses DRM master restriction
    vcp_val = "1" if on else "4"
    if subprocess.call(["ddcutil", "setvcp", "D6", vcp_val], **devnull) == 0:
        return
    # fallback for older Pi / fkms setups
    subprocess.call(["vcgencmd", "display_power", "1" if on else "0"], **devnull)

def main():
    sneaky = "--sneaky" in sys.argv
    silent = "--silent" in sys.argv
    _display_power(True)
    if silent:
        set_boot_volume(0.0)
    app = App()
    app.rescan()
    term_enter_alt_screen()
    app.term_rows, app.term_cols = get_terminal_size()
    mtimes = _source_mtimes() if DEV_MODE else {}
    try:
        if sneaky:
            app.screensaver_active = True
            app.screensaver_start_time = time.monotonic()
            render_screensaver()
        else:
            render_boot(app)
        while True:
            now = time.monotonic()
            night = _is_night_mode()
            if night and not app._was_night:
                if app.display_off:
                    _display_power(True)
                    app.display_off = False
                    time.sleep(DISPLAY_WAKE_DELAY)
                app.screensaver_active = False
                app.screensaver_start_time = None
                app.wake_attempt_start = None
                app.last_wake_input_time = None
                app.last_input_time = time.monotonic()
                if app.state == "MENU":
                    render(app)
            app._was_night = night

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
                elif now - app.wake_attempt_start >= app.wake_duration():
                    power_on_time = app.display_power_on_time
                    app.display_off = False
                    app.display_power_on_time = None
                    app.screensaver_active = False
                    app.screensaver_start_time = None
                    app.wake_attempt_start = None
                    app.last_wake_input_time = None
                    if power_on_time is not None:
                        remaining = DISPLAY_WAKE_DELAY - (time.monotonic() - power_on_time)
                        if remaining > 0:
                            time.sleep(remaining)
                    render_boot(app, monitor_was_off=(power_on_time is not None))
                    app.last_input_time = time.monotonic()
                    while poll_input(app.fds, app.ctrl, timeout_ms=0):  # drain held buttons
                        pass

            if app.state == "MENU" and not app.display_off and not night:
                idle = now - app.last_input_time
                if False and idle >= DISPLAY_OFF_TIMEOUT:
                    app.display_off = True
                    app.screensaver_active = True
                    app.screensaver_start_time = now
                    _display_power(False)
                elif idle >= SCREENSAVER_TIMEOUT and not app.screensaver_active:
                    app.screensaver_active = True
                    app.screensaver_start_time = now
                    render_screensaver()

            if app.state == "MENU" and not app.screensaver_active and not app.display_off:
                warm_next_scene_cache(app)

            flicker_tick()
            events = poll_input(app.fds, app.ctrl, timeout_ms=100)
            if events:
                if app.display_off:
                    app.display_off = False
                    app.display_power_on_time = time.monotonic()
                    _display_power(True)
                for ev in events:
                    if app.state == "MENU" and not app.screensaver_active and app.check_hide_chord(ev):
                        app.screensaver_active = True
                        app.screensaver_start_time = time.monotonic()
                        render_screensaver()
                        break
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
