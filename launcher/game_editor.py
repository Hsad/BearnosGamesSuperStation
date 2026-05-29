#!/usr/bin/env python3
"""Game Editor screen — view spec and (future) mod/broken actions."""

import json
import os
import sys
import threading
import time

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from input_handler import poll_input, Action
from game_creator import _load_builders, _run_build, _slugify, check_build_limits, _count_running_for, _hours_since_last_oneshot

ARCADE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_DIR   = os.path.join(ARCADE_DIR, "games", "_queue")
HOLD_WINDOW = 0.8



def _meta_path(game) -> str:
    return os.path.join(game.directory, "meta.json")

def _build_ordered(game) -> bool:
    try:
        with open(_meta_path(game)) as f:
            return json.load(f).get("build_ordered", False)
    except Exception:
        return False

def _set_build_ordered(game) -> None:
    path = _meta_path(game)
    try:
        with open(path) as f:
            meta = json.load(f)
        meta["build_ordered"] = True
        with open(path, "w") as f:
            json.dump(meta, f, indent=2)
    except Exception:
        pass

def _feedback_code(game) -> str | None:
    try:
        with open(_meta_path(game)) as f:
            return json.load(f).get("feedback_code")
    except Exception:
        return None

def _make_menu_items(game) -> list:
    can_build = not _build_ordered(game)
    items = []
    if _feedback_code(game):
        items.append(("Give Feedback", True))
    items += [
        ("View Spec",       True),
        ("Build This Game", can_build),
        ("Mod This Game",   False),
        ("Mark as Broken",  False),
    ]
    return items

def _matrix_to_halfblock(matrix: list) -> list[str]:
    lines = []
    n = len(matrix)
    for row_i in range(0, n, 2):
        top = matrix[row_i]
        bot = matrix[row_i + 1] if row_i + 1 < n else [False] * len(top)
        line = ""
        for t, b in zip(top, bot):
            if t and b:
                line += "█"
            elif t:
                line += "▀"
            elif b:
                line += "▄"
            else:
                line += " "
        lines.append(line)
    return lines

def _make_datamatrix_lines(game) -> list[str]:
    code = _feedback_code(game)
    if not code:
        return ["[No feedback code configured]"]
    url = f"https://tmnt.starcatcher/{code}"
    try:
        import sys, types
        if "distutils" not in sys.modules:
            _dist = types.ModuleType("distutils")
            _ver  = types.ModuleType("distutils.version")
            class _LV:
                def __init__(self, s): pass
                def __lt__(self, o): return False
                def __ge__(self, o): return True
            _ver.LooseVersion = _LV
            _dist.version = _ver
            sys.modules["distutils"]         = _dist
            sys.modules["distutils.version"] = _ver
        from pylibdmtx.pylibdmtx import encode as dm_encode
        from PIL import Image
        MODULE_SIZE = 5  # pylibdmtx default
        encoded = dm_encode(url.encode())
        img     = Image.frombytes("RGB", (encoded.width, encoded.height), encoded.pixels)
        modules_w = encoded.width  // MODULE_SIZE
        modules_h = encoded.height // MODULE_SIZE
        img     = img.resize((modules_w, modules_h), Image.NEAREST).convert("1")
        matrix  = [[not img.getpixel((x, y)) for x in range(img.width)]
                   for y in range(img.height)]
        return _matrix_to_halfblock(matrix)
    except ImportError:
        return ["[install python3-pylibdmtx]"]
    except Exception as e:
        return [f"[Data Matrix error: {e}]"]

def _make_qr_lines(game) -> list[str]:
    code = _feedback_code(game)
    if not code:
        return ["[No feedback code configured]"]
    url = f"https://tmnt.starcatcher/{code}"
    try:
        import qrcode as _qr
        qr = _qr.QRCode(border=4)
        qr.add_data(url)
        qr.make(fit=True)
        return _matrix_to_halfblock(qr.get_matrix())
    except Exception as e:
        return [f"[QR error: {e}]"]

