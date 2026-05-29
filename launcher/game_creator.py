#!/usr/bin/env python3
"""Game Creator screen — guided Q&A with Claude to spec out a new arcade game."""

import os
import sys
import json
import re
import shutil
import threading
import time
import datetime
import subprocess

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from input_handler import poll_input, Action
from text_input import (TextInput, MODE_MORSE, ALPHA_CHARS as TI_ALPHA_CHARS,
                        MORSE_TREE_LINES, MORSE_ICICLE_LINES, MORSE_LEGEND)

ARCADE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_DIR     = os.path.join(ARCADE_DIR, "games", "_queue")
GAMES_DIR     = os.path.join(ARCADE_DIR, "games")
DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_dev_daemon.py")
LOGS_DIR      = os.path.join(ARCADE_DIR, "logs")
PROMPT_FILE   = os.path.join(ARCADE_DIR, "GAME_GEN_PROMPT.md")

# Resolve claude explicitly: systemd-started parents have a minimal PATH that
# omits ~/.local/bin, so a bare "claude" subprocess fails with FileNotFoundError.
CLAUDE = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")

MAX_QUESTIONS        = 20
MAX_REGENERATES      = 3
MAX_TEXTCARD_REGENS  = 3
HOLD_WINDOW          = 0.8   # both buttons within this window = quit

_TOPIC_AREAS = [
    "Core mechanic / genre",
    "Number of players (1-4)",
    "Visual theme / aesthetic",
    "Win condition",
    "Pacing / difficulty",
    "Co-op vs competitive (if multiplayer)",
    "Special mechanic or power-up",
    "Tone (silly, tense, chaotic, chill)",
    "Controls / game feel",
    "Your wildcard",
]

_SYSTEM_PROMPT_TEMPLATE = """\
You are the Game Creator for the Bearnos Arcade Cabinet. Help a player design a new arcade game.

Hardware: 4 players, 8-way joystick + 2 buttons (JUMP, ATTACK). 1920x1080 display.
Stack: Python + pygame only. No external assets.

Ask at least 10 questions to understand the game the player wants. Aim to wrap up around 13-15 questions — only push beyond that if a previous answer opened up something genuinely important to resolve. Hard cap: 20 questions. Return ONLY valid JSON — no prose, no markdown fences.

For each question return exactly:
{{"status":"question","question":"...","options":["A","B","C","D"]}}

Exactly 4 options. Question: one sentence. Options: 2-5 words each.

When you have enough info, return the complete spec:
{{"status":"done","title":"...","slug":"...","players":"1-4","genre":"...","concept":"...","core_mechanic":"...","visual_style":"...","win_condition":"...","pacing":"...","tone":"...","notes":["..."],"build_constraints":["Python + pygame","No external assets required","Must launch cleanly and exit cleanly on ATTACK+JUMP"]}}

Cover these areas in this order (freely combine based on answers):
{topics}
11-20. Follow-up only if an answer raises something unresolved — don't pad"""


def _make_system_prompt() -> str:
    import random
    topics = random.sample(_TOPIC_AREAS, len(_TOPIC_AREAS))
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))
    return _SYSTEM_PROMPT_TEMPLATE.format(topics=numbered)


# ── TextCard generator ─────────────────────────────────────────────────────────

