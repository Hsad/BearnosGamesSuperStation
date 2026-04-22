#!/usr/bin/env python3
"""Game Creator screen — guided Q&A with Claude to spec out a new arcade game."""

import os
import sys
import json
import re
import threading
import time
import datetime
import subprocess

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from input_handler import poll_input, Action

ARCADE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_DIR     = os.path.join(ARCADE_DIR, "games", "_queue")
DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_dev_daemon.py")
LOGS_DIR      = os.path.join(ARCADE_DIR, "logs")

MAX_QUESTIONS   = 10
MAX_REGENERATES = 3
HOLD_WINDOW     = 0.8   # both buttons within this window = quit

SYSTEM_PROMPT = """\
You are the Game Creator for the Bearnos Arcade Cabinet. Help a player design a new arcade game.

Hardware: 4 players, 8-way joystick + 2 buttons (JUMP, ATTACK). 1920x1080 display.
Stack: Python + pygame only. No external assets.

Ask up to 10 questions to understand the game the player wants. Return ONLY valid JSON — no prose, no markdown fences.

For each question return exactly:
{"status":"question","question":"...","options":["A","B","C","D"]}

Exactly 4 options. Question: one sentence. Options: 2-5 words each.

When you have enough info (may be before 10 questions), return the complete spec:
{"status":"done","title":"...","slug":"...","players":"1-4","genre":"...","concept":"...","core_mechanic":"...","visual_style":"...","win_condition":"...","pacing":"...","tone":"...","notes":["..."],"build_constraints":["Python + pygame","No external assets required","Must launch cleanly and exit cleanly on ATTACK+JUMP"]}

Cover these areas (freely reorder/skip based on answers):
1. Core mechanic / genre
2. Number of players (1-4)
3. Visual theme / aesthetic
4. Win condition
5. Pacing / difficulty
6. Co-op vs competitive (if multiplayer)
7. Special mechanic or power-up
8. Tone (silly, tense, chaotic, chill)
9. Controls / game feel
10. Your wildcard"""

DUMMY_QR = [
    "███████████████████████",
    "█ ▄▄▄▄▄ █▄▀▀▄█ ▄▄▄▄▄ █",
    "█ █   █ █ ▄▀  █   █ █",
    "█ █▄▄▄█ ██▀▄█ █▄▄▄█ █",
    "█▄▄▄▄▄▄▄█▄█▄█▄▄▄▄▄▄▄▄█",
    "██▀▄▄█▀▄▄▄▀█ ▄▀▀▄▀█▄▀█",
    "█▀▀▄█▀▀▄▄▄ ▀▀▄▀▀▄▄▄▄▄█",
    "█ ▄▄▄▄▄ █▄ ▄▄▀▄▀▄▄▄▄ █",
    "█ █   █ █▀▀▄▄▀ ▀▀▄▄▀▀█",
    "█ █▄▄▄█ █▄▄▀▄▄▄▀▄▄▄▄▄█",
    "███████████████████████",
]


# ── Claude subprocess call ──────────────────────────────────────────────────────

def _call_claude(messages: list) -> dict:
    """Call `claude -p` with full conversation history. Returns parsed dict."""
    prompt = "\n".join(
        ("User: " if m["role"] == "user" else "Claude: ") + m["content"]
        for m in messages
    )
    try:
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json",
             "--system-prompt", SYSTEM_PROMPT, prompt],
            capture_output=True, text=True, timeout=90,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()[:300]
            return {"status": "error", "message": stderr or "claude subprocess failed"}
        outer = json.loads(proc.stdout)
        if outer.get("is_error"):
            return {"status": "error", "message": outer.get("result", "API error")}
        text = outer.get("result", "").strip()
        # Strip markdown fences if Claude wraps the JSON
        text = re.sub(r"^```[a-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
        return json.loads(text)
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Request timed out (90s)"}
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"JSON parse error: {e}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Spec file writer ────────────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:64] or "new-game"


def _write_spec(spec_data: dict) -> str:
    os.makedirs(QUEUE_DIR, exist_ok=True)
    slug    = spec_data.get("slug") or _slugify(spec_data.get("title", "new-game"))
    created = datetime.datetime.now().isoformat(timespec="seconds")
    notes   = "\n".join(f"- {n}" for n in spec_data.get("notes", []))
    constr  = "\n".join(f"- {c}" for c in spec_data.get("build_constraints", [
        "Python + pygame",
        "No external assets required",
        "Must launch cleanly and exit cleanly on ATTACK+JUMP",
    ]))
    content = f"""\
---
title: "{spec_data.get('title', 'Untitled')}"
slug: {slug}
players: {spec_data.get('players', '1-4')}
genre: {spec_data.get('genre', 'unknown')}
created: {created}
status: queued
---

## Game Concept

{spec_data.get('concept', '')}

## Core Mechanic

{spec_data.get('core_mechanic', '')}

## Visual Style

{spec_data.get('visual_style', '')}

## Win Condition

{spec_data.get('win_condition', '')}

## Pacing

{spec_data.get('pacing', '')}

## Tone

{spec_data.get('tone', '')}

## Notes

{notes}

## Build Constraints

{constr}
"""
    path = os.path.join(QUEUE_DIR, f"{slug}.md")
    with open(path, "w") as f:
        f.write(content)
    return path


# ── Daemon launcher ─────────────────────────────────────────────────────────────

def _ensure_daemon() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    pid_file = os.path.join(LOGS_DIR, "game_dev_daemon.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return  # already running
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
    log_path = os.path.join(LOGS_DIR, "game_dev_daemon.log")
    with open(log_path, "a") as log:
        proc = subprocess.Popen(
            [sys.executable, DAEMON_SCRIPT],
            stdout=log, stderr=log,
            close_fds=True, start_new_session=True,
        )
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))


