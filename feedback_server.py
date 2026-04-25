#!/usr/bin/env python3
"""
Arcade feedback server.
Serves a mobile-friendly page per game at http://tmnt.starcatcher/<code>
Players can report bugs or request features; submissions are written to
games/<slug>/feedback/<timestamp>_<type>.json
"""

import io
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import qrcode
from flask import Flask, abort, redirect, render_template_string, request, send_file, url_for

ARCADE_DIR = Path(__file__).parent
GAMES_DIR  = ARCADE_DIR / "games"
HOST       = "tmnt.starcatcher"
PORT       = 80

app = Flask(__name__)


def _load_games() -> dict[str, dict]:
    """Return {feedback_code: {slug, title}} for all games that have a feedback_code."""
    games = {}
    for meta_path in GAMES_DIR.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text())
            code = meta.get("feedback_code")
            if code:
                games[code] = {
                    "slug":  meta_path.parent.name,
                    "title": meta.get("title", meta_path.parent.name),
                }
        except Exception:
            pass
    return games


# ── HTML templates ─────────────────────────────────────────────────────────────

_BASE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0a0f">
<title>{{ title }} — Arcade Feedback</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0a0a0f;
    color: #e0e0f0;
    font-family: system-ui, -apple-system, sans-serif;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem 1.25rem;
    gap: 2rem;
  }
  header { text-align: center; }
  header small {
    display: block;
    font-size: .75rem;
    letter-spacing: .15em;
    text-transform: uppercase;
    color: #6060a0;
    margin-bottom: .4rem;
  }
  h1 { font-size: 1.75rem; font-weight: 700; color: #c8b8ff; }
  .buttons { display: flex; flex-direction: column; gap: 1rem; width: 100%; max-width: 320px; }
  .btn {
    display: block;
    padding: 1rem 1.5rem;
    border-radius: 10px;
    font-size: 1.1rem;
    font-weight: 600;
    text-align: center;
    text-decoration: none;
    border: 2px solid transparent;
    cursor: pointer;
    transition: filter .15s;
  }
  .btn:hover { filter: brightness(1.15); }
  .btn-bug     { background: #2a0a0a; border-color: #ff4444; color: #ff8888; }
  .btn-feature { background: #0a1a2a; border-color: #44aaff; color: #88ccff; }
  .btn-submit  { background: #1a2a1a; border-color: #44cc66; color: #88ee99; width: 100%; }
  form { width: 100%; max-width: 320px; display: flex; flex-direction: column; gap: 1rem; }
  label { font-size: .85rem; color: #8080b0; letter-spacing: .05em; }
  textarea {
    width: 100%;
    min-height: 8rem;
    background: #12121e;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    color: #e0e0f0;
    font-size: 1rem;
    padding: .75rem;
    resize: vertical;
    outline: none;
  }
  textarea:focus { border-color: #6060c0; }
  .back { font-size: .85rem; color: #5050a0; text-decoration: none; margin-top: .5rem; }
  .back:hover { color: #8080d0; }
  .thanks { text-align: center; color: #88ee99; font-size: 1.1rem; }
</style>
</head>
<body>
{% block body %}{% endblock %}
</body>
</html>"""

_INDEX = _BASE.replace("{% block body %}{% endblock %}", """
<header>
  <small>Star Catcher Arcade</small>
  <h1>{{ title }}</h1>
</header>
<div class="buttons">
  <a class="btn btn-bug"     href="{{ url_for('form', code=code, kind='bug') }}">🐛 Report a Bug</a>
  <a class="btn btn-feature" href="{{ url_for('form', code=code, kind='feature') }}">💡 Request a Feature</a>
</div>
""")

_FORM = _BASE.replace("{% block body %}{% endblock %}", """
<header>
  <small>{{ title }}</small>
  <h1>{{ heading }}</h1>
</header>
<form method="post" action="{{ url_for('submit', code=code) }}">
  <input type="hidden" name="kind" value="{{ kind }}">
  <label for="body">{{ prompt }}</label>
  <textarea id="body" name="body" placeholder="{{ placeholder }}" required autofocus></textarea>
  <button class="btn btn-submit" type="submit">Submit</button>
</form>
<a class="back" href="{{ url_for('index', code=code) }}">← back</a>
""")

_THANKS = _BASE.replace("{% block body %}{% endblock %}", """
<p class="thanks">✓ Submitted — thanks!</p>
<a class="back" href="{{ url_for('index', code=code) }}">← back</a>
""")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/<code>")
def index(code):
    games = _load_games()
    if code not in games:
        abort(404)
    return render_template_string(_INDEX, title=games[code]["title"], code=code)


@app.route("/<code>/<kind>")
def form(code, kind):
    if kind not in ("bug", "feature"):
        abort(404)
    games = _load_games()
    if code not in games:
        abort(404)
    title = games[code]["title"]
    if kind == "bug":
        heading, prompt, placeholder = "Report a Bug", "What went wrong?", "Describe what happened…"
    else:
        heading, prompt, placeholder = "Request a Feature", "What would you like to see?", "Describe your idea…"
    return render_template_string(_FORM, title=title, code=code, kind=kind,
                                  heading=heading, prompt=prompt, placeholder=placeholder)


@app.route("/<code>/submit", methods=["POST"])
def submit(code):
    games = _load_games()
    if code not in games:
        abort(404)
    kind = request.form.get("kind", "")
    if kind not in ("bug", "feature"):
        abort(400)
    body = request.form.get("body", "").strip()
    if not body:
        abort(400)

    slug     = games[code]["slug"]
    dest_dir = GAMES_DIR / slug / "feedback"
    dest_dir.mkdir(exist_ok=True)

    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{ts}_{kind}.json"
    payload  = {
        "type":      kind,
        "body":      body,
        "ip":        request.remote_addr,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "game":      slug,
    }
    (dest_dir / filename).write_text(json.dumps(payload, indent=2))

    return render_template_string(_THANKS, title=games[code]["title"], code=code)


@app.route("/qr/<code>.png")
def qr_image(code):
    games = _load_games()
    if code not in games:
        abort(404)
    url = f"http://{HOST}/{code}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/")
def root():
    games = _load_games()
    links = "".join(
        f'<li><a href="/{code}">{info["title"]}</a> ({code})</li>'
        for code, info in sorted(games.items(), key=lambda x: x[1]["title"])
    )
    return f"<ul>{links}</ul>", 200, {"Content-Type": "text/html"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
