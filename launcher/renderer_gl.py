#!/usr/bin/env python3
"""
moderngl CRT renderer — drop-in replacement for renderer_pygame.py.

pygame draws text/glyphs onto offscreen surfaces.  When the scene changes
(navigation, game list update) it is uploaded to a GPU texture.  A fragment
shader runs barrel distortion, scanlines, vignette, phosphor glow, and
flicker every frame — all essentially free on the GPU.

Public API is identical to renderer_pygame.py.
"""

import io, os, random, sys, time, wave
import pygame
import moderngl
import numpy as np

from renderer import (BLOCK_FONT, KHI_LOGO, SUBTEXT_1, SUBTEXT_2,
                      _star_char, _card_box, _center)

SCREEN_W, SCREEN_H = 1920, 1080
GLOW_W = SCREEN_W // 4   # 480
GLOW_H = SCREEN_H // 4   # 270
FONT_SIZE = 22

COL_BG       = (  8,   8,   6)
COL_CREAM    = (240, 235, 220)
COL_SEPIA    = (190, 185, 170)
COL_DIM      = ( 90,  85,  75)
COL_ACCENT   = (160, 150, 120)
COL_DANGER   = (200, 140,  90)
COL_PHOSPHOR = ( 74, 210,  90)

BARREL_K       = 0.15
SCANLINE_ALPHA = 70 / 255.0
VIGNETTE_MAX   = 170 / 255.0
GLOW_STRENGTH  = 0.30
GLOW_THRESHOLD = 0.20
FLICKER_CHANCE = 0.30
FLICKER_DEPTH  = 28

BOOT_VOLUME  = 0.20   # master boot-sound volume — raise once you know the room

def set_boot_volume(vol: float) -> None:
    global BOOT_VOLUME
    BOOT_VOLUME = vol
BOOT_COL_W   = 42
BOOT_LINE_T  = 0.15
BOOT_MESSAGES = [
    ("BIOS CHECKSUM",                 "0xDEADBEEF  [PASS]"),
    ("SYSTEM RAM DETECTION",          "32 MB FOUND"),
    ("DOWNLOADING MORE RAM",          "COMPLETE  [OK]"),
    ("DOWNLOADING ANY VRAM",          "PENDING [NOVIDIA]"),
    ("EXTENDED MEMORY TEST 2GB",      "[PASS]"),
    ("LAST USER HERE",                "KILROY"),
    ("LAST DATUM",                    "5318008"),
    ("GRID INTERFACE CONTROLLER",     "ONLINE    [OK]"),
    ("LIGHT CYCLE ENGINE v7.1",       "LOADED    [OK]"),
    ("MONTY PYTHON2.7",               "!DEAD     [YET]"),
    ("NEON CORTEX NEURAL ENGINE",     "NOMINAL   [OK]"),
    ("PRAYING TO ODIN",               "DONE"),
    ("MCP UPLINK STATUS",             "CONNECTED"),
    ("UNAUTHORIZED PROGRAM SCAN",     "[1] FOUND"),
    ("SANDBOXING DPRK BOTNET",        "DONE"),
    ("LASER NET ALIGNMENT",           "[PEW][PEW]"),
    ("WEAPONS GRADE VR",              "LUCKY"),
    ("USER IDENTITY VERIFICATION",    "MOGGING"),
    ("HYPERSPACE COORDINATE LOCK",    "LOST"),
    ("SYNTHWAVE AUDIO DRIVER v8.4",   "LOADED    [OK]"),
    ("JOYSTICK ARRAY CALIBRATION x4", "[OK]"),
    ("VAPORWAVE RENDERING PIPELINE",  "READY     [OK]"),
    ("FROG BLASTING THE VENT CORE",   "777"),
    ("TEMPORAL ALIGNMENT: 1993",      "LOCKED"),
]

# ── GLSL ──────────────────────────────────────────────────────────────────────

_VERT = """\
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

# pygame surface: row 0 = top.  tobytes() outputs top row first.
# OpenGL texture: row 0 = bottom.  So the image arrives "upside down" from GL's
# perspective.  The Y flip (1.0 - v_uv.y) corrects this — no CPU flip needed.
_FRAG = """\
#version 330
uniform sampler2D u_scene;
uniform sampler2D u_glow;
uniform float u_glow_strength;
uniform float u_flicker;
uniform float u_time;
in vec2 v_uv;
out vec4 out_color;