# ── Spec display lines ──────────────────────────────────────────────────────────

def _build_spec_lines(spec_data: dict, cols: int) -> list:
    """Return [(text, color)] pairs for the scrollable spec view."""
    from renderer_gl import COL_CREAM, COL_SEPIA, COL_ACCENT, COL_DIM

    def wrap(text, w):
        words, lines, line = text.split(), [], ""
        for word in words:
            if len(line) + len(word) + (1 if line else 0) <= w:
                line += (" " if line else "") + word
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines or [""]

    max_w = int(cols * 0.68)
    out   = []

    title = spec_data.get("title", "Untitled")
    out.append((title.upper(), COL_CREAM))
    genre   = spec_data.get("genre", "")
    players = spec_data.get("players", "")
    out.append((f"{genre}  ·  {players} players", COL_DIM))
    out.append(("", COL_DIM))

    for section, key in [
        ("Concept",       "concept"),
        ("Core Mechanic", "core_mechanic"),
        ("Visual Style",  "visual_style"),
        ("Win Condition", "win_condition"),
        ("Pacing",        "pacing"),
        ("Tone",          "tone"),
    ]:
        val = spec_data.get(key, "").strip()
        if val:
            out.append((f"[ {section} ]", COL_ACCENT))
            for line in wrap(val, max_w):
                out.append(("  " + line, COL_SEPIA))
            out.append(("", COL_DIM))

    notes = spec_data.get("notes", [])
    if notes:
        out.append(("[ Notes ]", COL_ACCENT))
        for n in notes:
            out.append((f"  · {n}", COL_SEPIA))
        out.append(("", COL_DIM))

    out.append(("", COL_DIM))
    out.append(("  [ SCAN TO CONTINUE ON YOUR PHONE — COMING SOON ]", COL_DIM))
    for line in DUMMY_QR:
        out.append((line, COL_DIM))
    out.append(("", COL_DIM))
    return out


# ── Main entry point ────────────────────────────────────────────────────────────

