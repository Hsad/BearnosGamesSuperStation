import os
import sys

ARCADE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIBRATE_SCRIPT = os.path.join(ARCADE_DIR, "tools", "calibrate.py")

ENV_BASE = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": os.path.expanduser("~"),
    "USER": os.environ.get("USER", "hsad"),
    "SDL_VIDEODRIVER": "kmsdrm",
    "MESA_GL_VERSION_OVERRIDE": "3.3",
    "MESA_GLSL_VERSION_OVERRIDE": "330",
    "TERM": "linux",
}

def launch_game(app) -> None:
    from renderer import term_enter_alt_screen, term_leave_alt_screen

    games = app.game_list()
    if not games:
        return
    game = games[app.selected]

    term_leave_alt_screen()
    sys.stdout.flush()
    sys.stderr.flush()

    pid = os.fork()
    if pid == 0:
        # child
        try:
            if game.is_calibrate:
                argv = ["/usr/bin/python3", CALIBRATE_SCRIPT]
            else:
                launch_sh = os.path.join(game.directory, "launch.sh")
                argv = ["/bin/bash", launch_sh]
            env = {**ENV_BASE}
            os.execve(argv[0], argv, env)
        except Exception as e:
            print(f"exec failed: {e}", file=sys.stderr)
            os._exit(1)
    else:
        # parent: wait for child
        os.waitpid(pid, 0)
        term_enter_alt_screen()
