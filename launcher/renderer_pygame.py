#!/usr/bin/env python3
"""
Pygame CRT renderer — drop-in replacement for renderer.py.
Public API: get_terminal_size, term_enter_alt_screen, term_leave_alt_screen,
            render, render_screensaver, render_launching, flicker_tick.
"""

import os
import math
import random
import pygame
import numpy as np

from renderer import (BLOCK_FONT, KHI_LOGO, SUBTEXT_1, SUBTEXT_2,
                      _star_char, _card_box, _center)

SCREEN_W, SCREEN_H = 1920, 1080
FONT_SIZE = 22

# Sepia CRT palette — same values as the ANSI renderer
COL_BG     = (  8,   8,   6)
COL_CREAM  = (240, 235, 220)
COL_SEPIA  = (190, 185, 170)
COL_DIM    = ( 90,  85,  75)
COL_ACCENT = (160, 150, 120)
COL_DANGER = (200, 140,  90)

# CRT effect params — tweak to taste
SCANLINE_ALPHA = 70    # 0-255 darkness of every-other-row scanlines
VIGNETTE_MAX   = 170   # 0-255 max corner darkness
GLOW_STRENGTH  = 0.30  # 0 = off
BARREL_K       = 0.06  # screen curvature; 0 = off, higher = more curve
FLICKER_CHANCE = 0.30  # probability per tick that a flicker frame fires
FLICKER_DEPTH  = 28    # max brightness drop per flicker event (0-255)

# Boot sequence messages — left column is padded with dots to BOOT_COL_W chars
BOOT_COL_W = 42
BOOT_LINE_T = 0.15   # seconds per message line
BOOT_MESSAGES = [
    ("BIOS CHECKSUM",                        "FF3A 9BC1  [PASS]"),
    ("SYSTEM RAM DETECTION",                 "32 MB FOUND"),
    ("DOWNLOADING MORE RAM",                 "COMPLETE  [OK]"),
    ("EXTENDED MEMORY TEST 640K",            "[PASS]"),
    ("LAST DATUM",                           "5318008"),
    ("GRID INTERFACE CONTROLLER",            "ONLINE    [OK]"),
    ("LIGHT CYCLE ENGINE v7.1",              "LOADED    [OK]"),
    ("MONTY PYTHON2.7",                      "!DEAD     [YET]"),
    ("NEON CORTEX NEURAL ENGINE",            "NOMINAL   [OK]"),
    ("PRAYING TO ODIN",                      "DONE"),
    ("MCP UPLINK STATUS",                    "CONNECTED"),
    ("UNAUTHORIZED PROGRAM SCAN",            "[1] FOUND"),
    ("SANDBOXING DPRK BOTNET",               "DONE"),
    ("LASER NET ALIGNMENT",                  "[PEW][PEW]"),
    ("WEAPONS GRADE VR",                     "LUCKY"),
    ("USER IDENTITY VERIFICATION",           "MOGGING"),
    ("HYPERSPACE COORDINATE LOCK",           "LOST"),
    ("SYNTHWAVE AUDIO DRIVER v8.4",          "LOADED    [OK]"),
    ("JOYSTICK ARRAY CALIBRATION x4",        "[OK]"),
    ("VAPORWAVE RENDERING PIPELINE",         "READY     [OK]"),
    ("TEMPORAL ALIGNMENT: 1993",             "LOCKED"),
]

_screen:       pygame.Surface | None = None
_font:         pygame.font.Font | None = None
_char_w:       int = 0
_char_h:       int = 0
_term_rows:    int = 0
_term_cols:    int = 0
_overlay:      pygame.Surface | None = None  # pre-baked scanlines + vignette
_starfield:    pygame.Surface | None = None  # pre-rendered static background
_barrel_sxi:   np.ndarray | None = None      # (W, H) int32 clamped source x
_barrel_syi:   np.ndarray | None = None      # (W, H) int32 clamped source y
_barrel_valid: np.ndarray | None = None      # (W, H) bool in-bounds mask
_last_scene:   pygame.Surface | None = None  # copy of last composited frame
_scene_cache:  dict[int, pygame.Surface] = {}  # game_idx → ready-to-blit surface
_glyph_cache:  dict = {}


