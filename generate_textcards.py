#!/usr/bin/env python3
"""Generate TextCard.txt for games that have a spec but no card yet."""

import os
import re
import json
import time
import subprocess

ARCADE_DIR  = os.path.dirname(os.path.abspath(__file__))
GAMES_DIR   = os.path.join(ARCADE_DIR, "games")
MODEL       = "claude-haiku-4-5-20251001"
TIMEOUT     = 60

TARGETS = ["bunker-down", "ice-clash", "space-junk-derby", "swarm-command", "sync"]


def parse_spec(path: str) -> dict:
    with open(path) as f:
        text = f.read()

    # YAML frontmatter
    fm = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"')

    # Section bodies
    def section(heading):
        pat = rf"## {heading}\n\n(.*?)(?=\n## |\Z)"
        m = re.search(pat, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    return {
        "title":         fm.get("title", "Untitled"),
        "slug":          fm.get("slug", ""),
        "genre":         fm.get("genre", ""),
        "concept":       section("Game Concept"),
        "core_mechanic": section("Core Mechanic"),
        "visual_style":  section("Visual Style"),
        "pacing":        section("Pacing"),
        "tone":          section("Tone"),
    }


WIDTH = 130


def render_figlet(title: str) -> str | None:
    for font in ("slant", "big", "small"):
        try:
            proc = subprocess.run(
                ["figlet", "-f", font, "-w", str(WIDTH), title],
                capture_output=True, text=True,
            )
            lines = proc.stdout.rstrip("\n").splitlines()
            if lines and max(len(l) for l in lines) <= WIDTH:
                return "\n".join(
                    " " * max(0, (WIDTH - len(l)) // 2) + l for l in lines
                )
        except Exception:
            continue
    return None


def fetch_taglines(title: str, genre: str, tone: str) -> str:
    prompt = (
        f"Write exactly 2 short taglines for an arcade game. "
        f"Title: {title}. Genre: {genre}. Tone: {tone}. "
        f"Return only 2 plain text lines, max 55 chars each, nothing else."
    )
    try:
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", MODEL, prompt],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        outer = json.loads(proc.stdout)
        lines = [l.strip() for l in outer.get("result", "").strip().splitlines() if l.strip()]
        return "\n".join(
            " " * max(0, (WIDTH - len(l)) // 2) + l for l in lines[:2]
        )
    except Exception:
        return ""


def generate(spec: dict) -> bool:
    title = spec["title"]
    slug  = spec["slug"]
    genre = spec["genre"]
    tone  = spec["tone"]

    game_dir = os.path.join(GAMES_DIR, slug)
    os.makedirs(game_dir, exist_ok=True)
    dest = os.path.join(game_dir, "TextCard.txt")

    print(f"  → rendering title ...", flush=True)
    art = render_figlet(title)
    if not art:
        print(f"  ✗ figlet failed")
        return False

    print(f"  → fetching taglines ...", flush=True)
    taglines = fetch_taglines(title, genre, tone)

    content = art + "\n\n" + taglines + "\n" if taglines else art + "\n"
    with open(dest, "w") as f:
        f.write(content)
    print(f"  ✓ {dest}  ({os.path.getsize(dest)} bytes)")
    return True


if __name__ == "__main__":
    for slug in TARGETS:
        game_dir  = os.path.join(GAMES_DIR, slug)
        card_path = os.path.join(game_dir, "TextCard.txt")

        meta_path = os.path.join(game_dir, "meta.json")
        spec_rel  = None
        try:
            with open(meta_path) as f:
                spec_rel = json.load(f).get("spec_path")
        except Exception as e:
            print(f"[{slug}] can't read meta.json: {e}")
            continue

        spec_path = os.path.join(ARCADE_DIR, spec_rel) if spec_rel else None
        if not spec_path or not os.path.exists(spec_path):
            print(f"[{slug}] spec file not found: {spec_path}")
            continue

        print(f"[{slug}]")
        spec = parse_spec(spec_path)
        generate(spec)
        time.sleep(1)