def run_game_creator(app) -> None:
    """Take over the pygame display for the full Game Creator Q&A flow."""
    import renderer_gl as R
    from renderer import KHI_LOGO, SUBTEXT_1, SUBTEXT_2

    rows = R._term_rows
    cols = R._term_cols

    def surf():
        return R._starfield.copy()

    def dc(s, text, row, color):
        R._draw_centered(s, text, row, color)

    def d(s, text, row, col, color):
        R._draw(s, text, row, col, color)

    def finish(s):
        R._upload_scene(s)
        R._glow_tex.write(R._BLACK_GLOW)
        R._draw_frame()

    def header(s):
        for i, line in enumerate(KHI_LOGO):
            dc(s, line.strip(), i + 1, R.COL_CREAM)
        dc(s, SUBTEXT_1.strip(), 4, R.COL_CREAM)
        dc(s, SUBTEXT_2.strip(), 5, R.COL_CREAM)

    def footer(s, hint):
        d(s, ("═" * cols)[:cols], rows - 1, 1, R.COL_ACCENT)
        dc(s, hint, rows, R.COL_SEPIA)

    def wordwrap(text, max_w):
        words, lines, line = text.split(), [], ""
        for w in words:
            if len(line) + len(w) + (1 if line else 0) <= max_w:
                line += (" " if line else "") + w
            else:
                if line:
                    lines.append(line)
                line = w
        if line:
            lines.append(line)
        return lines or [""]

    # ── State ──────────────────────────────────────────────────────────────────
    state       = "LOADING"
    messages    = [{"role": "user",
                    "content": "Start the game creator. Ask me the first question."}]
    q_num       = 0
    current_q   = None
    sel         = 0
    regens_left = MAX_REGENERATES
    spec_data   = None
    error_msg   = ""
    scroll      = 0
    spec_lines  = []

    # Thread result slot
    _result:  list = [None]
    _loading: list = [True]
    _lock = threading.Lock()

    def start_api(msgs):
        with _lock:
            _result[0]  = None
            _loading[0] = True
        def worker():
            r = _call_claude(msgs)
            with _lock:
                _result[0]  = r
                _loading[0] = False
        threading.Thread(target=worker, daemon=True).start()

    start_api(list(messages))

    # Hold-both-to-quit tracking (key-down only, so use timestamps)
    last_attack: dict = {}
    last_jump:   dict = {}

    def check_quit(evs) -> bool:
        now = time.monotonic()
        for ev in evs:
            if ev.action == Action.ATTACK:
                last_attack[ev.player] = now
            elif ev.action == Action.JUMP:
                last_jump[ev.player] = now
        for p in range(1, 5):
            ta = last_attack.get(p, 0.0)
            tj = last_jump.get(p, 0.0)
            if ta > 0 and tj > 0 and abs(ta - tj) <= HOLD_WINDOW:
                if now - max(ta, tj) <= HOLD_WINDOW:
                    return True
        return False

    clock = pygame.time.Clock()

    while True:
        clock.tick(30)
        pygame.event.pump()
        events = poll_input(app.fds, app.ctrl, timeout_ms=0)

        if check_quit(events):
            break

        if state == "LOADING":
            # ── Loading frame ───────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "GAME  CREATOR", 7, R.COL_CREAM)
            dots = "·" * (int(time.monotonic() * 2) % 4 + 1)
            dc(s, f"[ Thinking {dots} ]", rows // 2, R.COL_ACCENT)
            footer(s, "Please wait ...")
            finish(s)

            with _lock:
                done = not _loading[0]
                r    = _result[0] if done else None

            if done:
                if r is None or r.get("status") == "error":
                    error_msg = r.get("message", "Unknown error") if r else "No response"
                    state = "ERROR"
                elif r["status"] == "question":
                    messages.append({"role": "assistant", "content": json.dumps(r)})
                    q_num      += 1
                    current_q   = r
                    sel         = 0
                    regens_left = MAX_REGENERATES
                    state       = "ASKING"
                elif r["status"] == "done":
                    messages.append({"role": "assistant", "content": json.dumps(r)})
                    spec_data  = r
                    _write_spec(r)
                    _ensure_daemon()
                    spec_lines = _build_spec_lines(r, cols)
                    state      = "SPEC_DISPLAY"

        elif state == "ASKING":
            # ── Question frame ──────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "GAME  CREATOR", 7, R.COL_CREAM)
            regen_str = "".join("≋" if i < regens_left else "·"
                                for i in range(MAX_REGENERATES))
            dc(s, f"QUESTION {q_num} / {MAX_QUESTIONS}    [{regen_str}]", 9, R.COL_DIM)

            q_text  = current_q.get("question", "")
            q_lines = wordwrap(q_text, int(cols * 0.70))
            q_row   = 12
            for i, line in enumerate(q_lines):
                dc(s, line, q_row + i, R.COL_CREAM)

            opts    = current_q.get("options", [])
            opt_row = q_row + len(q_lines) + 2
            for i, opt in enumerate(opts):
                prefix = "►  " if i == sel else "   "
                color  = R.COL_CREAM if i == sel else R.COL_SEPIA
                dc(s, prefix + opt, opt_row + i, color)

            footer(s, "▲/▼ NAVIGATE   ATTACK=SELECT   JUMP=REGENERATE")
            finish(s)

            for ev in events:
                if ev.action == Action.UP:
                    sel = (sel - 1) % 4
                elif ev.action == Action.DOWN:
                    sel = (sel + 1) % 4
                elif ev.action == Action.ATTACK:
                    chosen = opts[sel] if opts else "?"
                    messages.append({"role": "user", "content": chosen})
                    if q_num >= MAX_QUESTIONS:
                        messages.append({
                            "role": "user",
                            "content": "That's all my answers. Generate the complete game spec now.",
                        })
                    start_api(list(messages))
                    state = "LOADING"
                elif ev.action == Action.JUMP and regens_left > 0:
                    regens_left -= 1
                    regen_msgs = list(messages) + [{
                        "role": "user",
                        "content": "Give me a different question on a different topic.",
                    }]
                    start_api(regen_msgs)
                    state = "LOADING"

        elif state == "SPEC_DISPLAY":
            # ── Spec frame ──────────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "YOUR  GAME  IS  READY !", 7, R.COL_CREAM)

            content_start = 9
            content_end   = rows - 2
            visible       = content_end - content_start + 1
            max_scroll    = max(0, len(spec_lines) - visible)
            scroll        = min(scroll, max_scroll)

            for i in range(visible):
                idx = scroll + i
                if idx < len(spec_lines):
                    line, color = spec_lines[idx]
                    dc(s, line, content_start + i, color)

            footer(s, "▲/▼ SCROLL   HOLD  ATTACK+JUMP  TO  EXIT")
            finish(s)

            for ev in events:
                if ev.action == Action.UP:
                    scroll = max(0, scroll - 1)
                elif ev.action == Action.DOWN:
                    scroll = min(max_scroll, scroll + 1)

        elif state == "ERROR":
            # ── Error frame ─────────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "GAME  CREATOR  ERROR", 7, R.COL_DANGER)
            for i, line in enumerate(wordwrap(error_msg, cols - 6)):
                dc(s, line, rows // 2 + i, R.COL_SEPIA)
            footer(s, "HOLD  ATTACK+JUMP  TO  EXIT")
            finish(s)

    R.clear_scene_cache()