# ── Initialization ─────────────────────────────────────────────────────────────

def _init_pygame() -> None:
    global _screen, _font, _char_w, _char_h
    global _term_rows, _term_cols, _overlay, _starfield
    global _barrel_sxi, _barrel_syi, _barrel_valid, _scene_cache, _glyph_cache

    os.environ.setdefault('SDL_VIDEODRIVER', 'kmsdrm')
    pygame.init()
    pygame.mouse.set_visible(False)

    try:
        _screen = pygame.display.set_mode(
            (SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME)
    except Exception:
        _screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption('Bearnos Arcade')

    home = os.path.expanduser('~')
    font_paths = [
        os.path.join(home, '.local/share/fonts/DepartureMono-Regular.otf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
        '/usr/share/fonts/truetype/freefont/FreeMono.ttf',
    ]
    _font = None
    for p in font_paths:
        if os.path.exists(p):
            _font = pygame.font.Font(p, FONT_SIZE)
            break
    if _font is None:
        _font = pygame.font.SysFont('monospace', FONT_SIZE)

    sample = _font.render('M', True, (255, 255, 255))
    _char_w = sample.get_width()
    _char_h = sample.get_height()
    _term_cols = SCREEN_W // _char_w
    _term_rows = SCREEN_H // _char_h
    _glyph_cache = {}

    _overlay   = _build_overlay()
    _starfield = _build_starfield()
    _scene_cache = {}
    if BARREL_K:
        _barrel_sxi, _barrel_syi, _barrel_valid = _build_barrel_map()
    else:
        _barrel_sxi = _barrel_syi = _barrel_valid = None

    # Log usable textcard dimensions for game authors
    tc_max_w = _term_cols
    tc_max_h = _term_rows - 8   # rows below the 5-line header + 2 footer rows + 1 buffer
    import sys
    print(f'[renderer] font: {_char_w}×{_char_h}px  grid: {_term_cols}×{_term_rows}'
          f'  textcard max: {tc_max_w}w × {tc_max_h}h chars', file=sys.stderr)


def _build_overlay() -> pygame.Surface:
    """Pre-bake scanlines + vignette into a single SRCALPHA surface."""
    surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))

    # Horizontal scanlines every other row
    for y in range(0, SCREEN_H, 2):
        pygame.draw.line(surf, (0, 0, 0, SCANLINE_ALPHA),
                         (0, y), (SCREEN_W - 1, y))

    # Vignette: radial dark gradient toward screen edges
    cx, cy = SCREEN_W / 2.0, SCREEN_H / 2.0
    max_r  = math.sqrt(cx * cx + cy * cy)
    xs = np.arange(SCREEN_W, dtype=np.float32)
    ys = np.arange(SCREEN_H, dtype=np.float32)
    xx, yy = np.meshgrid(xs, ys)
    dist   = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    t      = np.clip((dist / max_r - 0.30) / 0.70, 0.0, 1.0)
    smooth = t * t * (3.0 - 2.0 * t)
    alpha  = (smooth * VIGNETTE_MAX).astype(np.uint8)   # (H, W)

    vig = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    vig.fill((0, 0, 0, 0))
    pxa = pygame.surfarray.pixels_alpha(vig)             # (W, H) view
    pxa[:, :] = alpha.T
    del pxa

    surf.blit(vig, (0, 0))
    return surf


def _build_starfield() -> pygame.Surface:
    """Pre-render the static star field so render() can blit it cheaply."""
    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    surf.fill(COL_BG)
    for r in range(7, _term_rows + 1):
        for c in range(1, _term_cols + 1):
            ch = _star_char(r, c)
            if ch != ' ':
                surf.blit(_glyph(ch, COL_DIM),
                          ((c - 1) * _char_w, (r - 1) * _char_h))
    return surf