def _fetch_textcard_figlet(spec_data: dict) -> str | None:
    """Generate TextCard using figlet for the title + Haiku for taglines."""
    title = spec_data.get("title", "Untitled")
    genre = spec_data.get("genre", "")
    tone  = spec_data.get("tone", "")
    WIDTH = 130

    # Render title with figlet, falling back through fonts until it fits
    art = None
    for font in ("slant", "big", "small"):
        try:
            proc = subprocess.run(
                ["figlet", "-f", font, "-w", str(WIDTH), title],
                capture_output=True, text=True,
            )
            lines = proc.stdout.rstrip("\n").splitlines()
            if lines and max(len(l) for l in lines) <= WIDTH:
                centered = []
                for line in lines:
                    pad = max(0, (WIDTH - len(line)) // 2)
                    centered.append(" " * pad + line)
                art = "\n".join(centered)
                break
        except Exception:
            continue

    if art is None:
        return None

    # Ask Haiku for taglines only
    taglines = ""
    try:
        tag_prompt = (
            f'Write exactly 2 short taglines for an arcade game. '
            f'Title: {title}. Genre: {genre}. Tone: {tone}. '
            f'Return only 2 plain text lines, max 55 chars each, nothing else.'
        )
        proc = subprocess.run(
            [CLAUDE, "-p", "--output-format", "json", "--model", MODEL_HAIKU, tag_prompt],
            capture_output=True, text=True, timeout=60,
        )
        outer = json.loads(proc.stdout)
        lines = [l.strip() for l in outer.get("result", "").strip().splitlines() if l.strip()]
        taglines = "\n".join(
            " " * max(0, (WIDTH - len(l)) // 2) + l for l in lines[:2]
        )
    except Exception:
        pass

    return art + "\n\n" + taglines if taglines else art


def _fetch_textcard(spec_data: dict) -> str | None:
    """Ask Claude to write ASCII art TextCard into the game dir, then return the content."""
    title          = spec_data.get("title", "Untitled")
    genre          = spec_data.get("genre", "")
    tone           = spec_data.get("tone", "")
    concept        = spec_data.get("concept", "")
    core_mechanic  = spec_data.get("core_mechanic", "")
    visual_style   = spec_data.get("visual_style", "")
    pacing         = spec_data.get("pacing", "")
    slug           = spec_data.get("slug") or _slugify(title)

    game_dir = os.path.join(ARCADE_DIR, "games", slug)
    os.makedirs(game_dir, exist_ok=True)
    dest = os.path.join(game_dir, f"TextCard_{int(time.time() * 1000)}.txt")

    prompt = f"""\
Write the file {dest} — a full-screen ASCII art title card for an arcade cabinet game.

Game spec:
  Title:         {title}
  Genre:         {genre}
  Tone:          {tone}
  Concept:       {concept}
  Core mechanic: {core_mechanic}
  Visual style:  {visual_style}
  Pacing:        {pacing}

Canvas: 130 characters wide, 22 rows tall. Fill it. The title art alone should occupy 14–18 rows.

Design brief:
- Choose an ASCII/Unicode art style that reflects this game's specific tone and visual identity —
  not just generic block letters. A chaotic brawler should feel different from a zen puzzle game.
  Use the character set (box-drawing, braille, symbols, slash/pipe/underscore constructions,
  dense vs sparse fill) to evoke the game's feel.
- The title lettering should be bold and large — aim for letters 8–12 rows tall.
- Surround or underpin the title with decorative elements drawn from the game's theme
  (e.g. if it's a space game, sparse star-field framing; if it's a dungeon crawler, brick/shadow texture).
- Below the title art: 2–3 short centred taglines (≤60 chars each) that capture the tone and hook.
- Hard limits: max 130 chars wide, max 22 rows total including taglines.
- Raw text only — no markdown, no explanation, no code fences.
- Write exactly this content to {dest} and nothing else."""

    log_path = os.path.join(LOGS_DIR, "textcard_gen.log")
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        proc = subprocess.run(
            [CLAUDE, "-p", "--allowedTools", "Write", "--model", MODEL_SONNET, prompt],
            capture_output=True, text=True, timeout=180,
        )
        with open(log_path, "w") as lf:
            lf.write(f"dest: {dest}\nreturncode: {proc.returncode}\n\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}\n")
        if proc.returncode != 0:
            return None
        with open(dest) as f:
            return f.read().strip() or None
    except Exception as e:
        try:
            with open(log_path, "a") as lf:
                lf.write(f"\nexception: {e}\n")
        except Exception:
            pass
        return None


# ── Claude subprocess call ──────────────────────────────────────────────────────

MODEL_HAIKU    = "claude-haiku-4-5-20251001"
MODEL_SONNET   = "claude-sonnet-4-6"
MODEL_NEMOTRON = "nemotron-3-super:120b"
MODEL_GEMMA    = "gemma4:26b"
OLLAMA_SPARK   = "http://192.168.1.150:11434"
OLLAMA_CNC     = "http://192.168.1.100:11434"


def _call_claude(messages: list, system_prompt: str, model: str = MODEL_HAIKU) -> dict:
    """Call `claude -p` with full conversation history. Returns parsed dict."""
    prompt = "\n".join(
        ("User: " if m["role"] == "user" else "Claude: ") + m["content"]
        for m in messages
    )
    try:
        proc = subprocess.run(
            [CLAUDE, "-p", "--output-format", "json", "--model", model,
             "--system-prompt", system_prompt, prompt],
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

def _make_feedback_code() -> str:
    """Return a unique 4-char alphanumeric feedback code not already used by any game."""
    import random
    import string
    chars = string.ascii_lowercase + string.digits
    used = set()
    for meta_path in __import__('pathlib').Path(GAMES_DIR).glob("*/meta.json"):
        try:
            code = json.loads(meta_path.read_text()).get("feedback_code")
            if code:
                used.add(code)
        except Exception:
            pass
    for _ in range(1000):
        code = "".join(random.choices(chars, k=4))
        if code not in used:
            return code
    return "".join(random.choices(chars, k=6))


def _slugify(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:64] or "new-game"


def _write_spec(spec_data: dict, designer: str = "") -> str:
    os.makedirs(QUEUE_DIR, exist_ok=True)
    slug    = spec_data.get("slug") or _slugify(spec_data.get("title", "new-game"))
    created = datetime.datetime.now().isoformat(timespec="seconds")
    notes   = "\n".join(f"- {n}" for n in spec_data.get("notes", []))
    constr  = "\n".join(f"- {c}" for c in spec_data.get("build_constraints", [
        "Python + pygame",
        "No external assets required",
        "Must launch cleanly and exit cleanly on ATTACK+JUMP",
    ]))
    designer_line = f"\ndesigner: {designer}" if designer else ""
    content = f"""\
---
title: "{spec_data.get('title', 'Untitled')}"
slug: {slug}
players: {spec_data.get('players', '1-4')}
genre: {spec_data.get('genre', 'unknown')}
created: {created}{designer_line}
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
    spec_path = os.path.join(QUEUE_DIR, f"{slug}.md")
    with open(spec_path, "w") as f:
        f.write(content)

    # Create Coming Soon placeholder so the launcher shows it immediately
    game_dir = os.path.join(ARCADE_DIR, "games", slug)
    os.makedirs(game_dir, exist_ok=True)

    author = f"{designer} · game-creator" if designer else "game-creator"
    feedback_code = _make_feedback_code()
    feedback_url  = f"http://tmnt.starcatcher/{feedback_code}"
    meta = {
        "title":           spec_data.get("title", "Untitled"),
        "description":     spec_data.get("concept", ""),
        "players":         spec_data.get("players", "1-4"),
        "author":          author,
        "added":           created[:10],
        "generated":       True,
        "game_dev_status": "coming_soon",
        "spec_path":       os.path.join("games", "_queue", f"{slug}.md"),
        "feedback_code":   feedback_code,
        "feedback_url":    feedback_url,
    }
    with open(os.path.join(game_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    launch_stub = os.path.join(game_dir, "launch.sh")
    if not os.path.exists(launch_stub):
        with open(launch_stub, "w") as f:
            f.write("#!/bin/bash\n# Game not yet built\n")
        os.chmod(launch_stub, 0o755)

    return spec_path


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


# ── Build tracking ──────────────────────────────────────────────────────────────

BUILD_PIDS_DIR  = os.path.join(LOGS_DIR, "build_pids")
BUILD_STATE_LOG = os.path.join(LOGS_DIR, "build_state.json")


def _load_cooldown_hours() -> float:
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        return cfg.get("build_cooldown_hours", 5.0)
    except Exception:
        return 5.0


def _count_running_for(builder_id: str) -> int:
    prefix = f"{builder_id}__"
    count = 0
    try:
        for fname in os.listdir(BUILD_PIDS_DIR):
            if not fname.startswith(prefix) or not fname.endswith(".pid"):
                continue
            pid_file = os.path.join(BUILD_PIDS_DIR, fname)
            try:
                pid = int(open(pid_file).read().strip())
                os.kill(pid, 0)
                count += 1
            except (ProcessLookupError, PermissionError):
                try: os.unlink(pid_file)
                except FileNotFoundError: pass
            except Exception:
                pass
    except FileNotFoundError:
        pass
    return count


def _hours_since_last_oneshot() -> float | None:
    try:
        with open(BUILD_STATE_LOG) as f:
            data = json.load(f)
        last = data.get("oneshot_last_started")
        if last:
            import datetime as _dt
            then = _dt.datetime.fromisoformat(last)
            return (_dt.datetime.now() - then).total_seconds() / 3600.0
    except Exception:
        pass
    return None


def check_build_limits(builder_id: str) -> tuple[bool, str]:
    """Returns (ok, reason). Exposed for UI use."""
    if _count_running_for(builder_id) >= 1:
        return False, "build already running"
    if builder_id == "oneshot":
        cooldown_hours = _load_cooldown_hours()
        since = _hours_since_last_oneshot()
        if since is not None and since < cooldown_hours:
            mins = int((cooldown_hours - since) * 60)
            return False, f"cooldown: {mins}m remaining"
    return True, ""


def _record_build_start(slug: str, pid: int, builder_id: str = "unknown") -> None:
    import datetime as _dt
    os.makedirs(BUILD_PIDS_DIR, exist_ok=True)
    with open(os.path.join(BUILD_PIDS_DIR, f"{builder_id}__{slug}.pid"), "w") as f:
        f.write(str(pid))
    if builder_id == "oneshot":
        try:
            with open(BUILD_STATE_LOG) as f:
                data = json.load(f)
        except Exception:
            data = {}
        data["oneshot_last_started"] = _dt.datetime.now().isoformat(timespec="seconds")
        data["last_slug"]            = slug
        with open(BUILD_STATE_LOG, "w") as f:
            json.dump(data, f, indent=2)


def _record_build_end(slug: str, builder_id: str = "unknown") -> None:
    pid_file = os.path.join(BUILD_PIDS_DIR, f"{builder_id}__{slug}.pid")
    try:
        os.unlink(pid_file)
    except FileNotFoundError:
        pass


# ── Builder registry ────────────────────────────────────────────────────────────

def _slug_is_active(slug: str) -> bool:
    """True if any builder currently has an active build for this slug."""
    try:
        for fname in os.listdir(BUILD_PIDS_DIR):
            if not fname.endswith(f"__{slug}.pid"):
                continue
            try:
                pid = int(open(os.path.join(BUILD_PIDS_DIR, fname)).read().strip())
                os.kill(pid, 0)
                return True
            except (ProcessLookupError, PermissionError):
                pass
    except FileNotFoundError:
        pass
    return False


def _resolve_slug(base_slug: str) -> str:
    """Return base_slug if available, otherwise the next free versioned slug."""
    def _taken(s):
        return _slug_is_active(s) or os.path.exists(os.path.join(GAMES_DIR, s, f"{s}.py"))
    if not _taken(base_slug):
        return base_slug
    for n in range(2, 100):
        candidate = f"{base_slug}-v{n}"
        if not _taken(candidate):
            return candidate
    return f"{base_slug}-{int(time.time())}"


def _load_builders() -> list:
    """Return the builders list from daemon_config.json, with a safe fallback."""
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        builders = cfg.get("builders")
        if builders:
            return [b for b in builders if not b.get("hidden")]
    except Exception:
        pass
    return [
        {"id": "oneshot", "name": "One-Shot  (local claude -p)"},
        {"id": "queue",   "name": "Queue  (daemon)"},
    ]


def _run_oneshot_build(spec_path: str, slug: str, builder_id: str = "oneshot", model: str = MODEL_SONNET, builder_name: str = "") -> tuple[bool, str]:
    """Build a game using GAME_GEN_PROMPT.md as the prompt. Returns (ok, message)."""
    try:
        dest = os.path.join(GAMES_DIR, slug)
        os.makedirs(dest, exist_ok=True)

        # Save feedback fields before Claude may overwrite meta.json.
        pre_build_preserve = {}
        pre_meta = os.path.join(dest, "meta.json")
        if os.path.exists(pre_meta):
            try:
                pre = json.load(open(pre_meta))
                for key in ("feedback_code", "feedback_url"):
                    if pre.get(key):
                        pre_build_preserve[key] = pre[key]
            except Exception:
                pass

        with open(PROMPT_FILE) as f:
            prompt_template = f.read()

        # Strip the placeholder example section, append the real spec
        cut = prompt_template.find("\n## [GAME SPEC]")
        base_prompt = prompt_template[:cut] if cut != -1 else prompt_template

        with open(spec_path) as f:
            spec_text = f.read()

        full_prompt = base_prompt + "\n\n## GAME SPEC\n\n" + spec_text

        log_path = os.path.join(LOGS_DIR, f"oneshot_{slug}.log")
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(log_path, "w") as lf:
            proc = subprocess.Popen(
                [CLAUDE, "-p", "--dangerously-skip-permissions", full_prompt],
                stdout=lf, stderr=lf, cwd=dest,
                start_new_session=True,
            )
            _record_build_start(slug, proc.pid, builder_id)
            try:
                proc.wait(timeout=600)
            finally:
                _record_build_end(slug, builder_id)

        if proc.returncode != 0:
            return (False, f"claude exited {proc.returncode} — see logs/oneshot_{slug}.log")

        required = [f"{slug}.py", "launch.sh", "meta.json"]
        missing  = [f for f in required if not os.path.exists(os.path.join(dest, f))]
        if missing:
            return (False, f"missing files: {', '.join(missing)}")

        os.chmod(os.path.join(dest, "launch.sh"), 0o755)

        meta_path = os.path.join(dest, "meta.json")
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            meta.update(pre_build_preserve)
            meta["game_dev_status"] = "ok"
            meta["generated"]       = True
            meta["built_by"]        = model
            meta["author"]          = builder_name or model
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

        return (True, "Build complete")

    except subprocess.TimeoutExpired:
        return (False, "Timed out after 10 minutes")
    except Exception as e:
        return (False, str(e)[:120])


def _run_ollama_build(spec_path: str, slug: str, ollama_url: str, model: str, timeout: int = 900, builder_id: str = "ollama", builder_name: str = "") -> tuple[bool, str]:
    """Build using claude -p routed through an Ollama server. Returns (ok, message)."""
    try:
        dest = os.path.join(GAMES_DIR, slug)
        os.makedirs(dest, exist_ok=True)

        # Save feedback fields before Claude may overwrite meta.json.
        pre_build_preserve = {}
        pre_meta = os.path.join(dest, "meta.json")
        if os.path.exists(pre_meta):
            try:
                pre = json.load(open(pre_meta))
                for key in ("feedback_code", "feedback_url"):
                    if pre.get(key):
                        pre_build_preserve[key] = pre[key]
            except Exception:
                pass

        with open(PROMPT_FILE) as f:
            prompt_template = f.read()

        cut = prompt_template.find("\n## [GAME SPEC]")
        base_prompt = prompt_template[:cut] if cut != -1 else prompt_template

        with open(spec_path) as f:
            spec_text = f.read()

        full_prompt = base_prompt + "\n\n## GAME SPEC\n\n" + spec_text

        label    = model.replace(":", "-").replace("/", "-")
        log_path = os.path.join(LOGS_DIR, f"ollama_{label}_{slug}.log")
        os.makedirs(LOGS_DIR, exist_ok=True)

        env = {**os.environ, "ANTHROPIC_BASE_URL": ollama_url}

        with open(log_path, "w") as lf:
            proc = subprocess.Popen(
                [CLAUDE, "-p", "--dangerously-skip-permissions",
                 "--model", model, full_prompt],
                stdout=lf, stderr=lf, cwd=dest,
                env=env, start_new_session=True,
            )
            _record_build_start(slug, proc.pid, builder_id)
            try:
                proc.wait(timeout=timeout)
            finally:
                _record_build_end(slug, builder_id)

        if proc.returncode != 0:
            return (False, f"build exited {proc.returncode} — see {os.path.basename(log_path)}")

        required = [f"{slug}.py", "launch.sh", "meta.json"]
        missing  = [f for f in required if not os.path.exists(os.path.join(dest, f))]
        if missing:
            return (False, f"missing files: {', '.join(missing)}")

        os.chmod(os.path.join(dest, "launch.sh"), 0o755)

        meta_path = os.path.join(dest, "meta.json")
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            meta.update(pre_build_preserve)
            meta["game_dev_status"] = "ok"
            meta["generated"]       = True
            meta["built_by"]        = model
            meta["author"]          = builder_name or model
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

        return (True, "Build complete")

    except subprocess.TimeoutExpired:
        return (False, f"Timed out after {timeout // 60} minutes")
    except Exception as e:
        return (False, str(e)[:120])


def _run_build(builder: dict, spec_path: str, slug: str) -> tuple[bool, str]:
    bid       = builder.get("id", "")
    bname     = builder.get("name", bid)
    versioned = _resolve_slug(slug)
    if bid == "oneshot":
        ok, reason = check_build_limits(bid)
        if not ok:
            return (False, reason)
        return _run_oneshot_build(spec_path, versioned, builder_id=bid, model=MODEL_SONNET, builder_name=bname)
    elif bid == "spark":
        ok, reason = check_build_limits(bid)
        if not ok:
            return (False, reason)
        return _run_ollama_build(spec_path, versioned, OLLAMA_SPARK, MODEL_NEMOTRON, timeout=900, builder_id=bid, builder_name=bname)
    elif bid == "ollama_cnc":
        ok, reason = check_build_limits(bid)
        if not ok:
            return (False, reason)
        return _run_ollama_build(spec_path, versioned, OLLAMA_CNC, MODEL_GEMMA, timeout=600, builder_id=bid, builder_name=bname)
    elif bid == "queue":
        _ensure_daemon()
        return (True, "Queued — daemon will build it")
    else:
        # Delegate remote/spark builds to the daemon's SSH dispatch
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from game_dev_daemon import _dispatch_ssh
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daemon_config.json")
            with open(cfg_path) as f:
                cfg = {**json.load(f), **builder}
            ok = _dispatch_ssh(spec_path, cfg)
            return (ok, "Remote build complete" if ok else "Remote build failed")
        except Exception as e:
            return (False, str(e)[:120])


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daemon_config.json")


# ── Spec display lines ──────────────────────────────────────────────────────────

def _build_spec_lines(spec_data: dict, cols: int, card_text: str | None = None) -> list:
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
        block = "  ·  ".join(n.strip() for n in notes if n.strip())
        for line in wrap(block, max_w):
            out.append(("  " + line, COL_SEPIA))
        out.append(("", COL_DIM))

    out.append(("─" * min(int(cols * 0.68), cols - 2), COL_ACCENT))
    if card_text is None:
        out.append(("  [ generating title card... ]", COL_DIM))
    else:
        for line in card_text.split("\n"):
            out.append((line, COL_CREAM))
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

    def surf_dark():
        s = pygame.Surface((R.SCREEN_W, R.SCREEN_H))
        s.fill(R.COL_BG)
        return s

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
    SCROLL_INTERVAL = 1.0 / 7
    NAME_CHARS      = " ABCDEFGHIJKLMNOPQRSTUVWXYZ"   # space=0, A=1 — matches TI_ALPHA_CHARS

    state       = "INTRO"
    messages    = []
    q_num       = 0
    current_q   = None
    sel         = 0
    regens_left = MAX_REGENERATES
    spec_data   = None
    error_msg   = ""
    scroll         = 0
    spec_lines     = []
    last_scroll_t  = 0.0

    # Name entry state
    name_chars    = [0, 0, 0]   # indices into NAME_CHARS
    name_cursor   = 0
    designer_name = ""
    name_grace_t  = time.monotonic()
    name_long     = TextInput(max_len=32)

    # Intro / seed state
    intro_sel  = 0           # 0 = START, 1 = SEED AN IDEA
    seed_input = TextInput(max_len=64)

    # Thread result slot
    _result:   list = [None]
    _loading:  list = [False]
    _is_regen: list = [False]   # True when the in-flight call is a regenerate
    _lock = threading.Lock()

    # TextCard state
    cards:          list = []
    card_idx:       list = [0]
    tc_regens_left: list = [MAX_TEXTCARD_REGENS]
    _tc_result:     list = [None]
    _tc_loading:    list = [False]
    _tc_lock = threading.Lock()
    loading_label: list = ["Thinking"]
    system_prompt = _make_system_prompt()
    _force_spec:   list = [False]

    # Builder state
    builders:       list = _load_builders()
    builder_sel:    list = [0]
    _build_result:  list = [None]   # (ok, message) or None
    _build_loading: list = [False]
    _build_lock = threading.Lock()
    _build_finish_t: list = [0.0]   # monotonic time when build completed

    def start_api(msgs, label="Thinking", is_regen=False, model=MODEL_HAIKU):
        loading_label[0] = label
        _is_regen[0]     = is_regen
        with _lock:
            _result[0]  = None
            _loading[0] = True
        def worker():
            r = _call_claude(msgs, system_prompt, model)
            with _lock:
                _result[0]  = r
                _loading[0] = False
        threading.Thread(target=worker, daemon=True).start()

    def launch_creator(seed: str = ""):
        opening = "Start the game creator. Ask me the first question."
        if seed:
            opening = (f"Start the game creator. "
                       f"The player has a rough idea: '{seed}'. "
                       f"Ask me the first question.")
        messages.clear()
        messages.append({"role": "user", "content": opening})
        start_api(list(messages))

    def start_tc_gen(is_regen: bool = False):
        with _tc_lock:
            _tc_result[0]  = None
            _tc_loading[0] = True
        def worker():
            r = _fetch_textcard(spec_data) if is_regen else _fetch_textcard_figlet(spec_data)
            with _tc_lock:
                _tc_result[0]  = r
                _tc_loading[0] = False
        threading.Thread(target=worker, daemon=True).start()

    # Hold-both-to-quit tracking (key-down only, so use timestamps)
    last_attack: dict = {}
    last_jump:   dict = {}

    def track_buttons(evs) -> None:
        now = time.monotonic()
        for ev in evs:
            if ev.action == Action.ATTACK:
                last_attack[ev.player] = now
            elif ev.action == Action.JUMP:
                last_jump[ev.player] = now

    def both_held() -> bool:
        now = time.monotonic()
        for p in range(1, 5):
            ta = last_attack.get(p, 0.0)
            tj = last_jump.get(p, 0.0)
            if ta > 0 and tj > 0 and abs(ta - tj) <= HOLD_WINDOW:
                if now - max(ta, tj) <= HOLD_WINDOW:
                    return True
        return False

    def clear_button_timestamps() -> None:
        last_attack.clear()
        last_jump.clear()

    clock = pygame.time.Clock()

    while True:
        clock.tick(30)
        pygame.event.pump()
        events = poll_input(app.fds, app.ctrl, timeout_ms=0)

        track_buttons(events)
        tree_start = 7   # row where the morse tree begins (shared by SEED_INPUT and NAME_LONG)

        # In ASKING/LOADING, JUMP+ATTACK force-generates the spec instead of quitting
        if both_held():
            if state == "INTRO":
                break
            elif state == "SEED_INPUT" and seed_input.mode == MODE_MORSE:
                clear_button_timestamps()
            elif state == "SEED_INPUT":
                break
            elif state == "ASKING":
                clear_button_timestamps()
                messages.append({
                    "role": "user",
                    "content": "That's all my answers. Generate the complete game spec now.",
                })
                start_api(list(messages), label="Writing spec", model=MODEL_SONNET)
                state = "LOADING"
            elif state == "LOADING" and not _force_spec[0]:
                clear_button_timestamps()
                _force_spec[0] = True
            elif state == "NAME_LONG" and name_long.mode == MODE_MORSE:
                clear_button_timestamps()   # ignore chord mid-morse
            elif state == "NAME_LONG":
                clear_button_timestamps()
                name_long = TextInput(max_len=32)
                state = "NAME_ENTRY"
            elif state == "SPEC_DISPLAY":
                if cards:
                    slug     = spec_data.get("slug") or _slugify(spec_data.get("title", "new-game"))
                    game_dir = os.path.join(ARCADE_DIR, "games", slug)
                    dest     = os.path.join(game_dir, "TextCard.txt")
                    with open(dest, "w") as f:
                        f.write(cards[card_idx[0]])
                break
            else:
                break

        if state == "INTRO":
            # ── Intro menu ──────────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "GAME  CREATOR", 7, R.COL_CREAM)

            options = ["START", "SEED  AN  IDEA"]
            mid = rows // 2
            for i, opt in enumerate(options):
                row = mid - 1 + i * 2
                if i == intro_sel:
                    dc(s, f"[ {opt} ]", row, R.COL_ACCENT)
                else:
                    dc(s, f"  {opt}  ", row, R.COL_DIM)

            footer(s, "▲/▼  SELECT   ATTACK=CONFIRM   JUMP+ATTACK=QUIT")
            finish(s)

            for ev in events:
                if ev.action in (Action.UP, Action.LEFT):
                    intro_sel = (intro_sel - 1) % len(options)
                elif ev.action in (Action.DOWN, Action.RIGHT):
                    intro_sel = (intro_sel + 1) % len(options)
                elif ev.action == Action.ATTACK:
                    if intro_sel == 0:
                        launch_creator()
                        state = "LOADING"
                    else:
                        seed_input = TextInput(max_len=64)
                        state = "SEED_INPUT"

        elif state == "SEED_INPUT":
            # ── Seed idea entry (shares morse rendering with NAME_LONG) ──────
            s = surf_dark() if seed_input.mode == MODE_MORSE else surf()
            header(s)

            if seed_input.mode == MODE_MORSE:
                for i, line in enumerate(MORSE_TREE_LINES):
                    dc(s, line, tree_start + i, R.COL_DIM)

                seq    = seed_input.morse_seq_str()
                cur    = seed_input.morse_letter() or "·"
                dit_l  = seed_input.morse_dit_letter()
                dash_l = seed_input.morse_dash_letter()
                state_row = tree_start + len(MORSE_TREE_LINES) + 1
                dc(s, f"[JUMP ·]→{dit_l}   {seq}  [{cur}]   {dash_l}←[ATTACK —]",
                   state_row, R.COL_ACCENT)

                icicle_start = state_row + 2
                dc(s, MORSE_LEGEND, icicle_start, R.COL_SEPIA)
                for i, line in enumerate(MORSE_ICICLE_LINES):
                    dc(s, line, icicle_start + 1 + i, R.COL_CREAM)

                footer(s, ". JUMP   _ ATTACK   ► ACCEPT+NEXT   ◄ ACCEPT+BACK   UP HOLD=CONFIRM")
            else:
                dc(s, "GAME  CREATOR", 7, R.COL_CREAM)
                dc(s, "SEED  AN  IDEA", 9, R.COL_DIM)
                footer(s, "▲/▼  CYCLE   ◄ MORSE MODE   ► ADVANCE   JUMP=CONFIRM   JUMP+ATTACK=BACK")

            buf_row = tree_start + len(MORSE_TREE_LINES) + 2 if seed_input.mode == MODE_MORSE else rows // 2
            visible = cols - 6
            chars   = seed_input.chars
            cur_idx = seed_input.cursor
            morse_preview = seed_input.morse_letter() if seed_input.mode == MODE_MORSE else ""
            start   = max(0, cur_idx - visible + 4)
            line    = ""
            for i, ci in enumerate(chars[start:start + visible]):
                ch    = TI_ALPHA_CHARS[ci] if ci < len(TI_ALPHA_CHARS) else " "
                col_i = start + i
                if col_i == cur_idx:
                    line += f"[{morse_preview or ch}]"
                else:
                    line += f" {ch} "
            dc(s, line.strip(), buf_row, R.COL_CREAM)
            finish(s)

            def _commit_seed():
                nonlocal state
                launch_creator(seed=seed_input.text())
                state = "LOADING"

            if seed_input.tick():
                _commit_seed()
            else:
                for ev in events:
                    if seed_input.handle_event(ev):
                        _commit_seed()
                        break

        elif state == "NAME_ENTRY":
            # ── Name entry frame ────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "GAME  CREATOR", 7, R.COL_CREAM)
            dc(s, "SIGN  YOUR  WORK", 9, R.COL_DIM)

            mid = rows // 2
            slot_w   = 5   # "[ X ]" or "  X  "
            gap      = 4
            total_w  = 3 * slot_w + 2 * gap   # 23
            start_col = max(1, (cols - total_w) // 2)

            for i in range(3):
                ch  = NAME_CHARS[name_chars[i]]
                col = start_col + i * (slot_w + gap)
                if i == name_cursor:
                    d(s, f"[ {ch} ]", mid - 1, col, R.COL_ACCENT)
                    d(s, "  ▲  ",     mid - 3, col, R.COL_DIM)
                    d(s, "  ▼  ",     mid + 1, col, R.COL_DIM)
                else:
                    d(s, f"  {ch}  ", mid - 1, col, R.COL_SEPIA)

            footer(s, "▲/▼  CYCLE   ◄/►  MOVE   ATTACK=NEXT/SIGN   JUMP=BACK   ◄ AT START = FULL  NAME")
            finish(s)

            if time.monotonic() - name_grace_t >= 0.35:
                for ev in events:
                    if ev.action == Action.UP:
                        name_chars[name_cursor] = (name_chars[name_cursor] - 1) % len(NAME_CHARS)
                    elif ev.action == Action.DOWN:
                        name_chars[name_cursor] = (name_chars[name_cursor] + 1) % len(NAME_CHARS)
                    elif ev.action == Action.LEFT:
                        if name_cursor > 0:
                            name_cursor -= 1
                        else:
                            name_long = TextInput(max_len=32)
                            state = "NAME_LONG"
                    elif ev.action == Action.RIGHT:
                        name_cursor = min(2, name_cursor + 1)
                    elif ev.action == Action.JUMP:
                        if name_cursor > 0:
                            name_cursor -= 1
                        else:
                            state = "SPEC_DISPLAY"
                    elif ev.action == Action.ATTACK:
                        if name_cursor < 2:
                            name_cursor += 1
                        else:
                            designer_name = "".join(
                                NAME_CHARS[name_chars[i]] for i in range(3)
                            ).strip()
                            # Update meta.json with designer + author
                            slug     = spec_data.get("slug") or _slugify(spec_data.get("title", "new-game"))
                            meta_path = os.path.join(ARCADE_DIR, "games", slug, "meta.json")
                            try:
                                with open(meta_path) as _f:
                                    _meta = json.load(_f)
                                _meta["author"] = f"{designer_name} · game-creator" if designer_name else "game-creator"
                                with open(meta_path, "w") as _f:
                                    json.dump(_meta, _f, indent=2)
                            except Exception:
                                pass
                            builder_sel[0] = 0
                            state = "BUILDER_PICK"

        elif state == "NAME_LONG":
            # ── Full-name entry ──────────────────────────────────────────────
            s = surf_dark() if name_long.mode == MODE_MORSE else surf()
            header(s)

            if name_long.mode == MODE_MORSE:
                # ── tree ─────────────────────────────────────────────────
                for i, line in enumerate(MORSE_TREE_LINES):
                    dc(s, line, tree_start + i, R.COL_DIM)

                # ── current morse state ───────────────────────────────────
                seq    = name_long.morse_seq_str()
                cur    = name_long.morse_letter() or "·"
                dit_l  = name_long.morse_dit_letter()
                dash_l = name_long.morse_dash_letter()
                state_row = tree_start + len(MORSE_TREE_LINES) + 1
                dc(s, f"[JUMP ·]→{dit_l}   {seq}  [{cur}]   {dash_l}←[ATTACK —]",
                   state_row, R.COL_ACCENT)

                # ── icicles ───────────────────────────────────────────────
                icicle_start = state_row + 2
                dc(s, MORSE_LEGEND, icicle_start, R.COL_SEPIA)
                for i, line in enumerate(MORSE_ICICLE_LINES):
                    dc(s, line, icicle_start + 1 + i, R.COL_CREAM)

                footer(s, ". JUMP   _ ATTACK   ► ACCEPT+NEXT   ◄ ACCEPT+BACK   UP HOLD=DONE")
            else:
                dc(s, "GAME  CREATOR", 7, R.COL_CREAM)
                dc(s, "FULL  NAME", 9, R.COL_DIM)
                footer(s, "▲/▼  CYCLE   ◄ MORSE MODE   ► ADVANCE   JUMP=DONE   JUMP+ATTACK=3-CHAR")

            # Draw text buffer (between state row and icicles in morse mode)
            buf_row  = tree_start + len(MORSE_TREE_LINES) + 2 if name_long.mode == MODE_MORSE else rows // 2
            visible  = cols - 6
            chars    = name_long.chars
            cur_idx  = name_long.cursor
            morse_preview = name_long.morse_letter() if name_long.mode == MODE_MORSE else ""
            start    = max(0, cur_idx - visible + 4)
            line     = ""
            for i, ci in enumerate(chars[start:start + visible]):
                ch   = TI_ALPHA_CHARS[ci] if ci < len(TI_ALPHA_CHARS) else " "
                col_i = start + i
                if col_i == cur_idx:
                    line += f"[{morse_preview or ch}]"
                else:
                    line += f" {ch} "
            dc(s, line.strip(), buf_row, R.COL_CREAM)

            finish(s)

            def _commit_long_name():
                nonlocal designer_name, state
                designer_name = name_long.text()
                slug_     = spec_data.get("slug") or _slugify(spec_data.get("title", "new-game"))
                mpath     = os.path.join(ARCADE_DIR, "games", slug_, "meta.json")
                try:
                    with open(mpath) as _f:
                        _meta = json.load(_f)
                    _meta["author"] = f"{designer_name} · game-creator" if designer_name else "game-creator"
                    with open(mpath, "w") as _f:
                        json.dump(_meta, _f, indent=2)
                except Exception:
                    pass
                builder_sel[0] = 0
                state = "BUILDER_PICK"

            if name_long.tick():
                _commit_long_name()
            else:
                for ev in events:
                    if name_long.handle_event(ev):
                        _commit_long_name()
                        break

        elif state == "LOADING":
            # ── Loading frame ───────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "GAME  CREATOR", 7, R.COL_CREAM)
            dots = "·" * (int(time.monotonic() * 2) % 4 + 1)
            label = "Skipping to spec" if _force_spec[0] else loading_label[0]
            dc(s, f"[ {label} {dots} ]", rows // 2, R.COL_ACCENT)
            hint = "Please wait ..." if _force_spec[0] else "HOLD  JUMP+ATTACK  TO  SKIP  TO  SPEC"
            footer(s, hint)
            finish(s)

            with _lock:
                done = not _loading[0]
                r    = _result[0] if done else None

            if done:
                if r is None or r.get("status") == "error":
                    error_msg = r.get("message", "Unknown error") if r else "No response"
                    state = "ERROR"
                elif r["status"] == "question" and _force_spec[0]:
                    _force_spec[0] = False
                    messages.append({"role": "assistant", "content": json.dumps(r)})
                    messages.append({
                        "role": "user",
                        "content": "That's all my answers. Generate the complete game spec now.",
                    })
                    start_api(list(messages), label="Writing spec", model=MODEL_SONNET)
                elif r["status"] == "question":
                    messages.append({"role": "assistant", "content": json.dumps(r)})
                    if not _is_regen[0]:
                        q_num      += 1
                        regens_left = MAX_REGENERATES
                    _is_regen[0] = False
                    current_q    = r
                    sel          = 0
                    state        = "ASKING"
                elif r["status"] == "done":
                    _force_spec[0] = False
                    messages.append({"role": "assistant", "content": json.dumps(r)})
                    spec_data  = r
                    _write_spec(r)
                    spec_lines = _build_spec_lines(r, cols)
                    start_tc_gen()
                    state      = "SPEC_DISPLAY"

        elif state == "ASKING":
            # ── Question frame ──────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "GAME  CREATOR", 7, R.COL_CREAM)
            regen_str = "".join("≋" if i < regens_left else "·"
                                for i in range(MAX_REGENERATES))
            q_counter = f"{q_num} / 10+" if q_num <= 10 else str(q_num)
            dc(s, f"QUESTION {q_counter}    [{regen_str}]", 9, R.COL_DIM)

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

            footer(s, "▲/▼ NAVIGATE   ATTACK=SELECT   JUMP=REGENERATE   JUMP+ATTACK=FINISH")
            finish(s)

            for ev in events:
                if ev.action == Action.UP:
                    sel = (sel - 1) % max(len(opts), 1)
                elif ev.action == Action.DOWN:
                    sel = (sel + 1) % max(len(opts), 1)
                elif ev.action == Action.ATTACK:
                    chosen = opts[sel] if opts else "?"
                    messages.append({"role": "user", "content": chosen})
                    if q_num >= MAX_QUESTIONS:
                        messages.append({
                            "role": "user",
                            "content": "That's all my answers. Generate the complete game spec now.",
                        })
                        start_api(list(messages), label="Writing spec", model=MODEL_SONNET)
                    else:
                        start_api(list(messages))
                    state = "LOADING"
                elif ev.action == Action.JUMP and regens_left > 0:
                    regens_left -= 1
                    option_count = 4 + 2 * (MAX_REGENERATES - regens_left)
                    regen_msgs = list(messages) + [{
                        "role": "user",
                        "content": f"Regenerate that same question with a completely different set of {option_count} options — same topic, fresh choices.",
                    }]
                    start_api(regen_msgs, label="Regenerating question", is_regen=True)
                    state = "LOADING"

        elif state == "SPEC_DISPLAY":
            # ── Spec frame ──────────────────────────────────────────────────
            # Pick up a finished TC result and rebuild spec_lines in-place
            with _tc_lock:
                tc_r = _tc_result[0] if not _tc_loading[0] else None
                if tc_r is not None:
                    _tc_result[0] = None  # consume
            if tc_r is not None:
                cards.append(tc_r)
                card_idx[0] = len(cards) - 1
                spec_lines  = _build_spec_lines(spec_data, cols, tc_r)

            s = surf()
            header(s)
            dc(s, "YOUR  GAME  IS  READY !", 7, R.COL_CREAM)

            # regen indicator in subtitle row
            if _tc_loading[0]:
                dots = "·" * (int(time.monotonic() * 2) % 4 + 1)
                dc(s, f"[ generating title card {dots} ]", 9, R.COL_DIM)
            elif tc_regens_left[0] > 0:
                regen_str = "".join("≋" if i < tc_regens_left[0] else "·"
                                    for i in range(MAX_TEXTCARD_REGENS))
                dc(s, f"title card  [{regen_str}]", 9, R.COL_DIM)

            content_start = 11
            content_end   = rows - 2
            visible       = content_end - content_start + 1
            max_scroll    = max(0, len(spec_lines) - visible)
            scroll        = min(scroll, max_scroll)

            for i in range(visible):
                idx = scroll + i
                if idx < len(spec_lines):
                    line, color = spec_lines[idx]
                    dc(s, line, content_start + i, color)

            hints = ["▲/▼ SCROLL"]
            if tc_regens_left[0] > 0 and not _tc_loading[0]:
                hints.append("JUMP=REGEN CARD")
            hints.append("ATTACK=SIGN & BUILD")
            hints.append("HOLD ATTACK+JUMP=EXIT")
            footer(s, "   ".join(hints))
            finish(s)

            for ev in events:
                now = time.monotonic()
                if ev.action == Action.UP and now - last_scroll_t >= SCROLL_INTERVAL:
                    scroll = max(0, scroll - 1)
                    last_scroll_t = now
                elif ev.action == Action.DOWN and now - last_scroll_t >= SCROLL_INTERVAL:
                    scroll = min(max_scroll, scroll + 1)
                    last_scroll_t = now
                elif ev.action == Action.JUMP and tc_regens_left[0] > 0 and not _tc_loading[0]:
                    tc_regens_left[0] -= 1
                    start_tc_gen(is_regen=True)
                    spec_lines = _build_spec_lines(spec_data, cols, None)
                elif ev.action == Action.ATTACK:
                    name_chars[:]  = [0, 0, 0]
                    name_cursor    = 0
                    name_grace_t   = time.monotonic()
                    state          = "NAME_ENTRY"

        elif state == "BUILDER_PICK":
            # ── Builder selection ────────────────────────────────────────────
            s = surf()
            header(s)
            dc(s, "BUILD  THIS  GAME", 7, R.COL_CREAM)
            dc(s, "choose a build agent", 9, R.COL_DIM)

            mid = rows // 2 - len(builders) // 2
            for i, b in enumerate(builders):
                prefix = "►  " if i == builder_sel[0] else "   "
                color  = R.COL_CREAM if i == builder_sel[0] else R.COL_SEPIA
                dc(s, prefix + b["name"], mid + i, color)

            footer(s, "▲/▼ NAVIGATE   ATTACK=SELECT   JUMP=BACK")
            finish(s)

            for ev in events:
                if ev.action == Action.UP:
                    builder_sel[0] = (builder_sel[0] - 1) % max(len(builders), 1)
                elif ev.action == Action.DOWN:
                    builder_sel[0] = (builder_sel[0] + 1) % max(len(builders), 1)
                elif ev.action == Action.JUMP:
                    state = "SPEC_DISPLAY"
                elif ev.action == Action.ATTACK:
                    chosen = builders[builder_sel[0]]
                    slug   = spec_data.get("slug") or _slugify(spec_data.get("title", "new-game"))
                    sp     = os.path.join(QUEUE_DIR, f"{slug}.md")
                    with _build_lock:
                        _build_result[0]  = None
                        _build_loading[0] = True
                    def _build_worker(b=chosen, spec_path=sp, sl=slug):
                        r = _run_build(b, spec_path, sl)
                        with _build_lock:
                            _build_result[0]  = r
                            _build_loading[0] = False
                    threading.Thread(target=_build_worker, daemon=True).start()
                    state = "BUILDING"

        elif state == "BUILDING":
            # ── Build progress ───────────────────────────────────────────────
            s = surf()
            header(s)

            with _build_lock:
                still_loading = _build_loading[0]
                result        = _build_result[0]

            if still_loading:
                dc(s, "BUILDING ...", 7, R.COL_CREAM)
                dots = "·" * (int(time.monotonic() * 2) % 4 + 1)
                dc(s, f"[ running build agent {dots} ]", rows // 2, R.COL_ACCENT)
                dc(s, "this may take several minutes", rows // 2 + 2, R.COL_DIM)
                footer(s, "JUMP=GO BACK   (build continues in background)")
            else:
                ok, msg = result
                if _build_finish_t[0] == 0.0:
                    _build_finish_t[0] = time.monotonic()
                if ok:
                    dc(s, "BUILD  COMPLETE", 7, R.COL_CREAM)
                    dc(s, msg, rows // 2, R.COL_ACCENT)
                else:
                    dc(s, "BUILD  FAILED", 7, R.COL_DANGER)
                    for i, line in enumerate(wordwrap(msg, cols - 6)):
                        dc(s, line, rows // 2 + i, R.COL_SEPIA)
                footer(s, "returning to spec ...")
                if time.monotonic() - _build_finish_t[0] > 3.0:
                    _build_finish_t[0] = 0.0
                    state = "SPEC_DISPLAY"

            finish(s)

            for ev in events:
                if ev.action == Action.JUMP:
                    state = "SPEC_DISPLAY"

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
