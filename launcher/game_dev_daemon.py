#!/usr/bin/env python3
"""
Game Dev Daemon — watches games/_queue/ for spec files and dispatches build jobs.

Dispatch modes (set in daemon_config.json):
  local          — run a local build agent script on this machine
  spark          — SSH to DGX Spark, run agent, SCP result back
  remote_generic — SSH to any host, same interface as spark
"""

import os
import sys
import json
import re
import time
import subprocess
import logging
import signal

ARCADE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_DIR    = os.path.join(ARCADE_DIR, "games", "_queue")
GAMES_DIR    = os.path.join(ARCADE_DIR, "games")
LOGS_DIR     = os.path.join(ARCADE_DIR, "logs")
CONFIG_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daemon_config.json")
PID_FILE     = os.path.join(LOGS_DIR, "game_dev_daemon.pid")

DEFAULT_CONFIG = {
    "dispatch_mode":      "spark",
    "spark_host":         "spark.local",
    "spark_user":         "arcade",
    "spark_agent_path":   "/home/arcade/arcade-builder/run_agent.sh",
    "result_pickup_path": "/home/arcade/arcade-builder/output/",
    "poll_interval_seconds": 30,
}


# ── Logging setup ───────────────────────────────────────────────────────────────

def _setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "game_dev_daemon.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout),
        ],
    )

log = logging.getLogger(__name__)


# ── Spec frontmatter helpers ────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> dict:
    """Parse YAML-ish frontmatter between --- delimiters. Returns key→value dict."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"')
    return result


def _set_status(path: str, old_status: str, new_status: str) -> bool:
    """Replace `status: old` with `status: new` in the spec file. Returns True on success."""
    try:
        with open(path) as f:
            text = f.read()
        new_text = text.replace(f"status: {old_status}", f"status: {new_status}", 1)
        if new_text == text:
            return False
        with open(path, "w") as f:
            f.write(new_text)
        return True
    except Exception as e:
        log.error("Failed to update status in %s: %s", path, e)
        return False


# ── Dispatch implementations ────────────────────────────────────────────────────

def _dispatch_local(spec_path: str, config: dict) -> bool:
    """
    Run a local build agent. The agent receives the spec path and must deposit
    the finished game into games/<slug>/. Returns True on success.

    Local mode invokes `claude -p` to generate the game directly.
    """
    try:
        meta = _parse_frontmatter(open(spec_path).read())
        slug = meta.get("slug", os.path.splitext(os.path.basename(spec_path))[0])
        dest = os.path.join(GAMES_DIR, slug)
        os.makedirs(dest, exist_ok=True)

        with open(spec_path) as f:
            spec_text = f.read()

        task_prompt = f"""\
You are a game developer. Build a complete arcade game from this spec.

{spec_text}

Create these files in {dest}/:
1. {slug}.py — complete pygame game, fullscreen 1920x1080
2. launch.sh — shell script that sets SDL env vars and runs the .py
3. meta.json — {{"title":"...","description":"...","players":"...","author":"generated","added":"{time.strftime('%Y-%m-%d')}"}}

Requirements:
- Python + pygame only, no external assets
- 4 players: joystick + JUMP + ATTACK buttons per player
- Controller layout: P1=arrow keys/lctrl/lalt, P2=rfgd/a/s, P3=ijkl/rctrl/rshift, P4=ynvu/b/e
- Exit on any player holding ATTACK+JUMP simultaneously
- No pygame.key.get_pressed() with range loops (breaks P1/P3)
- Use event-based input only
- Must not crash on launch