def _build_barrel_map() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Pre-compute CRT screen-curvature remap tables, ready for use each frame.
    Returns (sxi, syi, valid) all in (W, H) pygame-surfarray layout:
      sxi/syi  — int32 source coords clamped to surface bounds
      valid    — bool mask; False pixels are forced to black
    """
    xd = np.arange(SCREEN_W, dtype=np.float32)
    yd = np.arange(SCREEN_H, dtype=np.float32)
    xxd, yyd = np.meshgrid(xd, yd)           # (H, W)

    nx = 2.0 * xxd / SCREEN_W - 1.0
    ny = 2.0 * yyd / SCREEN_H - 1.0
    r2 = nx * nx + ny * ny

    factor = 1.0 + BARREL_K * r2
    xs = (nx * factor + 1.0) * SCREEN_W / 2.0   # (H, W) float
    ys = (ny * factor + 1.0) * SCREEN_H / 2.0

    # Transpose to (W, H) and pre-compute everything the render loop needs
    xs = xs.T;  ys = ys.T
    valid = (xs >= 0) & (xs < SCREEN_W) & (ys >= 0) & (ys < SCREEN_H)
    sxi   = np.clip(xs, 0, SCREEN_W - 1).astype(np.int32)
    syi   = np.clip(ys, 0, SCREEN_H - 1).astype(np.int32)
    return sxi, syi, valid


# ── Glyph cache and drawing helpers ───────────────────────────────────────────

def _glyph(text: str, color: tuple) -> pygame.Surface:
    key = (text, color)
    if key not in _glyph_cache:
        _glyph_cache[key] = _font.render(text, True, color)
    return _glyph_cache[key]


def _draw(surf: pygame.Surface, text: str, row: int, col: int,
          color: tuple) -> None:
    """Blit text at 1-indexed grid (row, col)."""
    if not text:
        return
    surf.blit(_glyph(text, color),
              ((col - 1) * _char_w, (row - 1) * _char_h))


def _draw_centered(surf: pygame.Surface, text: str, row: int,
                   color: tuple) -> None:
    g = _glyph(text, color)
    x = (SCREEN_W - g.get_width()) // 2
    surf.blit(g, (x, (row - 1) * _char_h))


# ── CRT effects ────────────────────────────────────────────────────────────────

def _box_blur(arr: np.ndarray, radius: int) -> np.ndarray:
    """Separable box blur (no edge wrap) using the prefix-sum trick."""
    out = arr.astype(np.float32)
    for axis in (0, 1):
        n = out.shape[axis]
        pad = [1 if a == axis else s for a, s in enumerate(out.shape)]
        cs = np.concatenate(
            [np.zeros(pad, dtype=np.float32), np.cumsum(out, axis=axis)],
            axis=axis)
        i    = np.arange(n)
        lo   = np.maximum(0, i - radius)
        hi   = np.minimum(n, i + radius + 1)
        cnt  = (hi - lo).astype(np.float32)
        sums = np.take(cs, hi, axis=axis) - np.take(cs, lo, axis=axis)
        bcast = [1] * out.ndim
        bcast[axis] = n
        out = sums / cnt.reshape(bcast)
    return out


def _apply_glow(scene: pygame.Surface) -> None:
    """Additive phosphor glow via downscale → blur → upscale → add."""
    if GLOW_STRENGTH <= 0:
        return
    arr = pygame.surfarray.array3d(scene).astype(np.float32) / 255.0  # (W,H,3)

    small = arr[::4, ::4]
    lum   = (0.299 * small[:, :, 0]
           + 0.587 * small[:, :, 1]
           + 0.114 * small[:, :, 2])
    mask  = np.clip((lum - 0.20) * 3.0, 0.0, 1.0)[:, :, np.newaxis]
    bright = small * mask

    glow = _box_blur(bright, radius=8)
    glow = _box_blur(glow,   radius=5)

    glow_up = np.repeat(np.repeat(glow, 4, axis=0), 4, axis=1)
    gw = min(glow_up.shape[0], arr.shape[0])
    gh = min(glow_up.shape[1], arr.shape[1])

    result = arr[:gw, :gh] + glow_up[:gw, :gh] * GLOW_STRENGTH
    np.clip(result, 0.0, 1.0, out=result)
    scene.blit(pygame.surfarray.make_surface((result * 255).astype(np.uint8)),
               (0, 0))


def _apply_barrel(scene: pygame.Surface) -> None:
    """Remap pixels through the pre-computed barrel/screen-curvature map."""
    if _barrel_sxi is None:
        return
    arr    = pygame.surfarray.array3d(scene)   # (W, H, 3)
    result = arr[_barrel_sxi, _barrel_syi]     # fancy index with pre-clipped int32
    result[~_barrel_valid] = 0                 # out-of-bounds → black
    scene.blit(pygame.surfarray.make_surface(result), (0, 0))


# ── Public API ─────────────────────────────────────────────────────────────────

def get_terminal_size() -> tuple[int, int]:
    return (_term_rows, _term_cols) if _term_rows else (30, 80)


def term_enter_alt_screen() -> None:
    _init_pygame()


def term_leave_alt_screen() -> None:
    pygame.quit()


def flicker_tick() -> None:
    """
    Call from the main loop each iteration.  With probability FLICKER_CHANCE,
    re-blits the last rendered frame with a random dim overlay to simulate
    phosphor decay / CRT refresh flicker.
    """
    global _last_scene
    if _screen is None or _last_scene is None:
        return
    pygame.event.pump()
    if random.random() > FLICKER_CHANCE:
        return
    alpha = random.randint(2, FLICKER_DEPTH)
    _screen.blit(_last_scene, (0, 0))
    dark = pygame.Surface((SCREEN_W, SCREEN_H))
    dark.fill((0, 0, 0))
    dark.set_alpha(alpha)
    _screen.blit(dark, (0, 0))
    pygame.display.flip()


def _finish_frame(scene: pygame.Surface) -> None:
    """Apply overlay, store last_scene, blit to screen."""
    global _last_scene
    scene.blit(_overlay, (0, 0))
    _last_scene = scene.copy()
    _screen.blit(scene, (0, 0))
    pygame.display.flip()


def _compose_menu(app, idx: int | None = None) -> pygame.Surface:
    """Build the menu scene with glow applied. No barrel or overlay yet."""
    if idx is None:
        idx = app.selected
    rows, cols = app.term_rows, app.term_cols
    scene = _starfield.copy()

    # Header — strip leading/trailing spaces so pixel-centering is accurate
    for i, line in enumerate(KHI_LOGO):
        _draw_centered(scene, line.strip(), i + 1, COL_CREAM)
    _draw_centered(scene, SUBTEXT_1.strip() + '  ', 4, COL_CREAM)
    _draw_centered(scene, SUBTEXT_2.strip() + '  ', 5, COL_CREAM)

    games = app.game_list()
    count = len(games)

    if count == 0:
        mid = rows // 2
        _draw_centered(scene, 'NO GAMES INSTALLED', mid, COL_DANGER)
        _draw_centered(scene,
                       'drop a game folder into ~/Arcade/games/', mid + 1, COL_DIM)
    else:
        game = games[idx]

        if game.textcard:
            _render_textcard_full(scene, game, rows)
        else:
            box_row, box_col, box_h, box_w = _card_box(rows, cols)

            info_row  = box_row - 1
            desc_row  = box_row - 2
            title_row = max(7, box_row - 4)
            desc_row  = max(title_row + 1, desc_row)
            info_row  = max(desc_row + 1, info_row)

            prev_title = games[(idx - 1) % count].title if count > 1 else ''
            next_title = games[(idx + 1) % count].title if count > 1 else ''
            nav_left   = f'◄ {prev_title}' if count > 1 else ''
            nav_right  = f'{next_title} ►' if count > 1 else ''
            cur_title  = f'[ {game.title} ]'

            _draw(scene, nav_left[:cols // 3], title_row, 2, COL_DIM)
            _draw_centered(scene, cur_title, title_row, COL_CREAM)
            if nav_right:
                _draw(scene, nav_right, title_row,
                      cols - len(nav_right) - 1, COL_DIM)

            _draw_centered(scene, game.description, desc_row, COL_SEPIA)

            info = (f'{game.players} players · by {game.author}'
                    if game.author else f'{game.players} players')
            _draw_centered(scene, info, info_row, COL_DIM)

            _render_block_title(scene, game.title, box_col, box_row, box_w, box_h)

    _draw(scene, ('═' * cols)[:cols], rows - 1, 1, COL_ACCENT)
    _draw_centered(
        scene,
        '◄ LEFT/RIGHT TO BROWSE ►    [ ATTACK ] TO PLAY',
        rows, COL_SEPIA)

    _apply_glow(scene)
    return scene


def clear_scene_cache() -> None:
    """Invalidate all cached game screens (call after game list changes)."""
    _scene_cache.clear()


def _build_scene(app, idx: int) -> pygame.Surface:
    """Full pipeline for one game index → ready-to-blit surface."""
    scene = _compose_menu(app, idx)   # glow already applied inside
    _apply_barrel(scene)
    scene.blit(_overlay, (0, 0))
    return scene


def warm_next_scene_cache(app) -> bool:
    """
    Build one uncached scene (neighbours first).
    Call once per main-loop tick; returns True if work was done.
    """
    if _screen is None:
        return False
    games = app.game_list()
    count = len(games)
    if count == 0:
        return False
    for offset in range(1, count):
        idx = (app.selected + offset) % count
        if idx not in _scene_cache:
            _scene_cache[idx] = _build_scene(app, idx)
            return True
    return False


def render(app) -> None:
    if _screen is None:
        return
    idx = app.selected
    if idx not in _scene_cache:
        _scene_cache[idx] = _build_scene(app, idx)
    global _last_scene
    _last_scene = _scene_cache[idx]
    _screen.blit(_last_scene, (0, 0))
    pygame.display.flip()


def render_boot(app, monitor_was_off: bool = False) -> None:
    """
    CRT power-on + boot-log animation.
    Phases:
      0.00–5.00  blank wait (only when monitor_was_off, while display wakes up)
      +0.00–2.00 CRT hardware startup (spot → line expansion → flash → static)
      +2.00–end  scrolling boot messages, one every BOOT_LINE_T seconds
      +0.70      "BEARNOS GAME STATION ONLINE" finaliser
      +0.80      menu fades in from white
    """
    if _screen is None:
        return

    final     = _compose_menu(app)
    final_arr = pygame.surfarray.array3d(final).astype(np.float32) / 255.0

    MONITOR_DELAY = 5.0 if monitor_was_off else 0.0
    CRT_DUR   = 2.0
    CRT_END   = MONITOR_DELAY + CRT_DUR
    t_text    = CRT_END
    t_online  = t_text + len(BOOT_MESSAGES) * BOOT_LINE_T
    t_fade    = t_online + 0.70
    t_end     = t_fade   + 0.80

    # Boot text pixel layout — centred on screen
    block_chars = BOOT_COL_W + 22           # left col + dots + gap + status
    left_x      = (SCREEN_W - block_chars * _char_w) // 2
    right_x     = left_x + (BOOT_COL_W + 2) * _char_w
    header_y    = 3 * _char_h
    sep_y       = header_y + _char_h
    text_y0     = sep_y + _char_h           # first message row
    SEP         = "═" * block_chars
    HEADER      = "KIELER HEAVY INDUSTRIES - BEARNOS GAMES   ■   BIOS v2.3   ■   (C) 1993"

    cy    = SCREEN_H // 2
    start = pygame.time.get_ticks() / 1000.0

    while True:
        t = pygame.time.get_ticks() / 1000.0 - start
        if t >= t_end:
            break

        pygame.event.pump()
        frame = pygame.Surface((SCREEN_W, SCREEN_H))
        frame.fill(COL_BG)

        # ── Phase 0: blank wait for monitor to wake ───────────────────────────
        if t < MONITOR_DELAY:
            pass  # frame stays black

        # ── Phase 1: CRT hardware startup (2 s) ──────────────────────────────
        elif t < CRT_END:
            tc = t - MONITOR_DELAY   # local time within CRT phase, 0–2.0
            if tc < 0.27:
                p  = tc / 0.27
                rw = int(SCREEN_W * 0.04 * p)
                rh = int(SCREEN_H * 0.008 * p)
                if rw > 0 and rh > 0:
                    pygame.draw.ellipse(
                        frame, (255, 240, 190),
                        pygame.Rect(SCREEN_W // 2 - rw, cy - rh, rw * 2, rh * 2))

            elif tc < 1.20:
                p  = (tc - 0.27) / 0.93
                sp = p * p * (3.0 - 2.0 * p)
                hh = int(cy * sp)
                bright = 255 - int(35 * sp)
                warm   = int(bright * 0.90)
                frame.fill((bright, warm, int(warm * 0.78)),
                           pygame.Rect(0, cy - hh, SCREEN_W, max(2, hh * 2)))

            elif tc < 1.55:
                p      = (tc - 1.20) / 0.35
                bright = int(255 * (1.0 - p * 0.22))
                warm   = int(bright * 0.91)
                frame.fill((bright, warm, int(warm * 0.80)))

            else:
                # Static noise transitioning to dark
                p     = (tc - 1.55) / 0.45
                alpha = int(255 * (1.0 - p))
                noise = np.random.randint(20, 190,
                                          (SCREEN_W, SCREEN_H, 3), dtype=np.uint8)
                noise[:, :, 2] = (noise[:, :, 2].astype(np.uint16) * 55 // 100
                                   ).astype(np.uint8)
                ns = pygame.surfarray.make_surface(noise)
                ns.set_alpha(alpha)
                frame.blit(ns, (0, 0))

        # ── Phase 2: scrolling boot messages ─────────────────────────────────
        elif t < t_online:
            t_rel      = t - t_text
            lines_done = int(t_rel / BOOT_LINE_T)
            line_frac  = (t_rel % BOOT_LINE_T) / BOOT_LINE_T

            frame.blit(_glyph(HEADER, COL_ACCENT),            (left_x, header_y))
            frame.blit(_glyph(SEP[:block_chars], COL_DIM),    (left_x, sep_y))

            # Completed lines (dimmed — they're done)
            for i in range(min(lines_done, len(BOOT_MESSAGES))):
                left, status = BOOT_MESSAGES[i]
                y = text_y0 + i * _char_h
                frame.blit(_glyph(left.ljust(BOOT_COL_W, '.'), COL_DIM),
                           (left_x, y))
                frame.blit(_glyph(status, COL_SEPIA), (right_x, y))

            # Active line: dots appear first, then status flicks on
            if lines_done < len(BOOT_MESSAGES):
                left, status = BOOT_MESSAGES[lines_done]
                dots = left.ljust(BOOT_COL_W, '.')
                y    = text_y0 + lines_done * _char_h
                if line_frac < 0.50:
                    frame.blit(_glyph(dots, COL_SEPIA), (left_x, y))
                else:
                    frame.blit(_glyph(dots, COL_DIM),   (left_x, y))
                    frame.blit(_glyph(status, COL_CREAM), (right_x, y))

        # ── Phase 3: finaliser message ────────────────────────────────────────
        elif t < t_fade:
            frame.blit(_glyph(HEADER, COL_ACCENT),         (left_x, header_y))
            frame.blit(_glyph(SEP[:block_chars], COL_DIM), (left_x, sep_y))
            for i, (left, status) in enumerate(BOOT_MESSAGES):
                y = text_y0 + i * _char_h
                frame.blit(_glyph(left.ljust(BOOT_COL_W, '.'), COL_DIM),
                           (left_x, y))
                frame.blit(_glyph(status, COL_SEPIA), (right_x, y))

            bot_sep_y  = text_y0 + len(BOOT_MESSAGES) * _char_h
            online_y   = bot_sep_y + _char_h
            ready_y    = online_y  + _char_h
            frame.blit(_glyph(SEP[:block_chars], COL_DIM), (left_x, bot_sep_y))

            p      = (t - t_online) / 0.70
            online_col = COL_CREAM if p > 0.25 else COL_DIM
            frame.blit(_glyph("  BEARNOS GAME STATION  ■  ONLINE", online_col),
                       (left_x, online_y))

            # Blinking cursor on the ready line
            if p > 0.55:
                cursor = "█" if int((t - t_online) * 3) % 2 == 0 else " "
                frame.blit(_glyph(f"  > READY PLAYER ONE {cursor}", COL_ACCENT),
                           (left_x, ready_y))

        # ── Phase 4: menu fades in from bright ───────────────────────────────
        else:
            p   = (t - t_fade) / 0.80
            sp  = p * p * (3.0 - 2.0 * p)
            add = (1.0 - sp) * 0.88
            arr = np.clip(final_arr + add * (1.0 - final_arr), 0.0, 1.0)
            frame.blit(pygame.surfarray.make_surface(
                (arr * 255).astype(np.uint8)), (0, 0))

        # Barrel distortion is expensive (~400ms on Pi 4) — only run it for the
        # CRT startup animation and the final fade where the visual matters.
        # Skipping it during text phases keeps each frame under 16ms.
        if MONITOR_DELAY <= t < CRT_END or t >= t_fade:
            _apply_barrel(frame)
        frame.blit(_overlay, (0, 0))
        _screen.blit(frame, (0, 0))
        pygame.display.flip()
        pygame.time.delay(16)

    scene = final.copy()
    _apply_barrel(scene)
    _finish_frame(scene)


def _render_textcard_full(surf, game, rows: int) -> None:
    """
    Render a textcard centered on screen with the actual content block as the
    unit of measurement.  Positions with ~30% whitespace above / ~70% below so
    the card sits in the upper-centre of the content area.
    """
    lines = [l.rstrip() for l in game.textcard.splitlines()]

    # Trim blank lines from top and bottom
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return

    content_w = max(len(l) for l in lines)   # widest line (chars)
    content_h = len(lines)

    # Horizontal: centre the block by pixel; shorter lines stay left-aligned
    # within the block (preserves ASCII-art internal spacing)
    block_px_w = content_w * _char_w
    start_x    = (SCREEN_W - block_px_w) // 2   # may be negative → pygame clips

    # Vertical: available rows are 7..rows-2 (below header, above footer)
    content_start = 7          # first row below subtext
    content_end   = rows - 2
    available_h   = max(1, content_end - content_start + 1)
    gap           = max(0, available_h - content_h)
    top_gap       = int(gap * 0.30)             # 30% above → more room below
    start_row     = content_start + top_gap     # 1-indexed

    for i, line in enumerate(lines):
        r = start_row + i
        if r > content_end:
            break
        if line:
            y = (r - 1) * _char_h
            surf.blit(_glyph(line, COL_CREAM), (start_x, y))


def _render_block_title(surf, title, box_col, box_row, box_w, box_h) -> None:
    chars = [c for c in title.upper() if c in BLOCK_FONT]
    if not chars:
        return

    scale = 1
    while True:
        glyph_w = 5 * (scale + 1)
        gap_w   = scale + 1
        total_w = len(chars) * glyph_w + (len(chars) - 1) * gap_w
        if total_w > int(box_w * 0.90):
            break
        scale += 1
    scale = max(1, scale)

    glyph_w  = 5 * scale
    gap_w    = scale
    total_w  = len(chars) * glyph_w + (len(chars) - 1) * gap_w
    glyph_h  = 5 * scale
    left_pad = max(0, (box_w - total_w) // 2)
    top_pad  = max(0, (box_h - glyph_h) // 2)

    for row_idx in range(5):
        pixel_row = ''
        for ci, ch in enumerate(chars):
            for pixel in BLOCK_FONT[ch][row_idx]:
                pixel_row += ('█' if pixel == '█' else ' ') * scale
            if ci < len(chars) - 1:
                pixel_row += ' ' * gap_w
        for rep in range(scale):
            r = box_row + top_pad + row_idx * scale + rep
            _draw(surf, pixel_row[:box_w], r, box_col + left_pad, COL_CREAM)


def render_screensaver() -> None:
    global _last_scene
    if _screen is None:
        return
    _screen.fill((0, 0, 0))
    pygame.display.flip()
    _last_scene = None   # suppress flicker on blank screen


def render_launching(app) -> None:
    if _screen is None:
        return
    games = app.game_list()
    title = games[app.selected].title if games else '?'
    mid   = app.term_rows // 2

    scene = pygame.Surface((SCREEN_W, SCREEN_H))
    scene.fill(COL_BG)
    _draw_centered(scene, f'LAUNCHING  {title} ...', mid, COL_CREAM)
    _finish_frame(scene)