const float BARREL_K    = 0.15;
const float SCANLINE_A  = 0.2745;   // 70/255
const float VIG_MAX     = 0.6667;   // 170/255
const float VIG_START   = 0.30;
const float VIG_RANGE   = 0.70;

// Rolling bar sync artifact — one sweep every ~9 seconds
const float BAR_SPEED  = 0.11;    // screen-heights per second
const float BAR_WIDTH  = 0.022;   // narrow band — sharp transient
const float BAR_WARP   = 0.0022;  // max horizontal offset (~4 px at 1920)
const float BAR_FREQ   = 16.0;    // tight zigzag cycles within the band

void main() {
    // Correct for OpenGL vs. pygame Y-axis convention
    vec2 uv = vec2(v_uv.x, 1.0 - v_uv.y);

    // Vignette in linear screen space — unaffected by barrel or bar warp
    vec2 cc  = uv - 0.5;
    float d  = length(cc) * 1.4142;           // 1.4142 ≈ 1/length(0.5,0.5)
    float vt = clamp((d - VIG_START) / VIG_RANGE, 0.0, 1.0);
    float vig = 1.0 - vt * vt * (3.0 - 2.0 * vt) * VIG_MAX;

    // Barrel distortion — defines the fixed screen edge shape
    vec2 buv = uv + cc * dot(cc, cc) * BARREL_K;
    if (buv.x < 0.0 || buv.x > 1.0 || buv.y < 0.0 || buv.y > 1.0) {
        out_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // Rolling bar warp applied after barrel so it displaces image content
    // but never touches the screen border shape.
    float bar_y    = fract(u_time * BAR_SPEED);
    float bar_dist = abs(buv.y - bar_y);
    bar_dist       = min(bar_dist, 1.0 - bar_dist);  // wrap at top/bottom
    float influence = smoothstep(BAR_WIDTH, 0.0, bar_dist);

    // Beat-frequency envelope: product of two incommensurate sines, positive
    // half only — makes the glitch rise and fall rather than carry constantly.
    float env = sin(u_time * 1.31) * sin(u_time * 0.43);
    influence *= clamp(env, 0.0, 1.0);

    // Sawtooth wave across Y — displacement flips sign each cycle
    float saw = fract(buv.y * BAR_FREQ) * 2.0 - 1.0;
    buv.x = clamp(buv.x + saw * BAR_WARP * influence, 0.0, 1.0);

    vec3 col = texture(u_scene, buv).rgb
             + texture(u_glow,  buv).rgb * u_glow_strength;
    col = clamp(col, 0.0, 1.0);

    // Horizontal scanlines on every other pixel row
    float scan = mod(floor(gl_FragCoord.y), 2.0) < 1.0
                 ? (1.0 - SCANLINE_A) : 1.0;

    out_color = vec4(col * (scan * vig * u_flicker), 1.0);
}
"""

# ── Global state ───────────────────────────────────────────────────────────────

_ctx:         moderngl.Context   | None = None
_prog:        moderngl.Program   | None = None
_vao:         moderngl.VertexArray | None = None
_scene_tex:   moderngl.Texture   | None = None
_glow_tex:    moderngl.Texture   | None = None
_font:        pygame.font.Font   | None = None
_char_w:      int = 0
_char_h:      int = 0
_term_rows:   int = 0
_term_cols:   int = 0
_starfield:   pygame.Surface     | None = None
_glyph_cache: dict = {}
# idx → (scene_surf, glow_bytes) — scene_surf for display, glow_bytes pre-computed
_scene_cache:      dict[int, tuple[pygame.Surface, bytes]] = {}
_BLACK_GLOW:       bytes = bytes(GLOW_W * GLOW_H * 3)  # used during boot/launching
_start_time:       float = 0.0
_screensaver_on:   bool  = False  # suppresses flicker_tick redraws on blank screen
_boot_sounds:      dict  = {}     # synthesized sounds for the boot sequence


# ── Boot sounds ───────────────────────────────────────────────────────────────

def _build_boot_sounds() -> dict:
    """Synthesize all boot sounds using numpy. Returns {} if mixer unavailable."""
    if not pygame.mixer.get_init():
        return {}

    SR = 44100

    def _snd(arr: np.ndarray, vol: float):
        arr = np.clip(arr, -1.0, 1.0)
        s16 = (arr * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(s16.tobytes())
        buf.seek(0)
        snd = pygame.mixer.Sound(buf)
        snd.set_volume(BOOT_VOLUME * vol)
        return snd

    def _t(dur):
        return np.linspace(0, dur, int(SR * dur))

    # CRT power-on: FM synthesis for the organic hollow "dwing/thunk" —
    # carrier sweeps down (mouth closing), modulator adds wet formant texture
    t      = _t(0.55)
    car_f  = 180 * np.exp(-t * 9) + 40                  # 220 Hz → 40 Hz
    car_ph = 2 * np.pi * np.cumsum(car_f) / SR
    mod_f  = 220 * np.exp(-t * 11) + 30
    mod_ph = 2 * np.pi * np.cumsum(mod_f) / SR
    tone   = np.sin(car_ph + np.sin(mod_ph) * 2.5) * np.exp(-t * 9) * 0.85
    click_n = int(SR * 0.003)
    click   = np.zeros(len(t))
    click[:click_n] = np.exp(-np.arange(click_n) * 800 / SR) * np.random.choice([-1.0, 1.0], click_n)
    crt    = np.clip(click * 0.35 + tone, -1.0, 1.0)

    # Static: 2 s white noise base + sparse crackle peaks for texture,
    # triggered at the scan line so it covers the whole CRT warmup
    t = _t(2.0)
    base    = np.random.uniform(-1, 1, len(t)) * np.exp(-t * 2.5)
    crackle = np.zeros(len(t))
    s_len   = int(SR * 0.003)
    for idx in np.random.randint(0, len(t) - s_len, 70):
        bt = np.arange(s_len) / SR
        crackle[idx:idx + s_len] += np.random.choice([-1.0, 1.0]) * np.exp(-bt * 500)
    crackle *= np.exp(-t * 3.5)
    static   = np.clip(base * 0.65 + crackle * 0.60, -1.0, 1.0)

    # CRT whine: 15.7 kHz tone — fades in at startup, sustains through boot,
    # then drifts out over ~2.5 s after the menu appears
    t     = _t(12.5)
    w_in  = np.minimum(t / 0.15, 1.0)
    w_out = np.clip(1.0 - (t - 9.65) / 2.5, 0.0, 1.0)
    w_env = w_in * np.where(t < 9.65, 1.0, w_out)
    whine = np.sin(2 * np.pi * 15734 * t) * w_env * 0.70

    # Key tick: short click (noise) + 80 Hz thump for depth
    t = _t(0.04)
    tick = (np.random.uniform(-1, 1, len(t)) * np.exp(-t * 150) * 0.45 +
            np.sin(2 * np.pi * 80 * t)       * np.exp(-t *  80) * 0.65)

    # Halo "Du Du Du Dah" — G3/C4 (one octave lower), bass-weighted harmonics,
    # long fade on the final note
    def _note(freq, dur, decay_rate=1.8, attack=0.06):
        t2   = _t(dur)
        saw  = sum(np.sin(2 * np.pi * freq * n * t2) / n for n in range(3, 10)) * 0.12
        tone = (np.sin(2 * np.pi * freq     * t2) * 0.72 +
                np.sin(2 * np.pi * freq * 2 * t2) * 0.20 +
                saw)
        env  = np.exp(-t2 * decay_rate)
        ramp = np.minimum(t2 / attack, 1.0)
        return tone * env * ramp

    NOTE_DUR = 0.13
    NOTE_GAP = 0.045
    DAH_DUR  = 1.47   # ~2/3 of previous fade
    E2, E3   = 82.41, 164.81   # exact notes from MIDI at 36s
    total    = int(SR * (3 * (NOTE_DUR + NOTE_GAP) + DAH_DUR))
    halo     = np.zeros(total)
    for i in range(3):
        off = int(SR * i * (NOTE_DUR + NOTE_GAP))
        seg = _note(E2, NOTE_DUR)
        halo[off:off + len(seg)] += seg
    dah_off = int(SR * 3 * (NOTE_DUR + NOTE_GAP))
    seg = _note(E3, DAH_DUR, decay_rate=0.55, attack=0.08)   # very slow decay
    halo[dah_off:dah_off + len(seg)] += seg

    return {
        'crt':    _snd(crt,    1.0),
        'static': _snd(static, 0.72),
        'whine':  _snd(whine,  0.70),
        'tick':   _snd(tick,   0.75),
        'halo':   _snd(halo,   1.0),
    }


# ── Init ───────────────────────────────────────────────────────────────────────

def _init_pygame() -> None:
    global _ctx, _prog, _vao, _scene_tex, _glow_tex
    global _font, _char_w, _char_h, _term_rows, _term_cols
    global _starfield, _glyph_cache, _scene_cache, _start_time, _screensaver_on
    global _boot_sounds

    os.environ.setdefault('SDL_VIDEODRIVER', 'kmsdrm')
    os.environ.setdefault('MESA_GL_VERSION_OVERRIDE',   '3.3')
    os.environ.setdefault('MESA_GLSL_VERSION_OVERRIDE', '330')

    pygame.mixer.pre_init(44100, -16, 2, 4096)
    pygame.init()
    pygame.mouse.set_visible(False)

    try:
        pygame.display.set_mode(
            (SCREEN_W, SCREEN_H),
            pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN | pygame.NOFRAME)
    except Exception:
        pygame.display.set_mode(
            (SCREEN_W, SCREEN_H),
            pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.display.set_caption('Bearnos Arcade')

    _ctx  = moderngl.create_context()
    _ctx.viewport = (0, 0, SCREEN_W, SCREEN_H)
    _prog = _ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)

    vbo  = _ctx.buffer(np.array([
        -1.0, -1.0,   1.0, -1.0,  -1.0,  1.0,
         1.0, -1.0,   1.0,  1.0,  -1.0,  1.0,
    ], dtype=np.float32).tobytes())
    _vao = _ctx.vertex_array(_prog, [(vbo, '2f', 'in_vert')])

    _scene_tex = _ctx.texture((SCREEN_W, SCREEN_H), 3)
    _scene_tex.filter   = (moderngl.LINEAR, moderngl.LINEAR)
    _scene_tex.repeat_x = False
    _scene_tex.repeat_y = False
    _glow_tex  = _ctx.texture((GLOW_W, GLOW_H), 3)
    _glow_tex.filter    = (moderngl.LINEAR, moderngl.LINEAR)
    _glow_tex.repeat_x  = False
    _glow_tex.repeat_y  = False

    _scene_tex.use(location=0)
    _glow_tex.use(location=1)
    _prog['u_scene']        = 0
    _prog['u_glow']         = 1
    _prog['u_glow_strength'] = GLOW_STRENGTH

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

    sample    = _font.render('M', True, (255, 255, 255))
    _char_w   = sample.get_width()
    _char_h   = sample.get_height()
    _term_cols = SCREEN_W // _char_w
    _term_rows = SCREEN_H // _char_h
    _glyph_cache   = {}
    _scene_cache   = {}
    _start_time    = time.monotonic()
    _screensaver_on = False

    _starfield = _build_starfield()

    try:
        _boot_sounds = _build_boot_sounds()
    except Exception as e:
        print(f'[renderer_gl] boot sounds unavailable: {e}', file=sys.stderr)
        _boot_sounds = {}

    print(f'[renderer_gl] font: {_char_w}×{_char_h}px  '
          f'grid: {_term_cols}×{_term_rows}', file=sys.stderr)


def _rebuild_gl() -> None:
    """Recreate the GL context and GPU objects after a game returns.

    Called by term_enter_alt_screen() on every invocation after the first.
    pygame.display was quit before the game launched to release DRM master;
    we reinit just the display subsystem here, leaving font/glyph/scene
    caches untouched so the menu reappears instantly.

    glcontext auto-detection falls through to X11/GLX when DISPLAY is set
    (e.g. from an SSH session), so we clear it temporarily to force EGL.
    """
    global _ctx, _prog, _vao, _scene_tex, _glow_tex, _start_time, _screensaver_on

    pygame.display.init()
    try:
        pygame.display.set_mode(
            (SCREEN_W, SCREEN_H),
            pygame.OPENGL | pygame.DOUBLEBUF | pygame.FULLSCREEN | pygame.NOFRAME)
    except Exception:
        pygame.display.set_mode(
            (SCREEN_W, SCREEN_H),
            pygame.OPENGL | pygame.DOUBLEBUF)

    # Clear the cached context so create_context() re-enters the init_context()
    # path (DefaultLoader / EGL) instead of falling through to the glcontext
    # x11 backend which calls glXGetCurrentContext() → NULL on kmsdrm.
    moderngl._store.default_context = None
    _ctx = moderngl.create_context()

    _ctx.viewport = (0, 0, SCREEN_W, SCREEN_H)
    _prog = _ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)

    vbo  = _ctx.buffer(np.array([
        -1.0, -1.0,   1.0, -1.0,  -1.0,  1.0,
         1.0, -1.0,   1.0,  1.0,  -1.0,  1.0,
    ], dtype=np.float32).tobytes())
    _vao = _ctx.vertex_array(_prog, [(vbo, '2f', 'in_vert')])

    _scene_tex = _ctx.texture((SCREEN_W, SCREEN_H), 3)
    _scene_tex.filter   = (moderngl.LINEAR, moderngl.LINEAR)
    _scene_tex.repeat_x = False
    _scene_tex.repeat_y = False
    _glow_tex  = _ctx.texture((GLOW_W, GLOW_H), 3)
    _glow_tex.filter    = (moderngl.LINEAR, moderngl.LINEAR)
    _glow_tex.repeat_x  = False
    _glow_tex.repeat_y  = False

    _scene_tex.use(location=0)
    _glow_tex.use(location=1)
    _prog['u_scene']         = 0
    _prog['u_glow']          = 1
    _prog['u_glow_strength'] = GLOW_STRENGTH

    _screensaver_on = False
    _start_time     = time.monotonic()


# ── Glyph / drawing helpers ────────────────────────────────────────────────────

def _glyph(text: str, color: tuple) -> pygame.Surface:
    key = (text, color)
    if key not in _glyph_cache:
        _glyph_cache[key] = _font.render(text, True, color)
    return _glyph_cache[key]


def _draw(surf: pygame.Surface, text: str, row: int, col: int,
          color: tuple) -> None:
    if not text:
        return
    surf.blit(_glyph(text, color), ((col - 1) * _char_w, (row - 1) * _char_h))


def _draw_centered(surf: pygame.Surface, text: str, row: int,
                   color: tuple) -> None:
    g = _glyph(text, color)
    surf.blit(g, ((SCREEN_W - g.get_width()) // 2, (row - 1) * _char_h))


def _build_starfield() -> pygame.Surface:
    import random
    surf = pygame.Surface((SCREEN_W, SCREEN_H))
    surf.fill(COL_BG)
    rng   = random.Random()
    chars = ['·', '·', '·', '·', '.', '.', '.', '*', '*', '+']
    for r in range(7, _term_rows + 1):
        for c in range(1, _term_cols + 1):
            if rng.random() < 0.05:
                surf.blit(_glyph(rng.choice(chars), COL_DIM),
                          ((c - 1) * _char_w, (r - 1) * _char_h))
    return surf


# ── Glow (CPU, once per scene change) ─────────────────────────────────────────

def _box_blur(arr: np.ndarray, radius: int) -> np.ndarray:
    out = arr.astype(np.float32)
    for axis in (0, 1):
        n   = out.shape[axis]
        pad = [1 if a == axis else s for a, s in enumerate(out.shape)]
        cs  = np.concatenate(
            [np.zeros(pad, dtype=np.float32), np.cumsum(out, axis=axis)],
            axis=axis)
        i    = np.arange(n)
        lo   = np.maximum(0, i - radius)
        hi   = np.minimum(n, i + radius + 1)
        cnt  = (hi - lo).astype(np.float32)
        sums = np.take(cs, hi, axis=axis) - np.take(cs, lo, axis=axis)
        bc   = [1] * out.ndim
        bc[axis] = n
        out  = sums / cnt.reshape(bc)
    return out


def _build_glow_bytes(surf: pygame.Surface) -> bytes:
    """Return pre-blurred glow as raw RGB bytes for the (GLOW_W × GLOW_H) texture.

    surfarray gives (W, H, 3).  We downsample 4×, blur, then transpose to
    (H, W, 3) row-major for OpenGL upload.  Y-orientation matches the scene
    texture (pygame top-row first, corrected by the shader's UV flip).
    """
    arr   = pygame.surfarray.array3d(surf).astype(np.float32) / 255.0  # (W,H,3)
    small = arr[::4, ::4]                                               # (GW,GH,3)
    lum   = (0.299 * small[:, :, 0]
           + 0.587 * small[:, :, 1]
           + 0.114 * small[:, :, 2])
    mask   = np.clip((lum - GLOW_THRESHOLD) * 3.0, 0.0, 1.0)[:, :, np.newaxis]
    bright = small * mask
    glow   = _box_blur(_box_blur(bright, 8), 5)                        # (GW,GH,3)
    glow   = np.clip(glow, 0.0, 1.0).transpose(1, 0, 2)               # (GH,GW,3)
    return (glow * 255).astype(np.uint8).tobytes()


# ── GL upload / render ─────────────────────────────────────────────────────────

def _upload_scene(surf: pygame.Surface) -> None:
    """Upload a pygame surface to the scene texture (no copy, no flip)."""
    _scene_tex.write(pygame.image.tobytes(surf, 'RGB'))


def _draw_frame(flicker: float = 1.0) -> None:
    _ctx.clear(0.0, 0.0, 0.0)
    _prog['u_flicker'] = flicker
    _prog['u_time']    = time.monotonic() - _start_time
    _scene_tex.use(location=0)
    _glow_tex.use(location=1)
    _vao.render(moderngl.TRIANGLES)
    pygame.display.flip()


# ── Scene composition (same logic as renderer_pygame.py) ──────────────────────

def _compose_menu(app, idx: int | None = None) -> pygame.Surface:
    if idx is None:
        idx = app.selected
    rows, cols = app.term_rows, app.term_cols
    scene = _starfield.copy()

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
    if count > 0 and getattr(games[idx], 'generated', False):
        hint = '◄ LEFT/RIGHT TO BROWSE ►    [ ATTACK ] TO PLAY    [ JUMP ] TO EDIT'
    else:
        hint = '◄ LEFT/RIGHT TO BROWSE ►    [ ATTACK ] TO PLAY'
    _draw_centered(scene, hint, rows, COL_SEPIA)
    return scene


_COMING_SOON_BANNER = [
    "▄▖        ▘      ▄▖      ",
    "▌ ▛▌▛▛▌▛▛▌▌▛▌▛▌  ▚ ▛▌▛▌▛▌",
    "▙▖▙▌▌▌▌▌▌▌▌▌▌▙▌  ▄▌▙▌▙▌▌▌",
    "             ▄▌          ",
]


def _render_textcard_full(surf: pygame.Surface, game, rows: int) -> None:
    lines = [l.rstrip() for l in game.textcard.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return

    content_w  = max(len(l) for l in lines)
    block_px_w = content_w * _char_w
    start_x    = (SCREEN_W - block_px_w) // 2

    content_start = 7
    content_end   = rows - 2
    available_h   = max(1, content_end - content_start + 1)
    gap           = max(0, available_h - len(lines))
    start_row     = content_start + int(gap * 0.30)

    for i, line in enumerate(lines):
        r = start_row + i
        if r > content_end:
            break
        if line:
            tc_col = COL_PHOSPHOR if getattr(game, "is_creator", False) else COL_CREAM
            surf.blit(_glyph(line, tc_col), (start_x, (r - 1) * _char_h))

    if getattr(game, "game_dev_status", None) == "coming_soon":
        banner_w  = max(len(l) for l in _COMING_SOON_BANNER)
        banner_x  = (SCREEN_W - banner_w * _char_w) // 2
        banner_start_row = content_end - len(_COMING_SOON_BANNER) + 1
        for i, line in enumerate(_COMING_SOON_BANNER):
            if line.strip():
                surf.blit(_glyph(line, COL_ACCENT),
                          (banner_x, (banner_start_row + i - 1) * _char_h))


def _render_block_title(surf: pygame.Surface, title: str,
                        box_col: int, box_row: int,
                        box_w: int, box_h: int) -> None:
    chars = [c for c in title.upper() if c in BLOCK_FONT]
    if not chars:
        return

    scale = 1
    while True:
        if len(chars) * 5 * (scale + 1) + (len(chars) - 1) * (scale + 1) > int(box_w * 0.90):
            break
        scale += 1
    scale = max(1, scale)

    glyph_w = 5 * scale
    gap_w   = scale
    total_w = len(chars) * glyph_w + (len(chars) - 1) * gap_w
    glyph_h = 5 * scale
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


# ── Scene cache ────────────────────────────────────────────────────────────────

def _build_scene(app, idx: int) -> tuple[pygame.Surface, bytes]:
    surf = _compose_menu(app, idx)
    return surf, _build_glow_bytes(surf)


def clear_scene_cache() -> None:
    _scene_cache.clear()


def warm_next_scene_cache(app) -> bool:
    if _ctx is None:
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


# ── Public API ─────────────────────────────────────────────────────────────────

def get_terminal_size() -> tuple[int, int]:
    return (_term_rows, _term_cols) if _term_rows else (30, 80)


def term_enter_alt_screen() -> None:
    if _ctx is None:
        _init_pygame()
    else:
        _rebuild_gl()


def term_leave_alt_screen() -> None:
    # Only quit the display subsystem so the game child can claim DRM master.
    # Font, glyph cache, and scene cache survive in CPU memory.
    pygame.display.quit()


def flicker_tick() -> None:
    if _ctx is None or _screensaver_on:
        return
    pygame.event.pump()
    flicker = 1.0
    if random.random() < FLICKER_CHANCE:
        flicker = 1.0 - random.randint(2, FLICKER_DEPTH) / 255.0
    _draw_frame(flicker)


def render(app) -> None:
    global _screensaver_on
    if _ctx is None:
        return
    _screensaver_on = False
    idx = app.selected
    if idx not in _scene_cache:
        _scene_cache[idx] = _build_scene(app, idx)
    surf, glow = _scene_cache[idx]
    _upload_scene(surf)
    _glow_tex.write(glow)
    _draw_frame(1.0)


def render_screensaver() -> None:
    global _screensaver_on
    if _ctx is None:
        return
    _screensaver_on = True
    _ctx.clear(0.0, 0.0, 0.0)
    pygame.display.flip()


def render_launching(app) -> None:
    if _ctx is None:
        return
    games = app.game_list()
    title = games[app.selected].title if games else '?'
    mid   = app.term_rows // 2
    scene = pygame.Surface((SCREEN_W, SCREEN_H))
    scene.fill(COL_BG)
    _draw_centered(scene, f'LAUNCHING  {title} ...', mid, COL_CREAM)
    _upload_scene(scene)
    _glow_tex.write(_BLACK_GLOW)
    _draw_frame(1.0)


def render_boot(app, monitor_was_off: bool = False) -> None:
    """Boot animation.

    All CRT effects (barrel, scanlines, vignette) are in the shader and run
    every frame for free.  The animation draws frames to a pygame surface and
    uploads them — the expensive numpy operations in the original (barrel
    remap, per-frame glow) are completely eliminated.
    """
    if _ctx is None:
        return

    final_surf = _compose_menu(app)
    final_glow = _build_glow_bytes(final_surf)

    MONITOR_DELAY = 5.0 if monitor_was_off else 0.0
    CRT_DUR  = 2.0
    CRT_END  = MONITOR_DELAY + CRT_DUR
    t_text   = CRT_END
    t_online = t_text + len(BOOT_MESSAGES) * BOOT_LINE_T
    t_fade   = t_online + 0.70
    t_end    = t_fade   + 0.80

    block_chars = BOOT_COL_W + 22
    left_x   = (SCREEN_W - block_chars * _char_w) // 2
    right_x  = left_x + (BOOT_COL_W + 2) * _char_w
    header_y = 3 * _char_h
    sep_y    = header_y + _char_h
    text_y0  = sep_y + _char_h
    SEP      = "═" * block_chars
    HEADER   = "KIELER HEAVY INDUSTRIES - BEARNOS GAMES   ■   BIOS v2.3   ■   (C) 1993"

    cy    = SCREEN_H // 2
    start = pygame.time.get_ticks() / 1000.0

    _glow_tex.write(_BLACK_GLOW)

    _snd_fired:  set = set()   # tracks which one-shot sounds have played
    _ticks_fired: set = set()  # tracks which BIOS-line ticks have played

    def _play(name: str) -> None:
        if name not in _snd_fired and name in _boot_sounds:
            _boot_sounds[name].play()
            _snd_fired.add(name)

    while True:
        t = pygame.time.get_ticks() / 1000.0 - start
        if t >= t_end:
            break

        pygame.event.pump()
        frame = pygame.Surface((SCREEN_W, SCREEN_H))
        frame.fill(COL_BG)

        if t < MONITOR_DELAY:
            pass

        elif t < CRT_END:
            _play('crt')
            _play('static')
            _play('whine')
            tc = t - MONITOR_DELAY
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
                # Static noise — generate at quarter-res and scale up for speed
                p         = (tc - 1.55) / 0.45
                alpha_val = int(255 * (1.0 - p))
                noise = np.random.randint(20, 190,
                                          (SCREEN_W // 4, SCREEN_H // 4, 3),
                                          dtype=np.uint8)
                noise[:, :, 2] = (noise[:, :, 2].astype(np.uint16) * 55 // 100
                                  ).astype(np.uint8)
                ns = pygame.transform.scale(
                    pygame.surfarray.make_surface(noise),
                    (SCREEN_W, SCREEN_H))
                ns.set_alpha(alpha_val)
                frame.blit(ns, (0, 0))

        elif t < t_online:
            t_rel      = t - t_text
            lines_done = int(t_rel / BOOT_LINE_T)
            line_frac  = (t_rel % BOOT_LINE_T) / BOOT_LINE_T

            frame.blit(_glyph(HEADER, COL_ACCENT),         (left_x, header_y))
            frame.blit(_glyph(SEP[:block_chars], COL_DIM), (left_x, sep_y))

            for i in range(min(lines_done, len(BOOT_MESSAGES))):
                left, status = BOOT_MESSAGES[i]
                y = text_y0 + i * _char_h
                frame.blit(_glyph(left.ljust(BOOT_COL_W, '.'), COL_DIM),
                           (left_x, y))
                frame.blit(_glyph(status, COL_SEPIA), (right_x, y))

            if lines_done < len(BOOT_MESSAGES):
                left, status = BOOT_MESSAGES[lines_done]
                dots = left.ljust(BOOT_COL_W, '.')
                y    = text_y0 + lines_done * _char_h
                if line_frac < 0.50:
                    frame.blit(_glyph(dots, COL_SEPIA), (left_x, y))
                else:
                    if lines_done not in _ticks_fired:
                        if 'tick' in _boot_sounds:
                            _boot_sounds['tick'].play()
                        _ticks_fired.add(lines_done)
                    frame.blit(_glyph(dots, COL_DIM),     (left_x, y))
                    frame.blit(_glyph(status, COL_CREAM), (right_x, y))

        elif t < t_fade:
            _play('halo')
            frame.blit(_glyph(HEADER, COL_ACCENT),         (left_x, header_y))
            frame.blit(_glyph(SEP[:block_chars], COL_DIM), (left_x, sep_y))
            for i, (left, status) in enumerate(BOOT_MESSAGES):
                y = text_y0 + i * _char_h
                frame.blit(_glyph(left.ljust(BOOT_COL_W, '.'), COL_DIM),
                           (left_x, y))
                frame.blit(_glyph(status, COL_SEPIA), (right_x, y))

            bot_sep_y = text_y0 + len(BOOT_MESSAGES) * _char_h
            online_y  = bot_sep_y + _char_h
            ready_y   = online_y  + _char_h
            frame.blit(_glyph(SEP[:block_chars], COL_DIM), (left_x, bot_sep_y))
            p = (t - t_online) / 0.70
            frame.blit(
                _glyph("  BEARNOS GAME STATION  ■  ONLINE",
                       COL_CREAM if p > 0.25 else COL_DIM),
                (left_x, online_y))
            if p > 0.55:
                cursor = "█" if int((t - t_online) * 3) % 2 == 0 else " "
                frame.blit(_glyph(f"  > READY PLAYER ONE {cursor}", COL_ACCENT),
                           (left_x, ready_y))

        else:
            # Fade in from white: blend final menu with a white overlay
            p  = (t - t_fade) / 0.80
            sp = p * p * (3.0 - 2.0 * p)
            frame.blit(final_surf, (0, 0))
            overlay = pygame.Surface((SCREEN_W, SCREEN_H))
            overlay.fill((255, 255, 255))
            overlay.set_alpha(int((1.0 - sp) * 224))
            frame.blit(overlay, (0, 0))
            if sp > 0.5:
                _glow_tex.write(final_glow)

        _upload_scene(frame)
        _draw_frame(1.0)
        pygame.time.delay(16)

    # Leave display showing the final menu frame with full glow
    _glow_tex.write(final_glow)
    _upload_scene(final_surf)
    _draw_frame(1.0)