Write all files now. Do not explain, just write the code."""

        log.info("Dispatching local build for %s", slug)
        proc = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions",
             "--output-format", "json", task_prompt],
            capture_output=True, text=True, timeout=600,
            cwd=dest,
        )

        if proc.returncode != 0:
            log.error("Local agent failed (rc=%d): %s", proc.returncode, proc.stderr[:500])
            return False

        # Verify required files exist
        required = [f"{slug}.py", "launch.sh", "meta.json"]
        missing  = [f for f in required if not os.path.exists(os.path.join(dest, f))]
        if missing:
            log.error("Agent finished but files missing: %s", missing)
            return False

        # Make launch.sh executable
        os.chmod(os.path.join(dest, "launch.sh"), 0o755)
        log.info("Local build succeeded for %s", slug)
        return True

    except subprocess.TimeoutExpired:
        log.error("Local agent timed out (600s)")
        return False
    except Exception as e:
        log.error("Local dispatch error: %s", e)
        return False


def _dispatch_ssh(spec_path: str, config: dict) -> bool:
    """
    SSH to a remote host, copy the spec, run the agent, SCP the result back.
    Returns True on success.
    """
    host       = config.get("spark_host", "spark.local")
    user       = config.get("spark_user", "arcade")
    agent_path = config.get("spark_agent_path", "/home/arcade/arcade-builder/run_agent.sh")
    pickup     = config.get("result_pickup_path", "/home/arcade/arcade-builder/output/")
    target     = f"{user}@{host}"

    meta = _parse_frontmatter(open(spec_path).read())
    slug = meta.get("slug", os.path.splitext(os.path.basename(spec_path))[0])
    remote_spec = f"/tmp/{os.path.basename(spec_path)}"

    try:
        log.info("Copying spec to %s:%s", target, remote_spec)
        subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", spec_path, f"{target}:{remote_spec}"],
            check=True, timeout=30,
        )

        log.info("Running remote agent on %s", target)
        subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", target,
             f"bash {agent_path} {remote_spec}"],
            check=True, timeout=600,
        )

        remote_result = f"{pickup.rstrip('/')}/{slug}/"
        local_dest    = os.path.join(GAMES_DIR, slug)
        log.info("Copying result from %s:%s", target, remote_result)
        subprocess.run(
            ["scp", "-r", "-o", "StrictHostKeyChecking=no",
             f"{target}:{remote_result}", local_dest],
            check=True, timeout=60,
        )

        launch_sh = os.path.join(local_dest, "launch.sh")
        if os.path.exists(launch_sh):
            os.chmod(launch_sh, 0o755)

        log.info("SSH build succeeded for %s", slug)
        return True

    except subprocess.CalledProcessError as e:
        log.error("SSH dispatch failed: %s", e)
        return False
    except subprocess.TimeoutExpired:
        log.error("SSH dispatch timed out")
        return False
    except Exception as e:
        log.error("SSH dispatch error: %s", e)
        return False


def _dispatch(spec_path: str, config: dict) -> bool:
    mode = config.get("dispatch_mode", "spark")
    if mode == "local":
        return _dispatch_local(spec_path, config)
    elif mode in ("spark", "remote_generic"):
        return _dispatch_ssh(spec_path, config)
    else:
        log.error("Unknown dispatch_mode: %s", mode)
        return False


# ── Main daemon loop ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except FileNotFoundError:
        return DEFAULT_CONFIG
    except Exception as e:
        log.warning("Could not load daemon_config.json: %s — using defaults", e)
        return DEFAULT_CONFIG


def _find_queued(queue_dir: str) -> list[str]:
    """Return paths of spec files with status: queued."""
    found = []
    try:
        for fname in sorted(os.listdir(queue_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(queue_dir, fname)
            try:
                with open(path) as f:
                    text = f.read(512)
                meta = _parse_frontmatter(text)
                if meta.get("status") == "queued":
                    found.append(path)
            except Exception:
                pass
    except FileNotFoundError:
        pass
    return found


def _write_pid():
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid(sig=None, frame=None):
    try:
        os.unlink(PID_FILE)
    except FileNotFoundError:
        pass
    sys.exit(0)


def main():
    _setup_logging()
    _write_pid()
    signal.signal(signal.SIGTERM, _cleanup_pid)
    signal.signal(signal.SIGINT,  _cleanup_pid)

    log.info("Game Dev Daemon started (pid %d)", os.getpid())
    os.makedirs(QUEUE_DIR, exist_ok=True)

    try:
        while True:
            config  = _load_config()
            queued  = _find_queued(QUEUE_DIR)
            if queued:
                spec_path = queued[0]
                slug = os.path.splitext(os.path.basename(spec_path))[0]
                log.info("Processing spec: %s", slug)
                _set_status(spec_path, "queued", "building")
                success = _dispatch(spec_path, config)
                if success:
                    _set_status(spec_path, "building", "deployed")
                    log.info("Deployed: %s", slug)
                else:
                    _set_status(spec_path, "building", "failed")
                    log.error("Build failed for: %s", slug)
            time.sleep(config.get("poll_interval_seconds", 30))
    except Exception as e:
        log.exception("Daemon crashed: %s", e)
    finally:
        _cleanup_pid()


if __name__ == "__main__":
    main()
