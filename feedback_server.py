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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import qrcode
import requests
import urllib3
from flask import Flask, abort, redirect, render_template_string, request, send_file, url_for

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ARCADE_DIR = Path(__file__).parent
GAMES_DIR  = ARCADE_DIR / "games"
CONFIG_DIR = ARCADE_DIR / "config"
HOST       = "tmnt.starcatcher"
PORT       = 443
TLS_CERT   = CONFIG_DIR / "tmnt.crt"
TLS_KEY    = CONFIG_DIR / "tmnt.key"

SPARK_HOST         = "192.168.1.150"
GRANITE_URL        = f"https://{SPARK_HOST}:8870/api/transcribe"
SPARK_LAUNCHER     = f"http://{SPARK_HOST}:3456/launcher"
GRANITE_TIMEOUT_S  = 300
AUDIO_EXTS         = (".webm", ".m4a", ".ogg", ".wav", ".mp3", ".mp4")
SWEEP_INTERVAL_S   = 15
SWEEP_BACKOFF_S    = 120  # used when Spark unreachable entirely (powered off / no route)
WAKE_POLL_S        = 5
WAKE_TIMEOUT_S     = 90

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
  .btn-voice   { background: #1a0a2a; border-color: #aa66ff; color: #cc99ff; }
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
  <a class="btn btn-voice"   href="{{ url_for('voice', code=code) }}">🎙 Voice Notes</a>
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

_VOICE = _BASE.replace("{% block body %}{% endblock %}", """
<header>
  <small>{{ title }}</small>
  <h1>Voice Notes</h1>
</header>
<style>
  #ptt {
    width: 220px; height: 220px; border-radius: 50%;
    background: #1a0a2a; border: 4px solid #aa66ff;
    color: #cc99ff; font-size: 1.2rem; font-weight: 600;
    display: flex; align-items: center; justify-content: center;
    user-select: none; -webkit-user-select: none;
    touch-action: none; cursor: pointer;
    transition: transform .08s, background .08s;
  }
  #ptt.rec { background: #aa1144; border-color: #ff4488; color: #fff; transform: scale(1.05); }
  #status { color: #8080b0; font-size: .9rem; min-height: 1.2em; text-align: center; }
  #clips  { width: 100%; max-width: 320px; display: flex; flex-direction: column; gap: .4rem; }
  .clip   { background: #12121e; border: 1px solid #2a2a4a; border-radius: 6px;
            padding: .5rem .75rem; font-size: .85rem; color: #a0a0c0;
            display: flex; justify-content: space-between; }
  .clip .ok { color: #88ee99; }
  .clip .err { color: #ff8888; }
</style>
<div id="ptt">Hold to talk</div>
<div id="status">Tap and hold the button while speaking</div>
<div id="clips"></div>
<a class="back" href="{{ url_for('index', code=code) }}">← back</a>

<script>
(() => {
  const code = {{ code|tojson }};
  const btn = document.getElementById('ptt');
  const status = document.getElementById('status');
  const clips = document.getElementById('clips');
  let stream = null, rec = null, chunks = [], startedAt = 0, timer = null;

  async function ensureStream() {
    if (stream) return stream;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('getUserMedia unavailable (need HTTPS)');
    }
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    return stream;
  }

  function pickMime() {
    const cands = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'];
    for (const m of cands) if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m;
    return '';
  }

  async function start(ev) {
    ev.preventDefault();
    if (rec && rec.state === 'recording') return;
    try {
      await ensureStream();
    } catch (e) {
      status.textContent = 'Mic error: ' + e.message;
      return;
    }
    chunks = [];
    const mime = pickMime();
    rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
    rec.onstop = onStop;
    rec.start();
    startedAt = Date.now();
    btn.classList.add('rec');
    btn.textContent = 'Release to send';
    timer = setInterval(() => {
      const s = ((Date.now() - startedAt) / 1000).toFixed(1);
      status.textContent = 'Recording… ' + s + 's';
    }, 100);
  }

  function stop(ev) {
    ev.preventDefault();
    if (rec && rec.state === 'recording') rec.stop();
  }

  async function onStop() {
    clearInterval(timer);
    btn.classList.remove('rec');
    btn.textContent = 'Hold to talk';
    const dur = ((Date.now() - startedAt) / 1000).toFixed(1);
    const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
    chunks = [];

    const row = document.createElement('div');
    row.className = 'clip';
    const left = document.createElement('span');
    const ts = new Date().toLocaleTimeString();
    left.textContent = ts + ' · ' + dur + 's';
    const right = document.createElement('span');
    right.textContent = 'uploading…';
    row.append(left, right);
    clips.prepend(row);

    try {
      const ext = (blob.type.includes('mp4') ? 'm4a' :
                   blob.type.includes('ogg') ? 'ogg' : 'webm');
      const fd = new FormData();
      fd.append('audio', blob, 'clip.' + ext);
      fd.append('duration', dur);
      fd.append('client_ts', new Date().toISOString());
      const r = await fetch('/' + code + '/voice/submit', { method: 'POST', body: fd });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      right.innerHTML = '<span class="ok">✓ saved</span>';
      status.textContent = 'Saved ' + j.filename;
    } catch (e) {
      right.innerHTML = '<span class="err">✗ ' + e.message + '</span>';
      status.textContent = 'Upload failed';
    }
  }

  btn.addEventListener('pointerdown', start);
  btn.addEventListener('pointerup', stop);
  btn.addEventListener('pointerleave', stop);
  btn.addEventListener('pointercancel', stop);
})();
</script>
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


@app.route("/<code>/voice")
def voice(code):
    games = _load_games()
    if code not in games:
        abort(404)
    return render_template_string(_VOICE, title=games[code]["title"], code=code)


@app.route("/<code>/voice/submit", methods=["POST"])
def voice_submit(code):
    games = _load_games()
    if code not in games:
        abort(404)
    f = request.files.get("audio")
    if not f:
        abort(400, "missing audio")

    slug      = games[code]["slug"]
    voice_dir = GAMES_DIR / slug / "feedback" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    ts       = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")[:-3] + "Z"
    ext      = os.path.splitext(f.filename or "clip.webm")[1] or ".webm"
    audio_fn = f"{ts}{ext}"
    meta_fn  = f"{ts}.json"
    (voice_dir / audio_fn).write_bytes(f.read())

    payload = {
        "audio":     audio_fn,
        "mime":      f.mimetype,
        "duration":  request.form.get("duration"),
        "client_ts": request.form.get("client_ts"),
        "ip":        request.remote_addr,
        "server_ts": datetime.now(timezone.utc).isoformat(),
        "game":      slug,
    }
    (voice_dir / meta_fn).write_text(json.dumps(payload, indent=2))
    return {"ok": True, "filename": audio_fn}


@app.route("/qr/<code>.png")
def qr_image(code):
    games = _load_games()
    if code not in games:
        abort(404)
    url = f"https://{HOST}/{code}"
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


# ── Transcription worker ───────────────────────────────────────────────────────

def _stt_ready() -> bool | None:
    """True if STT is up, False if launcher reports it down, None if unreachable."""
    try:
        r = requests.get(f"{SPARK_LAUNCHER}/status", timeout=3)
        if r.status_code != 200:
            return None
        return bool(r.json().get("stt"))
    except requests.exceptions.RequestException:
        return None


def _wake_stt() -> bool:
    """Ask the Spark launcher to start STT and poll until ready.
    Returns True if STT became ready, False on timeout or launcher unreachable."""
    try:
        requests.post(f"{SPARK_LAUNCHER}/start/stt", timeout=5)
    except requests.exceptions.RequestException as e:
        print(f"[wake] launcher unreachable: {e}", flush=True)
        return False

    print("[wake] start/stt issued; polling…", flush=True)
    deadline = time.monotonic() + WAKE_TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(WAKE_POLL_S)
        ready = _stt_ready()
        if ready is True:
            print("[wake] stt ready", flush=True)
            return True
        if ready is None:
            print("[wake] launcher unreachable mid-poll", flush=True)
            return False
    print("[wake] timed out waiting for stt", flush=True)
    return False


def _iter_pending_audio():
    for ext in AUDIO_EXTS:
        for audio in GAMES_DIR.glob(f"*/feedback/voice/*{ext}"):
            if audio.with_suffix(".txt").exists():
                continue
            yield audio


def _transcribe_one(audio_path: Path) -> str:
    """POST audio to Granite. Returns 'ok', 'offline', or 'error:<msg>'."""
    try:
        with audio_path.open("rb") as f:
            r = requests.post(
                GRANITE_URL,
                files={"file": (audio_path.name, f, "application/octet-stream")},
                verify=False,
                timeout=GRANITE_TIMEOUT_S,
            )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return "offline"
    except requests.exceptions.RequestException as e:
        return f"error:{e}"

    if r.status_code != 200:
        return f"error:HTTP {r.status_code}"

    try:
        text = (r.json().get("text") or "").strip()
    except ValueError:
        return "error:bad json"

    audio_path.with_suffix(".txt").write_text(text)
    meta_path = audio_path.with_suffix(".json")
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            meta["transcript"]      = text
            meta["transcribed_at"]  = datetime.now(timezone.utc).isoformat()
            meta_path.write_text(json.dumps(meta, indent=2))
        except Exception:
            pass
    return "ok"


def _transcribe_worker():
    while True:
        delay = SWEEP_INTERVAL_S
        try:
            pending = list(_iter_pending_audio())
            if pending:
                ready = _stt_ready()
                if ready is None:
                    # Spark launcher itself unreachable — likely powered off / DNS / network.
                    # Nothing we can do here yet (future: WoL); back off.
                    print("[transcribe] spark launcher unreachable, backing off", flush=True)
                    delay = SWEEP_BACKOFF_S
                elif ready is False:
                    if not _wake_stt():
                        delay = SWEEP_BACKOFF_S
                        pending = []
                for audio in pending:
                    result = _transcribe_one(audio)
                    print(f"[transcribe] {audio.name}: {result}", flush=True)
                    if result == "offline":
                        # STT went away mid-batch; stop and let next sweep re-wake.
                        delay = SWEEP_BACKOFF_S
                        break
        except Exception as e:
            print(f"[transcribe] sweep error: {e}", flush=True)
        time.sleep(delay)


if __name__ == "__main__":
    threading.Thread(target=_transcribe_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT,
            ssl_context=(str(TLS_CERT), str(TLS_KEY)))