def _read_spec_lines(game, cols: int) -> list[str]:
    meta_path = os.path.join(game.directory, "meta.json")
    spec_rel  = None
    try:
        with open(meta_path) as f:
            spec_rel = json.load(f).get("spec_path")
    except Exception:
        pass

    path = (os.path.join(ARCADE_DIR, spec_rel) if spec_rel
            else os.path.join(QUEUE_DIR, f"{game.slug}.md"))
    try:
        with open(path) as f:
            raw = f.read().splitlines()
    except Exception:
        return ["[Spec file not found]", "", f"Expected: {path}"]

    max_w = cols - 4

    def _wrap(line):
        if len(line) <= max_w:
            return [line]
        stripped  = line.lstrip()
        indent    = " " * (len(line) - len(stripped))
        if stripped.startswith("- "):
            first_pfx = indent + "- "
            cont_pfx  = indent + "  "
            words     = stripped[2:].split()
        else:
            first_pfx = indent
            cont_pfx  = indent
            words     = stripped.split()
        result, cur, pfx = [], "", first_pfx
        for word in words:
            if not cur:
                cur = pfx + word
            elif len(cur) + 1 + len(word) <= max_w:
                cur += " " + word
            else:
                result.append(cur)
                cur = cont_pfx + word
                pfx = cont_pfx
        if cur:
            result.append(cur)
        return result or [line]

    out = []
    for line in raw:
        out.extend(_wrap(line))
    return out


def run_game_editor(app, game) -> None:
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

    SCROLL_INTERVAL = 1.0 / 7

    state          = "EDIT_MENU"
    sel            = 0
    scroll         = 0
    last_scroll_t  = 0.0
    INPUT_GRACE    = 0.35
    spec_lines       = _read_spec_lines(game, cols)
    dm_lines         = _make_datamatrix_lines(game)
    qr_lines         = _make_qr_lines(game)
    feedback_showing = "dm"
    menu_items       = _make_menu_items(game)

    builders        = _load_builders()
    builder_sel     = [0]
    _build_result   = [None]
    _build_loading  = [False]
    _build_lock     = threading.Lock()
    _build_finish_t = [0.0]

    last_attack: dict = {}
    last_jump:   dict = {}

    def track(evs):
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

    clock   = pygame.time.Clock()
    running = True

    _prev_state    = None
    state_entered_t = time.monotonic()

    while running:
        clock.tick(30)
        pygame.event.pump()
        events = poll_input(app.fds, app.ctrl, timeout_ms=0)
        if state != _prev_state:
            state_entered_t = time.monotonic()
            _prev_state     = state
        if time.monotonic() - state_entered_t < INPUT_GRACE:
            events = []
        track(events)

        # JUMP+ATTACK: back one level (spec → menu) or exit (menu → launcher)
        if both_held():
            last_attack.clear()
            last_jump.clear()
            if state == "SPEC_VIEW":
                state  = "EDIT_MENU"
                sel    = 0
                scroll = 0
            else:
                running = False
            continue

        if state == "EDIT_MENU":
            s = surf()
            header(s)
            dc(s, game.title.upper(), 7, R.COL_CREAM)

            if _build_ordered(game):
                dc(s, "[ BUILD  ORDERED ]", 9, R.COL_ACCENT)
            elif game.game_dev_status == "coming_soon":
                dc(s, "[ COMING  SOON™ ]", 9, R.COL_DIM)
            else:
                dc(s, "[ GENERATED ]", 9, R.COL_DIM)

            item_start = rows // 2 - len(menu_items) // 2
            for i, (label, active) in enumerate(menu_items):
                is_sel = (i == sel)
                prefix = "►  " if is_sel else "   "
                color  = (R.COL_CREAM if active else R.COL_DIM) if is_sel else (R.COL_SEPIA if active else R.COL_DIM)
                suffix = "" if active else "   · future"
                dc(s, prefix + label + suffix, item_start + i * 2, color)

            footer(s, "▲/▼ NAVIGATE   ATTACK=SELECT   JUMP=BACK   JUMP+ATTACK=EXIT")
            finish(s)

            for ev in events:
                if ev.action == Action.UP:
                    sel = (sel - 1) % len(menu_items)
                elif ev.action == Action.DOWN:
                    sel = (sel + 1) % len(menu_items)
                elif ev.action == Action.ATTACK:
                    label, active = menu_items[sel]
                    if active and label == "Give Feedback":
                        state = "FEEDBACK"
                    elif active and label == "View Spec":
                        state  = "SPEC_VIEW"
                        scroll = 0
                    elif active and label == "Build This Game":
                        builder_sel[0] = 0
                        state = "BUILDER_PICK"
                elif ev.action == Action.JUMP:
                    running = False

        elif state == "SPEC_VIEW":
            s = surf()
            header(s)
            dc(s, f"SPEC  —  {game.title.upper()}", 7, R.COL_CREAM)

            content_start = 9
            content_end   = rows - 2
            visible       = content_end - content_start + 1
            max_scroll    = max(0, len(spec_lines) - visible)
            scroll        = min(scroll, max_scroll)

            for i in range(visible):
                idx = scroll + i
                if idx >= len(spec_lines):
                    break
                line = spec_lines[idx]
                if line.startswith("## "):
                    color = R.COL_ACCENT
                    line  = line[3:]
                elif line.startswith("---") or line.startswith("title:") or line.startswith("slug:"):
                    color = R.COL_DIM
                else:
                    color = R.COL_SEPIA
                dc(s, line, content_start + i, color)

            footer(s, "▲/▼ SCROLL   JUMP=BACK   JUMP+ATTACK=EXIT")
            finish(s)

            for ev in events:
                now = time.monotonic()
                if ev.action == Action.UP and now - last_scroll_t >= SCROLL_INTERVAL:
                    scroll = max(0, scroll - 1)
                    last_scroll_t = now
                elif ev.action == Action.DOWN and now - last_scroll_t >= SCROLL_INTERVAL:
                    scroll = min(max_scroll, scroll + 1)
                    last_scroll_t = now
                elif ev.action == Action.JUMP:
                    state  = "EDIT_MENU"
                    sel    = 0
                    scroll = 0

        elif state == "FEEDBACK":
            s    = surf()
            code = _feedback_code(game)
            url  = f"http://tmnt.starcatcher/{code}"

            if feedback_showing == "dm":
                active_lines = dm_lines
                mode_label   = "DATA MATRIX"
                hint         = "ATTACK=SHOW QR   JUMP=BACK   JUMP+ATTACK=EXIT"
            else:
                active_lines = qr_lines
                mode_label   = "QR CODE"
                hint         = "ATTACK=SHOW DATA MATRIX   JUMP=BACK   JUMP+ATTACK=EXIT"

            header(s)
            dc(s, game.title.upper(), 7, R.COL_CREAM)
            dc(s, url, 9, R.COL_ACCENT)
            dc(s, mode_label, 11, R.COL_DIM)

            code_start = 13
            for i, line in enumerate(active_lines):
                dc(s, line, code_start + i, R.COL_CREAM)

            footer(s, hint)
            finish(s)

            for ev in events:
                if ev.action == Action.ATTACK:
                    feedback_showing = "qr" if feedback_showing == "dm" else "dm"
                elif ev.action == Action.JUMP:
                    state            = "EDIT_MENU"
                    sel              = 0
                    feedback_showing = "dm"

        elif state == "BUILDER_PICK":
            selected_bid  = builders[builder_sel[0]].get("id", "") if builders else ""
            can_build, limit_reason = check_build_limits(selected_bid)

            s = surf()
            header(s)
            dc(s, f"BUILD  —  {game.title.upper()}", 7, R.COL_CREAM)

            if can_build:
                num_running = _count_running_for(selected_bid)
                since       = _hours_since_last_oneshot() if selected_bid == "oneshot" else None
                if since is None:
                    status_txt = "no recent builds"
                else:
                    status_txt = f"last build {since:.1f}h ago"
                if num_running:
                    status_txt = f"{num_running} running  ·  {status_txt}"
                dc(s, status_txt, 9, R.COL_DIM)
            else:
                dc(s, f"[ {limit_reason} ]", 9, R.COL_DANGER)

            mid = rows // 2 - len(builders) // 2
            for i, b in enumerate(builders):
                is_sel = (i == builder_sel[0])
                prefix = "►  " if is_sel else "   "
                active = can_build or b.get("id") != "oneshot"
                color  = (R.COL_CREAM if active else R.COL_DIM) if is_sel else (R.COL_SEPIA if active else R.COL_DIM)
                dc(s, prefix + b["name"], mid + i, color)

            hint = "▲/▼ NAVIGATE   ATTACK=SELECT   JUMP=BACK" if can_build else "JUMP=BACK"
            footer(s, hint)
            finish(s)

            for ev in events:
                if ev.action == Action.UP:
                    builder_sel[0] = (builder_sel[0] - 1) % max(len(builders), 1)
                elif ev.action == Action.DOWN:
                    builder_sel[0] = (builder_sel[0] + 1) % max(len(builders), 1)
                elif ev.action == Action.JUMP:
                    state = "EDIT_MENU"
                elif ev.action == Action.ATTACK and can_build:
                    chosen = builders[builder_sel[0]]
                    slug   = game.slug or _slugify(game.title)
                    sp     = os.path.join(QUEUE_DIR, f"{slug}.md")
                    _set_build_ordered(game)
                    menu_items = _make_menu_items(game)
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
                    dc(s, msg[:cols - 4], rows // 2, R.COL_SEPIA)
                footer(s, "returning to menu ...")
                if time.monotonic() - _build_finish_t[0] > 3.0:
                    _build_finish_t[0] = 0.0
                    state = "EDIT_MENU"

            finish(s)

            for ev in events:
                if ev.action == Action.JUMP:
                    state = "EDIT_MENU"

    R.clear_scene_cache()
