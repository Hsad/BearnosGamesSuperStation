package breach

// BREACH — 1v1 tank duel where each player operates two cabinet stations.
//
// Each player sits between two adjacent stations. The two joysticks are skid-
// steer: stick-Y on each drives that tread, stick-X aims the cannon (left-X =
// pitch, right-X = yaw). The four buttons in front of the pair are an explicit
// reload sequence: shell, powder, breach toggle, fire.
//
// First-person view from the commander's cupola of each tank. Both views
// rendered to off-screen textures and composited side-by-side at 960×1080.

import rl "vendor:raylib"
import "core:math"
import "core:math/rand"
import "core:fmt"
import "core:os"
import "core:c"

// ── Window / split ──────────────────────────────────────────────────────────
W :: 1920
H :: 1080
VW :: 1920   // per-player viewport width (full width — horizontal split)
VH :: 540    // per-player viewport height (half — top/bottom)

// ── World ───────────────────────────────────────────────────────────────────
TERRAIN_SIZE   : f32 : 220.0     // world units across (X & Z)
TERRAIN_HEIGHT : f32 :  10.0     // max amplitude
TGRID          :: 56              // grid resolution (TGRID+1 vertices per side)
HALF_T         : f32 : TERRAIN_SIZE * 0.5

GRAVITY        : f32 : -22.0
SHELL_BASE_V   : f32 :  45.0     // 1 powder charge
SHELL_CHARGE_V : f32 :  17.0     // additional v per extra charge
SHELL_DRAG     : f32 :   0.10
SHELL_R        : f32 :   0.30
SHELL_LIFE     : f32 :  10.0
MAX_CHARGES    :: 3

// ── Tank dimensions (meters) ────────────────────────────────────────────────
HULL_W      : f32 : 3.2
HULL_L      : f32 : 5.2
HULL_H      : f32 : 1.4
TREAD_W     : f32 : 0.7
TURRET_R    : f32 : 1.5
TURRET_H    : f32 : 1.1
BARREL_L    : f32 : 4.6
BARREL_R    : f32 : 0.20
CUPOLA_R    : f32 : 0.55
CUPOLA_H    : f32 : 0.45

// motion
TREAD_MAX_V   : f32 : 12.0
TREAD_ACC     : f32 : 18.0
// Treads coast when the stick is released — momentum carries the tank
// forward. When the stick is held, we drive toward the target velocity;
// when released, we apply LINEAR friction (constant deceleration). Linear
// friction halts low speeds quickly without slowing high speeds too much,
// giving a heavy / mechanical feel — unlike exponential damping which
// proportionally tapers and feels "drifty" at low speeds. A snap-to-zero
// threshold kills the last sliver so the tank actually stops.
TREAD_FRICTION: f32 :  8.5
TREAD_STOP_V  : f32 :  0.30
// Skid-steer yaw rate scale. Without scaling, max tread differential would
// pirouette the tank faster than it advances; scaling lets "aim while
// moving" be playable.
YAW_RATE_SCALE: f32 :  0.40
TURRET_YAW_V  : f32 :  1.6   // rad/s
BARREL_PITCH_V: f32 :  0.9
BARREL_PITCH_MIN : f32 : -0.10
BARREL_PITCH_MAX : f32 :  0.55

STICK_DEAD : f32 : 0.05

// ── Damage ──────────────────────────────────────────────────────────────────
HP_MAX        : f32 : 5.0
DMG_FRONT     : f32 : 1.0
DMG_SIDE      : f32 : 5.0 / 3.0
DMG_REAR      : f32 : 5.0

ROUND_WIN     :: 3       // best of 5 (first to 3)
RESPAWN_T     : f32 : 3.0
INVULN_T      : f32 : 1.5

QUIT_HOLD     : f32 : 1.2

// ── Reload state machine ────────────────────────────────────────────────────
ReloadState :: enum {
    Breach_Open_Empty,    // breach open, nothing loaded
    Breach_Open_Shell,    // shell inserted, no powder
    Breach_Open_Powdered, // shell + 1..MAX_CHARGES powder
    Breach_Closed_Loaded, // closed and ready to fire
    Breach_Closed_Spent,  // breach closed, already fired — must reopen
}

// ── Colors ──────────────────────────────────────────────────────────────────
COL_SKY_TOP    := rl.Color{ 95, 130, 175, 255}
COL_SKY_HORZ   := rl.Color{210, 175, 140, 255}
COL_FOG        := rl.Color{180, 175, 160, 255}
COL_DIRT       := rl.Color{ 95,  80,  55, 255}
COL_GRASS      := rl.Color{ 95, 120,  60, 255}
COL_GRASS_DK   := rl.Color{ 60,  85,  45, 255}
COL_ROCK       := rl.Color{120, 115, 105, 255}
COL_ROCK_DK    := rl.Color{ 80,  78,  72, 255}
COL_RUIN       := rl.Color{160, 150, 130, 255}
COL_WHITE      := rl.Color{245, 245, 245, 255}
COL_DIM        := rl.Color{170, 170, 170, 255}
COL_HUDBG      := rl.Color{  8,  10,  16, 220}
COL_PANEL      := rl.Color{ 30,  34,  46, 230}
COL_RED        := rl.Color{220,  80,  60, 255}
COL_AMBER      := rl.Color{240, 180,  50, 255}
COL_GREEN      := rl.Color{120, 210, 110, 255}

P_COLORS := [2]rl.Color{
    rl.Color{180, 140,  90, 255},   // P1 desert tan
    rl.Color{ 90, 105,  80, 255},   // P2 forest olive
}
P_TINT := [2]rl.Color{
    rl.Color{120, 200, 255, 255},
    rl.Color{255, 140, 120, 255},
}

// ── Input mappings ──────────────────────────────────────────────────────────
KEYS_LEFT  := [?]rl.KeyboardKey{.LEFT, .D, .J, .V}
KEYS_RIGHT := [?]rl.KeyboardKey{.RIGHT, .G, .L, .U}
KEYS_UP    := [?]rl.KeyboardKey{.UP, .R, .I, .Y}
KEYS_DOWN  := [?]rl.KeyboardKey{.DOWN, .F, .K, .N}
KEYS_JUMP  := [?]rl.KeyboardKey{.LEFT_CONTROL, .A, .RIGHT_CONTROL, .B}
KEYS_ATK   := [?]rl.KeyboardKey{.LEFT_ALT,     .S, .RIGHT_SHIFT,    .E}

// Tank N is controlled by stations (N*2, N*2+1).
//   tank 0 → station 0 (left stick + buttons) and station 1 (right)
//   tank 1 → station 2 (left) and station 3 (right)

// ── Types ───────────────────────────────────────────────────────────────────
Vec2 :: rl.Vector2
Vec3 :: rl.Vector3

Tank :: struct {
    pos:           Vec3,
    hull_yaw:      f32,    // radians, 0 = +Z
    hull_pitch:    f32,    // derived from terrain slope (for visual roll/pitch)
    hull_roll:     f32,
    turret_yaw:    f32,    // relative to hull
    barrel_pitch:  f32,    // elevation

    // tread velocities (m/s along facing)
    left_v:        f32,
    right_v:       f32,

    // reload state
    reload:        ReloadState,
    powder:        i32,
    breach_anim:   f32,    // 0 closed, 1 open

    // damage
    front_hits:    f32,
    side_hits:     f32,
    rear_hits:     f32,
    hp:            f32,    // = HP_MAX - sum  (computed every frame)
    alive:         bool,
    respawn_t:     f32,
    invuln_t:      f32,
    hit_flash:     f32,
    last_hit_dir:  f32,    // for hit indicator (radians, 0=front, +π/2 right)

    // round score
    rounds_won:    i32,

    // visuals
    smoke_t:       f32,
    muzzle_flash:  f32,
    recoil:        f32,    // visual barrel recoil 0..1
    quit_hold:     f32,
}

Shell :: struct {
    alive:  bool,
    owner:  i32,
    pos:    Vec3,
    vel:    Vec3,
    life:   f32,
    trail:  [16]Vec3,
    trail_n: i32,
    trail_fill: i32,
}

Obstacle :: struct {
    pos:   Vec3,
    size:  Vec3,
    yaw:   f32,
    color: rl.Color,
    kind:  i32, // 0 = rock (sphere-ish), 1 = ruin wall (box), 2 = log (cyl)
}

Mode :: enum {
    Title,
    Playing,
    Round_Over,
    Match_Over,
}

State :: struct {
    mode:        Mode,
    tanks:       [2]Tank,
    shells:      [16]Shell,
    obstacles:   [24]Obstacle,
    obs_count:   int,

    round_t:     f32,    // round time elapsed
    round_start_t: f32,  // pre-round countdown
    intermission: f32,
    cur_round:   i32,

    cam:         [2]rl.Camera3D,
    rt:          [2]rl.RenderTexture2D,

    terrain_mesh: rl.Mesh,
    terrain_model: rl.Model,
    terrain_heights: [TGRID+1][TGRID+1]f32,
    terrain_normals: [TGRID+1][TGRID+1]Vec3,

    cube_mesh:   rl.Mesh,
    cube_mat:    rl.Material,

    snd_load:    rl.Sound,
    snd_powder:  rl.Sound,
    snd_breach:  rl.Sound,
    snd_fire:    rl.Sound,
    snd_hit:     rl.Sound,
    snd_clank:   rl.Sound,
    snd_dud:     rl.Sound,
    snd_explode: rl.Sound,
    audio_ok:    bool,

    time_total:  f32,
    quit_hold_global: f32,
}

st: State

// Per-station axis lock: once you push the stick on one axis, the other is
// suppressed until you release. Without this, diagonals on the 8-way joystick
// fire BOTH treads/aim and tread/pitch at once, which makes precision driving
// while standing-still aiming basically impossible.
StickLock :: enum { None, Vertical, Horizontal }
g_stick_lock: [4]StickLock

// keep mesh-backing memory alive for the lifetime of the program
g_vbuf:  [dynamic]f32
g_nbuf:  [dynamic]f32
g_cbuf:  [dynamic]u8
g_ibuf:  [dynamic]u16

// ── Helpers ─────────────────────────────────────────────────────────────────
v3 :: proc(x, y, z: f32) -> Vec3 { return Vec3{x, y, z} }
v3_add :: proc(a, b: Vec3) -> Vec3 { return Vec3{a.x+b.x, a.y+b.y, a.z+b.z} }
v3_sub :: proc(a, b: Vec3) -> Vec3 { return Vec3{a.x-b.x, a.y-b.y, a.z-b.z} }
v3_scl :: proc(a: Vec3, s: f32) -> Vec3 { return Vec3{a.x*s, a.y*s, a.z*s} }
v3_len :: proc(a: Vec3) -> f32 { return math.sqrt(a.x*a.x + a.y*a.y + a.z*a.z) }
v3_dot :: proc(a, b: Vec3) -> f32 { return a.x*b.x + a.y*b.y + a.z*b.z }
v3_cross :: proc(a, b: Vec3) -> Vec3 {
    return Vec3{a.y*b.z - a.z*b.y, a.z*b.x - a.x*b.z, a.x*b.y - a.y*b.x}
}
v3_norm :: proc(a: Vec3) -> Vec3 {
    l := v3_len(a)
    if l < 0.0001 do return Vec3{0, 1, 0}
    return v3_scl(a, 1.0/l)
}
clampf :: proc(x, a, b: f32) -> f32 {
    if x < a do return a
    if x > b do return b
    return x
}
lerpf :: proc(a, b, t: f32) -> f32 { return a + (b - a) * t }
rand_f :: proc(a, b: f32) -> f32 { return a + rand.float32() * (b - a) }
fade_color :: proc(c: rl.Color, a: f32) -> rl.Color {
    return rl.Color{c.r, c.g, c.b, u8(clampf(a, 0, 1) * 255)}
}
deadzone :: proc(x: f32) -> f32 {
    if abs(x) < STICK_DEAD do return 0
    return x
}

// Read a station's stick with axis-lock: the first axis you push (vertical or
// horizontal) is "locked" until you release it, suppressing the other axis.
// Without this, diagonals on the 8-way joystick can drive AND aim at once,
// which makes "hold position and aim sideways" very twitchy.
read_stick_locked :: proc(slot: int) -> (x, y: f32) {
    up    := rl.IsKeyDown(KEYS_UP[slot])
    down  := rl.IsKeyDown(KEYS_DOWN[slot])
    left  := rl.IsKeyDown(KEYS_LEFT[slot])
    right := rl.IsKeyDown(KEYS_RIGHT[slot])
    has_v := up || down
    has_h := left || right
    switch g_stick_lock[slot] {
    case .None:
        if has_v       do g_stick_lock[slot] = .Vertical
        else if has_h  do g_stick_lock[slot] = .Horizontal
    case .Vertical:
        if !has_v {
            g_stick_lock[slot] = has_h ? .Horizontal : .None
        }
    case .Horizontal:
        if !has_h {
            g_stick_lock[slot] = has_v ? .Vertical : .None
        }
    }
    switch g_stick_lock[slot] {
    case .Vertical:
        y = down ? 1 : (up ? -1 : 0)
        x = 0
    case .Horizontal:
        x = right ? 1 : (left ? -1 : 0)
        y = 0
    case .None:
        x = 0; y = 0
    }
    return
}

// Rotate a tank-local XZ point by yaw radians, matching raylib's
// MatrixRotateY exactly. That way "position via rot_xz" and "mesh rotation
// via MatrixRotateY" agree on which way is which — otherwise parts slide
// relative to their parent as yaw changes.
//
// With this convention, tank-local axes map under yaw:
//   tank-local +X  →  world ( cos yaw, -sin yaw)
//   tank-local +Z  →  world ( sin yaw,  cos yaw)
// So tank-local -Z (negative Z) is the tank's FORWARD direction in world.
// Anything you'd intuitively call "in front of" — mantlet, cupola, barrel
// base — uses a *negative* Z offset in tank-local.
rot_xz :: proc(x, z, yaw: f32) -> (f32, f32) {
    c := math.cos(yaw)
    s := math.sin(yaw)
    return x*c + z*s, -x*s + z*c
}

// Forward vector in world. yaw=0 → world -Z (raylib's "into the scene") so
// the rendered view isn't mirrored. yaw increases CCW from above (raylib math
// convention) so for stick-right → turn-right, we subtract input from yaw.
forward_dir :: proc(yaw, pitch: f32) -> Vec3 {
    cp := math.cos(pitch)
    return Vec3{
        -math.sin(yaw) * cp,
         math.sin(pitch),
        -math.cos(yaw) * cp,
    }
}

// ── Audio synthesis (PCM into raylib Wave) ──────────────────────────────────
SR :: 22050

synth :: proc(dur_s: f32, gen: proc(t: f32, i: int) -> f32) -> rl.Sound {
    frames := int(f32(SR) * dur_s)
    buf := make([]i16, frames)
    defer delete(buf)
    for i in 0..<frames {
        t := f32(i) / f32(SR)
        s := clampf(gen(t, i), -1, 1)
        buf[i] = i16(s * 31000)
    }
    w := rl.Wave{
        frameCount = c.uint(frames),
        sampleRate = c.uint(SR),
        sampleSize = 16,
        channels   = 1,
        data       = raw_data(buf),
    }
    return rl.LoadSoundFromWave(w)
}

env_ad :: proc(t, dur, attack: f32) -> f32 {
    if t < attack do return t / max(attack, 0.0001)
    return clampf(1.0 - (t - attack) / max(dur - attack, 0.0001), 0, 1)
}

gen_load :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.12)
    if t >= dur do return 0
    s := math.sin(t * 2 * math.PI * 240) * 0.6
    s += (rand.float32() * 2 - 1) * 0.4
    return s * env_ad(t, dur, 0.003) * 0.7
}
gen_powder :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.08)
    if t >= dur do return 0
    s := (rand.float32() * 2 - 1) * 0.9
    return s * env_ad(t, dur, 0.001) * 0.55
}
gen_breach :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.22)
    if t >= dur do return 0
    f1 := lerpf(180, 90, t/dur)
    s := math.sin(t * 2 * math.PI * f1) * 0.7
    s += (rand.float32() * 2 - 1) * 0.2 * (1 - t/dur)
    return s * env_ad(t, dur, 0.003) * 0.7
}
gen_fire :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.85)
    if t >= dur do return 0
    f := lerpf(80, 38, t/dur)
    s := math.sin(t * 2 * math.PI * f) * 0.9
    s += (rand.float32() * 2 - 1) * 0.6 * (1 - t/dur)
    return s * env_ad(t, dur, 0.002) * 0.95
}
gen_hit :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.40)
    if t >= dur do return 0
    f := lerpf(1100, 200, t/dur)
    s := math.sin(t * 2 * math.PI * f) * 0.7
    s += (rand.float32() * 2 - 1) * 0.5
    return s * env_ad(t, dur, 0.002) * 0.85
}
gen_clank :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.30)
    if t >= dur do return 0
    f := lerpf(800, 300, t/dur)
    s := math.sin(t * 2 * math.PI * f)
    s += math.sin(t * 2 * math.PI * f * 1.5) * 0.4
    return s * env_ad(t, dur, 0.002) * 0.55
}
gen_dud :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.18)
    if t >= dur do return 0
    s := (rand.float32() * 2 - 1) * 0.6
    return s * env_ad(t, dur, 0.001) * 0.45
}
gen_explode :: proc(t: f32, i: int) -> f32 {
    dur :: f32(1.2)
    if t >= dur do return 0
    f := lerpf(120, 35, t/dur)
    s := math.sin(t * 2 * math.PI * f) * 0.7
    s += (rand.float32() * 2 - 1) * 0.8 * env_ad(t, 0.4, 0.005)
    return s * env_ad(t, dur, 0.003) * 1.0
}

init_audio :: proc() {
    rl.InitAudioDevice()
    if !rl.IsAudioDeviceReady() {
        st.audio_ok = false
        return
    }
    st.audio_ok = true
    st.snd_load    = synth(0.12, gen_load)
    st.snd_powder  = synth(0.08, gen_powder)
    st.snd_breach  = synth(0.22, gen_breach)
    st.snd_fire    = synth(0.85, gen_fire)
    st.snd_hit     = synth(0.40, gen_hit)
    st.snd_clank   = synth(0.30, gen_clank)
    st.snd_dud     = synth(0.18, gen_dud)
    st.snd_explode = synth(1.20, gen_explode)
}

play :: proc(s: rl.Sound, pitch: f32 = 1.0, vol: f32 = 1.0) {
    if !st.audio_ok do return
    rl.SetSoundPitch(s, pitch)
    rl.SetSoundVolume(s, vol)
    rl.PlaySound(s)
}

// ── Terrain ─────────────────────────────────────────────────────────────────
heightfn :: proc(x, z: f32) -> f32 {
    // smooth rolling hills, deterministic — no noise lib required.
    fx := x / TERRAIN_SIZE
    fz := z / TERRAIN_SIZE
    h := math.sin(fx * 3.7) * math.cos(fz * 3.1) * 0.55
    h += math.sin(fx * 7.3 + fz * 5.7 + 1.3) * 0.25
    h += math.cos(fx * 11.0 - fz * 9.5 + 2.1) * 0.10
    // edge bowl — push the playable area down slightly toward middle
    d := math.sqrt(fx*fx + fz*fz)
    edge := clampf((d - 0.32) * 2.0, 0, 1)
    h -= edge * 0.5
    return clampf((h * 0.5 + 0.5) * TERRAIN_HEIGHT, 0, TERRAIN_HEIGHT)
}

sample_terrain :: proc(x, z: f32) -> f32 {
    // bilinear sample of pre-computed height grid
    gx := (x / TERRAIN_SIZE + 0.5) * f32(TGRID)
    gz := (z / TERRAIN_SIZE + 0.5) * f32(TGRID)
    gx = clampf(gx, 0, f32(TGRID) - 0.001)
    gz = clampf(gz, 0, f32(TGRID) - 0.001)
    gxi := int(gx)
    gzi := int(gz)
    fx := gx - f32(gxi)
    fz := gz - f32(gzi)
    h00 := st.terrain_heights[gzi][gxi]
    h10 := st.terrain_heights[gzi][gxi+1]
    h01 := st.terrain_heights[gzi+1][gxi]
    h11 := st.terrain_heights[gzi+1][gxi+1]
    return lerpf(lerpf(h00, h10, fx), lerpf(h01, h11, fx), fz)
}

sample_normal :: proc(x, z: f32) -> Vec3 {
    gx := (x / TERRAIN_SIZE + 0.5) * f32(TGRID)
    gz := (z / TERRAIN_SIZE + 0.5) * f32(TGRID)
    gx = clampf(gx, 0, f32(TGRID))
    gz = clampf(gz, 0, f32(TGRID))
    gxi := int(gx)
    gzi := int(gz)
    if gxi >= TGRID do gxi = TGRID
    if gzi >= TGRID do gzi = TGRID
    return st.terrain_normals[gzi][gxi]
}

build_terrain :: proc() {
    // pre-compute heights
    for z in 0..=TGRID {
        for x in 0..=TGRID {
            wx := (f32(x) / f32(TGRID) - 0.5) * TERRAIN_SIZE
            wz := (f32(z) / f32(TGRID) - 0.5) * TERRAIN_SIZE
            st.terrain_heights[z][x] = heightfn(wx, wz)
        }
    }
    // per-vertex normals via finite difference
    for z in 0..=TGRID {
        for x in 0..=TGRID {
            hl := st.terrain_heights[z][x > 0 ? x-1 : x]
            hr := st.terrain_heights[z][x < TGRID ? x+1 : x]
            hd := st.terrain_heights[z > 0 ? z-1 : z][x]
            hu := st.terrain_heights[z < TGRID ? z+1 : z][x]
            step := TERRAIN_SIZE / f32(TGRID) * 2.0
            n := v3_norm(Vec3{(hl - hr) / step, 1.0, (hd - hu) / step})
            st.terrain_normals[z][x] = n
        }
    }
    // build the mesh
    grid := (TGRID+1) * (TGRID+1)
    tris := TGRID * TGRID * 2
    reserve(&g_vbuf, grid * 3)
    reserve(&g_nbuf, grid * 3)
    reserve(&g_cbuf, grid * 4)
    reserve(&g_ibuf, tris * 3)
    for z in 0..=TGRID {
        for x in 0..=TGRID {
            wx := (f32(x) / f32(TGRID) - 0.5) * TERRAIN_SIZE
            wz := (f32(z) / f32(TGRID) - 0.5) * TERRAIN_SIZE
            h  := st.terrain_heights[z][x]
            n  := st.terrain_normals[z][x]
            append(&g_vbuf, wx, h, wz)
            append(&g_nbuf, n.x, n.y, n.z)
            // color: blend grass/dirt by slope + height
            slope := 1.0 - n.y
            t_dirt := clampf(slope * 4.0, 0, 1)
            t_h := clampf(h / TERRAIN_HEIGHT, 0, 1)
            base := COL_GRASS
            base.r = u8(lerpf(f32(COL_GRASS_DK.r), f32(COL_GRASS.r), t_h))
            base.g = u8(lerpf(f32(COL_GRASS_DK.g), f32(COL_GRASS.g), t_h))
            base.b = u8(lerpf(f32(COL_GRASS_DK.b), f32(COL_GRASS.b), t_h))
            r := u8(lerpf(f32(base.r), f32(COL_DIRT.r), t_dirt))
            g := u8(lerpf(f32(base.g), f32(COL_DIRT.g), t_dirt))
            b := u8(lerpf(f32(base.b), f32(COL_DIRT.b), t_dirt))
            // sun shading via normal.y
            shade := clampf(n.y * 0.6 + 0.45, 0.35, 1.0)
            // procedural texture: multi-frequency noise per vertex breaks up
            // the flat color so the eye can track motion against the ground.
            n1 := math.sin(wx * 0.28) * math.cos(wz * 0.31)
            n2 := math.sin((wx + wz * 0.7) * 0.73 + 1.4) * 0.6
            n3 := math.sin(wx * 1.9 + wz * 1.7) * 0.35
            // hash-y per-cell scatter for a "tuft" feel
            xi := ((x * 73856093) ~ (z * 19349663)) & 0xFF
            n4 := (f32(xi) / 255.0 - 0.5) * 0.7
            tex := (n1 + n2 + n3 + n4) * 0.10   // ±~25% local variation
            shade *= 1.0 + tex
            shade = clampf(shade, 0.32, 1.18)
            r = u8(clampf(f32(r) * shade, 0, 255))
            g = u8(clampf(f32(g) * shade, 0, 255))
            b = u8(clampf(f32(b) * shade, 0, 255))
            append(&g_cbuf, r, g, b, 255)
        }
    }
    for z in 0..<TGRID {
        for x in 0..<TGRID {
            i00 := u16(z * (TGRID+1) + x)
            i10 := u16(z * (TGRID+1) + x + 1)
            i01 := u16((z+1) * (TGRID+1) + x)
            i11 := u16((z+1) * (TGRID+1) + x + 1)
            append(&g_ibuf, i00, i01, i11)
            append(&g_ibuf, i00, i11, i10)
        }
    }
    m := rl.Mesh{
        vertexCount   = c.int(grid),
        triangleCount = c.int(tris),
        vertices      = raw_data(g_vbuf),
        normals       = raw_data(g_nbuf),
        colors        = raw_data(g_cbuf),
        indices       = raw_data(g_ibuf),
    }
    rl.UploadMesh(&m, false)
    st.terrain_mesh = m
    st.terrain_model = rl.LoadModelFromMesh(m)
}

// ── Obstacles ───────────────────────────────────────────────────────────────
gen_obstacles :: proc() {
    // deterministic seed for repeatable layout per round
    rand.reset(42)
    st.obs_count = 0
    // a few large boulders and ruin walls scattered, but not too near tank spawns
    spots := [?]Vec3{
        {-30,  0, -10}, { 25,  0,  18}, {-10,  0,  35}, { 40,  0, -25},
        {  0,  0, -45}, {-55,  0,  20}, { 55,  0,  40}, {-40,  0, -45},
        { 10,  0,  10}, {-20,  0, -30}, { 30,  0,  55}, {-65,  0, -30},
        { 60,  0,   0}, {-15,  0,  60}, { 45,  0, -55}, {  5,  0,  -5},
    }
    for s, i in spots {
        kind := i32(rand.int_max(3))
        x := s.x + rand_f(-6, 6)
        z := s.z + rand_f(-6, 6)
        y := sample_terrain(x, z)
        size: Vec3
        col := COL_ROCK
        switch kind {
        case 0:   // rock
            r := rand_f(1.8, 3.2)
            size = Vec3{r, r * rand_f(0.8, 1.2), r}
            col = COL_ROCK
            if rand.float32() < 0.5 do col = COL_ROCK_DK
        case 1:   // ruin wall
            size = Vec3{rand_f(3.5, 6.0), rand_f(2.0, 3.5), rand_f(0.6, 1.0)}
            col = COL_RUIN
        case 2:   // log / pillar
            r := rand_f(0.7, 1.1)
            size = Vec3{r, rand_f(2.2, 3.6), r}
            col = COL_RUIN
        }
        if st.obs_count >= len(st.obstacles) do break
        st.obstacles[st.obs_count] = Obstacle{
            pos = Vec3{x, y, z},
            size = size,
            yaw = rand_f(0, 2 * math.PI),
            color = col,
            kind = kind,
        }
        st.obs_count += 1
    }
}

obstacle_blocks_circle :: proc(x, z, r: f32) -> bool {
    for i in 0..<st.obs_count {
        o := &st.obstacles[i]
        // approximate footprint as axis-aligned circle of effective radius
        eff: f32
        switch o.kind {
        case 0: eff = (o.size.x + o.size.z) * 0.5 * 0.9
        case 1: eff = math.sqrt(o.size.x*o.size.x + o.size.z*o.size.z) * 0.5 * 0.85
        case 2: eff = o.size.x * 0.95
        case:   eff = 1.0
        }
        dx := x - o.pos.x
        dz := z - o.pos.z
        if dx*dx + dz*dz < (r + eff)*(r + eff) do return true
    }
    return false
}

obstacle_shell_hit :: proc(pos: Vec3, r: f32) -> bool {
    for i in 0..<st.obs_count {
        o := &st.obstacles[i]
        // AABB-ish vs sphere with rough orientation ignored (good enough)
        dx := pos.x - o.pos.x
        dy := pos.y - (o.pos.y + o.size.y * 0.5)
        dz := pos.z - o.pos.z
        eff_h := o.size.y * 0.6
        eff_r: f32
        switch o.kind {
        case 0: eff_r = (o.size.x + o.size.z) * 0.5 * 0.55
        case 1: eff_r = math.sqrt(o.size.x*o.size.x + o.size.z*o.size.z) * 0.5 * 0.55
        case 2: eff_r = o.size.x * 0.55
        case:   eff_r = 1.0
        }
        if dx*dx + dz*dz < (eff_r + r)*(eff_r + r) && abs(dy) < eff_h + r {
            return true
        }
    }
    return false
}

// ── Tank setup / damage ─────────────────────────────────────────────────────
tank_alive_hp :: proc(t: ^Tank) -> f32 {
    return clampf(HP_MAX - t.front_hits - t.side_hits - t.rear_hits, 0, HP_MAX)
}

spawn_tank :: proc(t: ^Tank, slot: int) {
    spots := [2]Vec3{
        Vec3{-70, 0,  -70},
        Vec3{ 70, 0,   70},
    }
    // yaw=0 = facing -Z (north). yaw increases CCW in raylib math
    // convention. Tank 0 at SW corner faces NE: forward = (sin*-1, _, cos*-1)
    // ≈ (0.707, _, -0.707), so yaw = 7π/4 (= -π/4). Tank 1 at NE faces SW
    // (yaw = 3π/4).
    facings := [2]f32{ math.PI * 1.75, math.PI * 0.75 }
    t.pos = spots[slot]
    t.pos.y = sample_terrain(t.pos.x, t.pos.z)
    t.hull_yaw = facings[slot]
    t.hull_pitch = 0
    t.hull_roll = 0
    t.turret_yaw = 0
    t.barrel_pitch = 0.15
    t.left_v = 0
    t.right_v = 0
    t.reload = .Breach_Open_Empty
    t.powder = 0
    t.breach_anim = 1.0
    t.front_hits = 0
    t.side_hits = 0
    t.rear_hits = 0
    t.hp = HP_MAX
    t.alive = true
    t.respawn_t = 0
    t.invuln_t = 1.0
    t.hit_flash = 0
    t.smoke_t = 0
    t.muzzle_flash = 0
    t.recoil = 0
}

start_round :: proc() {
    for i in 0..<2 {
        spawn_tank(&st.tanks[i], i)
    }
    for i in 0..<len(st.shells) do st.shells[i].alive = false
    gen_obstacles()
    st.round_t = 0
    st.round_start_t = 2.5
    st.mode = .Playing
}

start_match :: proc() {
    for i in 0..<2 do st.tanks[i].rounds_won = 0
    st.cur_round = 1
    start_round()
}

// ── Tank physics ────────────────────────────────────────────────────────────
update_tank :: proc(t: ^Tank, slot: int, dt: f32) {
    // station indices: left = slot*2, right = slot*2+1
    sl := slot * 2
    sr := slot * 2 + 1

    lx, ly := read_stick_locked(sl)
    rx, ry := read_stick_locked(sr)

    // quit hold (this player's own pair — either pair counts)
    quit_pair_held := false
    if rl.IsKeyDown(KEYS_JUMP[sl]) && rl.IsKeyDown(KEYS_ATK[sl]) &&
       rl.IsKeyDown(KEYS_JUMP[sr]) && rl.IsKeyDown(KEYS_ATK[sr]) {
        quit_pair_held = true
    }
    if quit_pair_held {
        t.quit_hold += dt
    } else {
        t.quit_hold = 0
    }

    // Drive treads with INERTIA: when a stick is held, accelerate that tread
    // toward the target velocity. When the stick is released, the tread just
    // coasts with a gentle damp — it doesn't snap back to zero. So you can
    // build up forward momentum and release the sticks to roll, and one stick
    // released while the other keeps pushing makes the tank arc in a wide
    // loop (the released tread is still spinning down). Only sticks pushed in
    // opposite directions give a true pivot-in-place.
    left_target  := -ly * TREAD_MAX_V
    right_target := -ry * TREAD_MAX_V
    ly_active := abs(ly) > STICK_DEAD
    ry_active := abs(ry) > STICK_DEAD
    apply_friction :: proc(v: f32, dt: f32) -> f32 {
        f := TREAD_FRICTION * dt
        if abs(v) < TREAD_STOP_V do return 0
        if abs(v) <= f          do return 0
        return v - (v > 0 ? f : -f)
    }
    if t.alive {
        if ly_active {
            t.left_v += clampf(left_target - t.left_v, -TREAD_ACC*dt, TREAD_ACC*dt)
        } else {
            t.left_v = apply_friction(t.left_v, dt)
        }
        if ry_active {
            t.right_v += clampf(right_target - t.right_v, -TREAD_ACC*dt, TREAD_ACC*dt)
        } else {
            t.right_v = apply_friction(t.right_v, dt)
        }
    } else {
        t.left_v  = apply_friction(t.left_v, dt * 3)
        t.right_v = apply_friction(t.right_v, dt * 3)
    }

    // Skid-steer: forward speed = average of treads, yaw rate from
    // differential. yaw increases CCW (raylib math convention), so for "left
    // tread forward → tank turns right" (real-tank physics), yaw must
    // *decrease* when left > right — hence (right - left).
    forward_v := (t.left_v + t.right_v) * 0.5
    yaw_rate  := (t.right_v - t.left_v) / HULL_W * YAW_RATE_SCALE

    if t.alive {
        new_yaw := t.hull_yaw + yaw_rate * dt
        // candidate position — uses forward_dir's XZ components so the
        // mesh rotation and movement direction stay in lockstep.
        fx := -math.sin(new_yaw)
        fz := -math.cos(new_yaw)
        nx := t.pos.x + fx * forward_v * dt
        nz := t.pos.z + fz * forward_v * dt
        // arena clamp (the playable area)
        bound : f32 = HALF_T - 8
        nx = clampf(nx, -bound, bound)
        nz = clampf(nz, -bound, bound)
        // obstacle block (treat tank as a circle in plan view)
        if !obstacle_blocks_circle(nx, nz, HULL_W * 0.6) {
            // also avoid the other tank
            other := &st.tanks[1 - slot]
            if other.alive {
                dx := nx - other.pos.x
                dz := nz - other.pos.z
                min_d := HULL_W * 1.2
                if dx*dx + dz*dz > min_d*min_d {
                    t.pos.x = nx
                    t.pos.z = nz
                }
            } else {
                t.pos.x = nx
                t.pos.z = nz
            }
        }
        t.hull_yaw = new_yaw
    }
    // terrain follow
    t.pos.y = sample_terrain(t.pos.x, t.pos.z)
    // hull pitch / roll from local terrain normal
    n := sample_normal(t.pos.x, t.pos.z)
    // Tank-local "forward" and "right" axes in world XZ. Forward must match
    // forward_dir (-sin, -cos). Right = forward rotated 90° CW (right of
    // facing direction); for MatrixRotateY(yaw)-rotated mesh, right axis is
    // (cos yaw, -sin yaw).
    fx_h := -math.sin(t.hull_yaw)
    fz_h := -math.cos(t.hull_yaw)
    rx_h :=  math.cos(t.hull_yaw)
    rz_h := -math.sin(t.hull_yaw)
    n_fwd := n.x * fx_h + n.z * fz_h
    n_rgt := n.x * rx_h + n.z * rz_h
    target_pitch := math.atan2(-n_fwd, max(n.y, 0.1))
    target_roll  := math.atan2( n_rgt, max(n.y, 0.1))
    t.hull_pitch += clampf(target_pitch - t.hull_pitch, -2.0*dt, 2.0*dt)
    t.hull_roll  += clampf(target_roll  - t.hull_roll,  -2.0*dt, 2.0*dt)

    // Aim: left stick X → barrel pitch, right stick X → turret yaw.
    if t.alive {
        // pitch: positive X (right) = raise barrel (more elevation)
        dp := deadzone(lx) * BARREL_PITCH_V * dt
        t.barrel_pitch = clampf(t.barrel_pitch + dp, BARREL_PITCH_MIN, BARREL_PITCH_MAX)
        // turret yaw: stick right (rx > 0) should pan the view right (compass
        // CW). yaw increases CCW in our convention, so right-stick *decreases*
        // turret_yaw.
        t.turret_yaw -= deadzone(rx) * TURRET_YAW_V * dt
    }
    // breach animation
    target_breach: f32 = 0
    if t.reload == .Breach_Open_Empty || t.reload == .Breach_Open_Shell || t.reload == .Breach_Open_Powdered {
        target_breach = 1
    }
    t.breach_anim += clampf(target_breach - t.breach_anim, -4*dt, 4*dt)

    t.invuln_t = max(0, t.invuln_t - dt)
    t.hit_flash = max(0, t.hit_flash - dt)
    t.muzzle_flash = max(0, t.muzzle_flash - dt * 4)
    t.recoil += clampf(0 - t.recoil, -3*dt, 3*dt)
    t.smoke_t += dt
    t.hp = tank_alive_hp(t)

    if !t.alive {
        t.respawn_t -= dt
        if t.respawn_t <= 0 {
            // respawn lives in round flow (don't auto-respawn here unless mode allows)
        }
    }

    // Reload inputs — only on edge presses.
    if t.alive {
        if rl.IsKeyPressed(KEYS_JUMP[sl]) {
            // load shell
            if t.reload == .Breach_Open_Empty {
                t.reload = .Breach_Open_Shell
                play(st.snd_load, 1.0, 0.9)
            } else {
                play(st.snd_dud, 1.0, 0.6)
            }
        }
        if rl.IsKeyPressed(KEYS_ATK[sl]) {
            // add powder
            if t.reload == .Breach_Open_Shell {
                t.powder = 1
                t.reload = .Breach_Open_Powdered
                play(st.snd_powder, 1.0, 0.85)
            } else if t.reload == .Breach_Open_Powdered && t.powder < MAX_CHARGES {
                t.powder += 1
                play(st.snd_powder, 1.0 + f32(t.powder) * 0.08, 0.85)
            } else {
                play(st.snd_dud, 1.1, 0.5)
            }
        }
        if rl.IsKeyPressed(KEYS_JUMP[sr]) {
            // toggle breach
            switch t.reload {
            case .Breach_Open_Empty, .Breach_Open_Shell, .Breach_Open_Powdered:
                if t.reload == .Breach_Open_Powdered {
                    t.reload = .Breach_Closed_Loaded
                } else {
                    // closing an unloaded breach — allowed but no shot possible
                    t.reload = .Breach_Closed_Spent
                }
                play(st.snd_breach, 0.95, 0.9)
            case .Breach_Closed_Loaded:
                // re-open before firing — abort the shot
                t.reload = .Breach_Open_Powdered  // keep the load
                play(st.snd_breach, 1.1, 0.8)
            case .Breach_Closed_Spent:
                t.reload = .Breach_Open_Empty
                t.powder = 0
                play(st.snd_breach, 1.1, 0.9)
            }
        }
        if rl.IsKeyPressed(KEYS_ATK[sr]) {
            // fire
            if t.reload == .Breach_Closed_Loaded {
                fire_shell(t, i32(slot))
                t.reload = .Breach_Closed_Spent
                t.muzzle_flash = 1.0
                t.recoil = 1.0
                play(st.snd_fire, rand_f(0.95, 1.05), 1.0)
            } else {
                play(st.snd_dud, 0.9, 0.6)
            }
        }
    }
}

// ── Cannon geometry ─────────────────────────────────────────────────────────
turret_world_yaw :: proc(t: ^Tank) -> f32 { return t.hull_yaw + t.turret_yaw }

cupola_world_pos :: proc(t: ^Tank) -> Vec3 {
    // Camera at "commander head out of hatch": above the cupola top so we
    // don't clip into its geometry, and slightly forward so the barrel is
    // framed naturally in the lower view. Tank-local -Z is forward, so the
    // "slightly forward" offset is negative.
    local_y : f32 = HULL_H + TURRET_H + CUPOLA_H + 0.45
    local_z : f32 = -0.4
    yaw := turret_world_yaw(t)
    wx, wz := rot_xz(0, local_z, yaw)
    return Vec3{t.pos.x + wx, t.pos.y + local_y, t.pos.z + wz}
}

barrel_tip_pos :: proc(t: ^Tank) -> Vec3 {
    yaw := turret_world_yaw(t)
    pitch := t.barrel_pitch
    base_y := t.pos.y + HULL_H + TURRET_H * 0.55
    // barrel base offset forward of turret center by TURRET_R
    base_local := TURRET_R * 0.6
    bx := math.sin(yaw) * base_local
    bz := math.cos(yaw) * base_local
    f := forward_dir(yaw, pitch)
    return Vec3{
        t.pos.x + bx + f.x * BARREL_L,
        base_y + f.y * BARREL_L,
        t.pos.z + bz + f.z * BARREL_L,
    }
}

barrel_base_pos :: proc(t: ^Tank) -> Vec3 {
    yaw := turret_world_yaw(t)
    base_y := t.pos.y + HULL_H + TURRET_H * 0.55
    base_local : f32 = -TURRET_R * 0.6   // negative = forward of turret center
    bx, bz := rot_xz(0, base_local, yaw)
    return Vec3{t.pos.x + bx, base_y, t.pos.z + bz}
}

// ── Shells ──────────────────────────────────────────────────────────────────
fire_shell :: proc(t: ^Tank, owner: i32) {
    // find free slot
    for i in 0..<len(st.shells) {
        if !st.shells[i].alive {
            s := &st.shells[i]
            s.alive = true
            s.owner = owner
            s.pos = barrel_tip_pos(t)
            yaw := turret_world_yaw(t)
            pitch := t.barrel_pitch
            f := forward_dir(yaw, pitch)
            charges := t.powder
            if charges < 1 do charges = 1
            v := SHELL_BASE_V + f32(charges - 1) * SHELL_CHARGE_V
            s.vel = Vec3{f.x * v, f.y * v, f.z * v}
            s.life = SHELL_LIFE
            s.trail_n = 0
            s.trail_fill = 0
            return
        }
    }
}

update_shells :: proc(dt: f32) {
    for i in 0..<len(st.shells) {
        s := &st.shells[i]
        if !s.alive do continue
        s.life -= dt
        if s.life <= 0 { s.alive = false; continue }
        // gravity + light drag
        s.vel.y += GRAVITY * dt
        damp := math.exp(-SHELL_DRAG * dt)
        s.vel.x *= damp
        s.vel.y *= damp
        s.vel.z *= damp
        s.pos.x += s.vel.x * dt
        s.pos.y += s.vel.y * dt
        s.pos.z += s.vel.z * dt
        // trail
        s.trail_n = (s.trail_n + 1) % i32(len(s.trail))
        s.trail[s.trail_n] = s.pos
        if s.trail_fill < i32(len(s.trail)) do s.trail_fill += 1
        // arena escape
        if abs(s.pos.x) > HALF_T + 5 || abs(s.pos.z) > HALF_T + 5 {
            s.alive = false; continue
        }
        // ground impact
        gh := sample_terrain(s.pos.x, s.pos.z)
        if s.pos.y < gh + SHELL_R {
            s.alive = false
            play(st.snd_hit, rand_f(0.85, 1.0), 0.5)
            continue
        }
        // obstacle impact
        if obstacle_shell_hit(s.pos, SHELL_R) {
            s.alive = false
            play(st.snd_clank, rand_f(0.9, 1.1), 0.6)
            continue
        }
        // tank impact
        for j in 0..<2 {
            if i32(j) == s.owner do continue
            t := &st.tanks[j]
            if !t.alive || t.invuln_t > 0 do continue
            // bounding-box-ish check around tank center (slightly above hull)
            cx := t.pos.x
            cy := t.pos.y + HULL_H * 0.5
            cz := t.pos.z
            dx := s.pos.x - cx
            dy := s.pos.y - cy
            dz := s.pos.z - cz
            // rotate dx,dz into tank-local frame
            lx, lz := rot_xz(dx, dz, -t.hull_yaw)
            // local half-extents (hull + turret cone)
            if abs(lx) < HULL_W * 0.55 + SHELL_R && abs(lz) < HULL_L * 0.6 + SHELL_R && abs(dy) < HULL_H + TURRET_H + SHELL_R {
                apply_hit(t, s, lx, lz)
                s.alive = false
                break
            }
        }
    }
}

apply_hit :: proc(t: ^Tank, s: ^Shell, lx, lz: f32) {
    // determine hit side from local impact point
    side: int
    // angle from center to impact in tank-local frame; +Z = front
    ang := math.atan2(lx, lz)
    abs_a := abs(ang)
    if abs_a < math.PI * 0.33 {
        side = 0   // front
        t.front_hits += DMG_FRONT
    } else if abs_a > math.PI * 0.66 {
        side = 2   // rear
        t.rear_hits += DMG_REAR
    } else {
        side = 1   // sides
        t.side_hits += DMG_SIDE
    }
    t.hit_flash = 0.6
    t.invuln_t = INVULN_T
    t.last_hit_dir = ang
    play(st.snd_hit, rand_f(0.95, 1.1), 0.95)
    play(st.snd_clank, rand_f(0.9, 1.1), 0.7)
    hp_now := tank_alive_hp(t)
    if hp_now <= 0 {
        destroy_tank(t)
    }
    _ = side
}

destroy_tank :: proc(t: ^Tank) {
    t.alive = false
    t.respawn_t = RESPAWN_T
    t.smoke_t = 0
    play(st.snd_explode, rand_f(0.9, 1.05), 1.0)
}

// ── 3D rendering ────────────────────────────────────────────────────────────
// Compose a TRS matrix. raylib's `*` follows the column-vector convention:
// the matrix on the LEFT is applied LAST to the vertex. So for a vertex to be
// scaled first, rotated next, then translated to a world position, the
// product must be: T * R * S.
trs_matrix :: proc(pos: Vec3, size: Vec3, yaw, pitch, roll: f32) -> rl.Matrix {
    s := rl.MatrixScale(size.x, size.y, size.z)
    rZ := rl.MatrixRotateZ(roll)
    rX := rl.MatrixRotateX(pitch)
    rY := rl.MatrixRotateY(yaw)
    t := rl.MatrixTranslate(pos.x, pos.y, pos.z)
    // Order in column-vector terms: scale → roll → pitch → yaw → translate.
    // Pitch/roll go BEFORE yaw so they tilt in the tank's local frame; if yaw
    // came first the pitch axis would stay world-aligned and a tank facing
    // east would "roll sideways" when going up a forward-sloped hill.
    return t * rY * rX * rZ * s
}

draw_box_rot :: proc(center: Vec3, size: Vec3, yaw, pitch, roll: f32, col: rl.Color) {
    st.cube_mat.maps[0].color = col
    rl.DrawMesh(st.cube_mesh, st.cube_mat, trs_matrix(center, size, yaw, pitch, roll))
}

draw_tank :: proc(t: ^Tank, slot: int) {
    if !t.alive {
        wreck_col := rl.Color{40, 40, 40, 255}
        draw_box_rot(Vec3{t.pos.x, t.pos.y + HULL_H * 0.4, t.pos.z},
                     Vec3{HULL_W, HULL_H * 0.7, HULL_L * 0.9},
                     t.hull_yaw, t.hull_pitch, t.hull_roll, wreck_col)
        rcol := rl.Color{60, 60, 65, 200}
        for k in 0..<5 {
            kf := f32(k)
            r := 0.8 + kf * 0.4 + math.sin(t.smoke_t * 1.2 + kf) * 0.2
            y := t.pos.y + HULL_H + kf * 1.2 + t.smoke_t * 0.4
            rl.DrawSphere(Vec3{t.pos.x + math.sin(t.smoke_t*0.8 + kf)*0.4, y, t.pos.z + math.cos(t.smoke_t*0.9 + kf)*0.4}, r, rcol)
        }
        return
    }

    base_col := P_COLORS[slot]
    if t.hit_flash > 0 {
        flash := t.hit_flash / 0.6
        base_col.r = u8(clampf(f32(base_col.r) + 80 * flash, 0, 255))
        base_col.g = u8(clampf(f32(base_col.g) + 80 * flash, 0, 255))
        base_col.b = u8(clampf(f32(base_col.b) + 80 * flash, 0, 255))
    }

    // Hull
    draw_box_rot(Vec3{t.pos.x, t.pos.y + HULL_H * 0.5, t.pos.z},
                 Vec3{HULL_W, HULL_H, HULL_L},
                 t.hull_yaw, t.hull_pitch, t.hull_roll, base_col)

    // Treads — two slim boxes flanking the hull. Compute their world position
    // by rotating the local offset by hull_yaw.
    tread_h : f32 = HULL_H * 0.7
    tread_y := t.pos.y + tread_h * 0.5
    tread_col := rl.Color{30, 30, 35, 255}
    for sx in 0..<2 {
        side_sign : f32 = sx == 0 ? -1.0 : 1.0
        local_x := side_sign * (HULL_W * 0.5 + TREAD_W * 0.5)
        wx, wz := rot_xz(local_x, 0, t.hull_yaw)
        draw_box_rot(Vec3{t.pos.x + wx, tread_y, t.pos.z + wz},
                     Vec3{TREAD_W, tread_h, HULL_L * 1.05},
                     t.hull_yaw, t.hull_pitch, t.hull_roll, tread_col)
    }

    // Turret
    yaw_w := turret_world_yaw(t)
    turret_pos := Vec3{t.pos.x, t.pos.y + HULL_H + TURRET_H * 0.5, t.pos.z}
    draw_box_rot(turret_pos,
                 Vec3{TURRET_R * 2.2, TURRET_H, TURRET_R * 2.6},
                 yaw_w, t.hull_pitch, t.hull_roll, base_col)
    // mantlet: offset forward in turret-local frame
    mx, mz := rot_xz(0, -TURRET_R * 0.9, yaw_w)   // negative Z = forward of turret center
    draw_box_rot(Vec3{t.pos.x + mx, t.pos.y + HULL_H + TURRET_H * 0.5, t.pos.z + mz},
                 Vec3{TURRET_R * 1.6, TURRET_H * 0.8, TURRET_R * 0.4},
                 yaw_w, t.hull_pitch, t.hull_roll, rl.Color{u8(f32(base_col.r) * 0.85), u8(f32(base_col.g) * 0.85), u8(f32(base_col.b) * 0.85), 255})
    // cupola — vertical cylinder behind turret center
    cx, cz := rot_xz(0, -0.3, yaw_w)
    cup_base := Vec3{t.pos.x + cx, t.pos.y + HULL_H + TURRET_H, t.pos.z + cz}
    cup_top  := Vec3{cup_base.x, cup_base.y + CUPOLA_H, cup_base.z}
    rl.DrawCylinderEx(cup_base, cup_top, CUPOLA_R, CUPOLA_R, 12, rl.Color{40, 40, 45, 255})

    // Barrel — separate transform with pitch
    base := barrel_base_pos(t)
    f := forward_dir(yaw_w, t.barrel_pitch)
    mid := Vec3{
        base.x + f.x * BARREL_L * 0.5 - f.x * t.recoil * 0.6,
        base.y + f.y * BARREL_L * 0.5 - f.y * t.recoil * 0.6,
        base.z + f.z * BARREL_L * 0.5 - f.z * t.recoil * 0.6,
    }
    tip := Vec3{
        base.x + f.x * BARREL_L - f.x * t.recoil * 0.6,
        base.y + f.y * BARREL_L - f.y * t.recoil * 0.6,
        base.z + f.z * BARREL_L - f.z * t.recoil * 0.6,
    }
    _ = mid
    // draw the barrel as a cylinder from base to tip
    rl.DrawCylinderEx(base, tip, BARREL_R, BARREL_R, 8, rl.Color{50, 50, 55, 255})
    // muzzle flash
    if t.muzzle_flash > 0 {
        rl.DrawSphere(tip, BARREL_R * (1.5 + t.muzzle_flash * 3.0), fade_color(rl.Color{255, 220, 130, 255}, t.muzzle_flash))
        rl.DrawSphere(tip, BARREL_R * (0.8 + t.muzzle_flash * 5.0), fade_color(rl.Color{255, 255, 220, 255}, t.muzzle_flash * 0.6))
    }
}

draw_shell :: proc(s: ^Shell) {
    if !s.alive do return
    // trail (oldest → newest) using ring buffer
    cnt := int(s.trail_fill)
    if cnt > 1 {
        start := int(s.trail_n) - cnt + 1
        if start < 0 do start += len(s.trail)
        for k in 0..<cnt-1 {
            a := s.trail[(start + k) % len(s.trail)]
            b := s.trail[(start + k + 1) % len(s.trail)]
            t := f32(k) / f32(cnt)
            col := fade_color(rl.Color{255, 240, 180, 255}, 0.15 + t * 0.65)
            rl.DrawLine3D(a, b, col)
        }
    }
    rl.DrawSphere(s.pos, SHELL_R, rl.Color{255, 230, 140, 255})
}

draw_obstacles :: proc() {
    for i in 0..<st.obs_count {
        o := &st.obstacles[i]
        center := Vec3{o.pos.x, o.pos.y + o.size.y * 0.5, o.pos.z}
        switch o.kind {
        case 0:
            // rock — sphere (yaw irrelevant)
            rl.DrawSphereEx(center, o.size.x * 0.5, 8, 10, o.color)
        case 1:
            // ruin wall — rotated box
            draw_box_rot(center, o.size, o.yaw, 0, 0, o.color)
        case 2:
            // pillar — vertical cylinder
            base := Vec3{o.pos.x, o.pos.y, o.pos.z}
            top  := Vec3{o.pos.x, o.pos.y + o.size.y, o.pos.z}
            rl.DrawCylinderEx(base, top, o.size.x * 0.5, o.size.x * 0.5, 10, o.color)
        }
    }
}

draw_sky :: proc() {
    // Drawn as a 2D gradient before BeginMode3D — fills the viewport.
    rl.DrawRectangleGradientV(0, 0, VW, VH, COL_SKY_TOP, COL_SKY_HORZ)
}

setup_camera :: proc(slot: int) -> rl.Camera3D {
    t := &st.tanks[slot]
    cup := cupola_world_pos(t)
    yaw_w := turret_world_yaw(t)
    pitch := t.barrel_pitch * 0.5   // camera tilts a bit with the barrel (commander tracks the aim)
    f := forward_dir(yaw_w, pitch)
    target := Vec3{cup.x + f.x * 10, cup.y + f.y * 10, cup.z + f.z * 10}
    return rl.Camera3D{
        position = cup,
        target = target,
        up = Vec3{0, 1, 0},
        fovy = 65,
        projection = .PERSPECTIVE,
    }
}

render_player_view :: proc(slot: int) {
    rl.BeginTextureMode(st.rt[slot])
    rl.ClearBackground(COL_SKY_HORZ)
    draw_sky()
    cam := setup_camera(slot)
    st.cam[slot] = cam
    rl.BeginMode3D(cam)
    // terrain
    rl.DrawModel(st.terrain_model, Vec3{0, 0, 0}, 1.0, rl.WHITE)
    // obstacles
    draw_obstacles()
    // both tanks
    for i in 0..<2 do draw_tank(&st.tanks[i], i)
    // shells
    for i in 0..<len(st.shells) do draw_shell(&st.shells[i])
    // small grid markers near the camera tank to give scale
    rl.EndMode3D()
    draw_hud_overlay(slot)
    rl.EndTextureMode()
}

// ── HUD ─────────────────────────────────────────────────────────────────────
// Each viewport is 1920×540. HUD lives in a bottom strip; 3D fills the rest.
HUD_H :: 130

draw_hud_overlay :: proc(slot: int) {
    t := &st.tanks[slot]
    other := &st.tanks[1 - slot]
    tint := P_TINT[slot]

    py : i32 = i32(VH) - HUD_H
    rl.DrawRectangle(0, py, i32(VW), HUD_H, COL_HUDBG)
    rl.DrawLineEx(Vec2{0, f32(py)}, Vec2{f32(VW), f32(py)}, 2, COL_PANEL)

    // ── LEFT: player banner, breach state, ammo ──
    rl.DrawText(slot == 0 ? cstring("P1") : cstring("P2"), 22, py + 14, 44, tint)
    rl.DrawText("BREACH", 110, py + 12, 18, COL_DIM)
    breach_lbl: cstring = "—"
    breach_col := COL_DIM
    switch t.reload {
    case .Breach_Open_Empty:    breach_lbl = "OPEN · EMPTY";     breach_col = COL_AMBER
    case .Breach_Open_Shell:    breach_lbl = "OPEN · SHELL";     breach_col = COL_AMBER
    case .Breach_Open_Powdered: breach_lbl = "OPEN · POWDERED";  breach_col = COL_AMBER
    case .Breach_Closed_Loaded: breach_lbl = "CLOSED · READY";   breach_col = COL_GREEN
    case .Breach_Closed_Spent:  breach_lbl = "CLOSED · SPENT";   breach_col = COL_RED
    }
    rl.DrawText(breach_lbl, 110, py + 34, 26, breach_col)

    // Ammo row: shell + powder
    rl.DrawText("SHELL", 110, py + 72, 16, COL_DIM)
    sh_loaded := t.reload != .Breach_Open_Empty && t.reload != .Breach_Closed_Spent
    rl.DrawCircle(180, py + 92, 12, sh_loaded ? COL_GREEN : COL_DIM)
    rl.DrawCircleLines(180, py + 92, 12, COL_WHITE)
    rl.DrawText("POWDER", 210, py + 72, 16, COL_DIM)
    for k in 0..<MAX_CHARGES {
        cx := i32(295) + i32(k) * 28
        cy := py + 82
        loaded := i32(k) < t.powder
        col := loaded ? COL_AMBER : COL_DIM
        if !loaded do col.a = 90
        rl.DrawRectangle(cx, cy, 20, 20, col)
        rl.DrawRectangleLines(cx, cy, 20, 20, COL_WHITE)
    }

    // ── CENTER: tank minimap with armor + turret direction arrow ──
    mm_w : i32 = 400
    mm_h : i32 = HUD_H - 20
    mm_x : i32 = i32(VW)/2 - mm_w/2
    mm_y : i32 = py + 10
    rl.DrawRectangleLines(mm_x, mm_y, mm_w, mm_h, COL_PANEL)

    cx := mm_x + mm_w/2
    cy := mm_y + mm_h/2
    hw : i32 = 60
    hl : i32 = 90

    // Front/rear labels (above and below the armor frame)
    rl.DrawText("FRONT", cx - 24, mm_y + 4, 14, COL_DIM)
    rl.DrawText("REAR",  cx - 20, mm_y + mm_h - 18, 14, COL_DIM)

    // Hull silhouette (front = up)
    rl.DrawRectangle(cx - hw/2, cy - hl/2, hw, hl, P_COLORS[slot])
    rl.DrawRectangleLines(cx - hw/2, cy - hl/2, hw, hl, COL_WHITE)

    // Turret indicator: a small disc on the hull plus an arrow showing where
    // the cannon is pointing relative to the hull (turret_yaw, hull-relative).
    tcx := f32(cx)
    tcy := f32(cy)
    rl.DrawCircle(i32(tcx), i32(tcy), 16, rl.Color{40, 40, 45, 255})
    rl.DrawCircleLines(i32(tcx), i32(tcy), 16, COL_WHITE)
    // turret_yaw is CCW around +Y in raylib math (positive = compass LEFT).
    // On the minimap, hull forward = up. A turret rotated CCW (positive yaw)
    // points left on the minimap, so the X offset is -sin(tang).
    tang := t.turret_yaw
    arrow_len : f32 = 38
    ax := tcx - math.sin(tang) * arrow_len
    ay := tcy - math.cos(tang) * arrow_len
    rl.DrawLineEx(Vec2{tcx, tcy}, Vec2{ax, ay}, 4, tint)
    // arrow head — two prongs from the tip going back-and-to-the-side
    head_w : f32 = 0.5
    h1x := ax + math.sin(tang + head_w) * 10
    h1y := ay + math.cos(tang + head_w) * 10
    h2x := ax + math.sin(tang - head_w) * 10
    h2y := ay + math.cos(tang - head_w) * 10
    rl.DrawLineEx(Vec2{ax, ay}, Vec2{h1x, h1y}, 4, tint)
    rl.DrawLineEx(Vec2{ax, ay}, Vec2{h2x, h2y}, 4, tint)

    // Armor bars on four sides (drain green → red)
    f_frac := clampf(t.front_hits / 5.0, 0, 1)
    s_frac := clampf(t.side_hits  / 5.0, 0, 1)
    r_frac := clampf(t.rear_hits  / 5.0, 0, 1)
    bh : i32 = 8
    // front (above silhouette)
    rl.DrawRectangle(cx - hw/2, cy - hl/2 - 12, hw, bh, COL_DIM)
    rl.DrawRectangle(cx - hw/2, cy - hl/2 - 12, i32(f32(hw) * (1 - f_frac)), bh, f_frac > 0.8 ? COL_RED : COL_GREEN)
    // sides (left/right of silhouette)
    rl.DrawRectangle(cx + hw/2 + 4, cy - hl/2, bh, hl, COL_DIM)
    rl.DrawRectangle(cx + hw/2 + 4, cy - hl/2, bh, i32(f32(hl) * (1 - s_frac)), s_frac > 0.66 ? COL_RED : COL_GREEN)
    rl.DrawRectangle(cx - hw/2 - bh - 4, cy - hl/2, bh, hl, COL_DIM)
    rl.DrawRectangle(cx - hw/2 - bh - 4, cy - hl/2, bh, i32(f32(hl) * (1 - s_frac)), s_frac > 0.66 ? COL_RED : COL_GREEN)
    // rear (below silhouette) — fragile zone, redder threshold
    rl.DrawRectangle(cx - hw/2, cy + hl/2 + 4, hw, bh, COL_DIM)
    rl.DrawRectangle(cx - hw/2, cy + hl/2 + 4, i32(f32(hw) * (1 - r_frac)), bh, r_frac > 0.1 ? COL_RED : COL_GREEN)

    // ── RIGHT: range + round wins ──
    rx_base := i32(VW) - 320
    rl.DrawText("RANGE", rx_base, py + 12, 18, COL_DIM)
    dx := other.pos.x - t.pos.x
    dz := other.pos.z - t.pos.z
    dist := math.sqrt(dx*dx + dz*dz)
    rl.DrawText(fmt.ctprintf("%3.0f m", dist), rx_base, py + 32, 36, COL_WHITE)
    rl.DrawText("ROUND", rx_base, py + 80, 16, COL_DIM)
    for k in 0..<ROUND_WIN {
        cxk := rx_base + 80 + i32(k) * 30
        cyk := py + 84
        col := i32(k) < t.rounds_won ? COL_GREEN : COL_DIM
        if i32(k) >= t.rounds_won do col.a = 90
        rl.DrawRectangle(cxk, cyk, 22, 22, col)
        rl.DrawRectangleLines(cxk, cyk, 22, 22, COL_WHITE)
    }

    // ── 3D viewport reticle: centered, no pitch offset.
    // The camera already pitches with the barrel so the crosshair is just
    // "where the camera points." Real shell impact depends on charge & gravity,
    // so this is a sight reference, not a hit predictor.
    view_h : i32 = i32(VH) - HUD_H
    ccx := i32(VW)/2
    ccy := view_h/2
    rl.DrawLineEx(Vec2{f32(ccx) - 22, f32(ccy)}, Vec2{f32(ccx) - 8, f32(ccy)}, 2, COL_WHITE)
    rl.DrawLineEx(Vec2{f32(ccx) + 8,  f32(ccy)}, Vec2{f32(ccx) + 22, f32(ccy)}, 2, COL_WHITE)
    rl.DrawLineEx(Vec2{f32(ccx), f32(ccy) - 22}, Vec2{f32(ccx), f32(ccy) - 8}, 2, COL_WHITE)
    rl.DrawLineEx(Vec2{f32(ccx), f32(ccy) + 8},  Vec2{f32(ccx), f32(ccy) + 22}, 2, COL_WHITE)
    rl.DrawCircleLines(ccx, ccy, 24, fade_color(COL_WHITE, 0.35))
    rl.DrawPixel(ccx, ccy, COL_WHITE)

    // ── Pre-round countdown (large, centered in view area) ──
    if st.mode == .Playing && st.round_start_t > 0 {
        n := i32(math.ceil(st.round_start_t))
        msg := fmt.ctprintf("%d", n)
        mw := rl.MeasureText(msg, 180)
        rl.DrawText(msg, i32(VW)/2 - mw/2, ccy - 90, 180, fade_color(COL_WHITE, 0.85))
    }

    // ── Hit indicator (last hit direction) ──
    if t.hit_flash > 0 {
        ang := t.last_hit_dir
        rr : f32 = 90
        ix := f32(ccx) + math.sin(ang) * rr
        iy := f32(ccy) - math.cos(ang) * rr
        rl.DrawCircleLines(i32(ix), i32(iy), 18, fade_color(COL_RED, t.hit_flash * 1.5))
    }

    // ── Quit hold ──
    if t.quit_hold > 0.1 {
        frac := clampf(t.quit_hold / QUIT_HOLD, 0, 1)
        bx := i32(VW)/2 - 220
        by := py - 36
        rl.DrawRectangle(bx-2, by-2, 444, 28, COL_HUDBG)
        rl.DrawRectangle(bx, by, i32(440 * frac), 24, COL_RED)
        rl.DrawText("HOLD ALL 4 BUTTONS TO QUIT", bx + 60, by + 2, 20, COL_WHITE)
    }
}

// ── Frame composition ──────────────────────────────────────────────────────
draw_frame :: proc() {
    rl.BeginDrawing()
    rl.ClearBackground(rl.BLACK)
    // composite the two render textures side by side (flip Y because RT is upside-down)
    src0 := rl.Rectangle{0, 0, f32(VW), -f32(VH)}
    src1 := rl.Rectangle{0, 0, f32(VW), -f32(VH)}
    // Top half = P1, bottom half = P2.
    dst0 := rl.Rectangle{0, 0,       f32(VW), f32(VH)}
    dst1 := rl.Rectangle{0, f32(VH), f32(VW), f32(VH)}
    rl.DrawTexturePro(st.rt[0].texture, src0, dst0, Vec2{0, 0}, 0, rl.WHITE)
    rl.DrawTexturePro(st.rt[1].texture, src1, dst1, Vec2{0, 0}, 0, rl.WHITE)
    // horizontal divider between the two views
    rl.DrawRectangle(0, VH - 2, W, 4, rl.Color{0, 0, 0, 255})
    rl.DrawRectangle(0, VH - 1, W, 2, rl.Color{120, 120, 130, 255})

    // overlay: round-over / match-over banner (drawn on top of both viewports)
    if st.mode == .Round_Over || st.mode == .Match_Over {
        rl.DrawRectangle(0, 0, W, H, rl.Color{0, 0, 0, 140})
        winner := st.tanks[0].rounds_won > st.tanks[1].rounds_won ? 0 : 1
        if st.tanks[0].rounds_won == st.tanks[1].rounds_won {
            winner = -1
        }
        if st.mode == .Round_Over {
            t1 := fmt.ctprintf("ROUND %d", st.cur_round)
            t1w := rl.MeasureText(t1, 80)
            rl.DrawText(t1, W/2 - t1w/2, 280, 80, COL_DIM)
            // last-round winner = whichever still has hp
            last_w := st.tanks[0].alive ? 0 : 1
            sub := fmt.ctprintf("P%d WINS THE ROUND", last_w + 1)
            sw := rl.MeasureText(sub, 100)
            rl.DrawText(sub, W/2 - sw/2, 400, 100, P_TINT[last_w])
            score := fmt.ctprintf("%d  -  %d", st.tanks[0].rounds_won, st.tanks[1].rounds_won)
            sw2 := rl.MeasureText(score, 80)
            rl.DrawText(score, W/2 - sw2/2, 560, 80, COL_WHITE)
            hint := cstring("next round starts shortly")
            hw := rl.MeasureText(hint, 32)
            rl.DrawText(hint, W/2 - hw/2, 720, 32, COL_DIM)
        } else {
            t1 := cstring("MATCH OVER")
            t1w := rl.MeasureText(t1, 100)
            rl.DrawText(t1, W/2 - t1w/2, 240, 100, COL_WHITE)
            sub := fmt.ctprintf("P%d  WINS  THE  MATCH", winner + 1)
            sw := rl.MeasureText(sub, 90)
            rl.DrawText(sub, W/2 - sw/2, 400, 90, P_TINT[winner])
            score := fmt.ctprintf("%d  -  %d", st.tanks[0].rounds_won, st.tanks[1].rounds_won)
            sw2 := rl.MeasureText(score, 70)
            rl.DrawText(score, W/2 - sw2/2, 560, 70, COL_DIM)
            hint := cstring("press FIRE to start a new match  ·  hold all 4 buttons to quit")
            hw := rl.MeasureText(hint, 28)
            rl.DrawText(hint, W/2 - hw/2, 720, 28, COL_DIM)
        }
    }

    if st.mode == .Title do draw_title()

    rl.EndDrawing()
}

// ── Title screen ───────────────────────────────────────────────────────────
draw_title :: proc() {
    rl.ClearBackground(rl.Color{12, 14, 22, 255})
    // small skyline silhouette using terrain noise
    for x in 0..<W/4 {
        wx := f32(x) * 4.0 - 800
        h := heightfn(wx, 0)
        h_px := i32(h * 18)
        rl.DrawRectangle(i32(x) * 4, H - 200 - h_px, 4, 200 + h_px, rl.Color{40, 45, 60, 255})
    }
    title := cstring("B R E A C H")
    tw := rl.MeasureText(title, 180)
    rl.DrawText(title, W/2 - tw/2, 180, 180, COL_WHITE)
    sub := cstring("a tank duel for two")
    sw := rl.MeasureText(sub, 40)
    rl.DrawText(sub, W/2 - sw/2, 380, 40, COL_DIM)

    // controls panel
    panel := [?]cstring{
        "EACH PLAYER OPERATES TWO ADJACENT STATIONS",
        "",
        "LEFT  STICK  Y   left tread fwd / back",
        "LEFT  STICK  X   barrel pitch (elevation)",
        "RIGHT STICK  Y   right tread fwd / back",
        "RIGHT STICK  X   turret yaw (azimuth)",
        "",
        "LEFT  JUMP    load shell",
        "LEFT  ATTACK  load powder  (1 - 3 charges = more range)",
        "RIGHT JUMP    breach toggle  (open / close)",
        "RIGHT ATTACK  FIRE",
        "",
        "ARMOR :  5 front  ·  3 side  ·  1 rear",
        "FIRST TO 3 ROUND WINS TAKES THE MATCH",
    }
    px := i32(W)/2 - 360
    py := i32(500)
    for line, i in panel {
        rl.DrawText(line, px, py + i32(i) * 30, 22, COL_WHITE)
    }
    hint := cstring("press FIRE (right ATTACK) on either pair to begin")
    hw := rl.MeasureText(hint, 28)
    rl.DrawText(hint, W/2 - hw/2, H - 90, 28, P_TINT[0])
}

// ── Main loop tick ─────────────────────────────────────────────────────────
update_title :: proc(dt: f32) {
    // any player's FIRE (right ATTACK = station 1 or 3) begins a match
    if rl.IsKeyPressed(KEYS_ATK[1]) || rl.IsKeyPressed(KEYS_ATK[3]) {
        start_match()
    }
    if rl.IsKeyDown(KEYS_JUMP[0]) && rl.IsKeyDown(KEYS_ATK[0]) &&
       rl.IsKeyDown(KEYS_JUMP[1]) && rl.IsKeyDown(KEYS_ATK[1]) {
        st.quit_hold_global += dt
    } else if rl.IsKeyDown(KEYS_JUMP[2]) && rl.IsKeyDown(KEYS_ATK[2]) &&
              rl.IsKeyDown(KEYS_JUMP[3]) && rl.IsKeyDown(KEYS_ATK[3]) {
        st.quit_hold_global += dt
    } else {
        st.quit_hold_global = 0
    }
    if st.quit_hold_global >= QUIT_HOLD {
        rl.CloseWindow()
        os.exit(0)
    }
}

update_play :: proc(dt: f32) {
    if st.round_start_t > 0 {
        st.round_start_t -= dt
        // freeze updates but allow turret/aim?
        for i in 0..<2 do update_tank(&st.tanks[i], i, dt * 0.3)
        update_shells(dt)
        return
    }
    st.round_t += dt
    for i in 0..<2 do update_tank(&st.tanks[i], i, dt)
    update_shells(dt)

    // round end?
    alive_count := 0
    for i in 0..<2 do if st.tanks[i].alive do alive_count += 1
    if alive_count <= 1 {
        // award round
        winner := -1
        if st.tanks[0].alive do winner = 0
        if st.tanks[1].alive do winner = 1
        if winner >= 0 do st.tanks[winner].rounds_won += 1
        st.intermission = 3.0
        if st.tanks[0].rounds_won >= ROUND_WIN || st.tanks[1].rounds_won >= ROUND_WIN {
            st.mode = .Match_Over
        } else {
            st.mode = .Round_Over
        }
    }

    // quit (per-player: all 4 buttons of either pair held)
    quit := false
    if st.tanks[0].quit_hold >= QUIT_HOLD || st.tanks[1].quit_hold >= QUIT_HOLD {
        quit = true
    }
    if quit {
        st.mode = .Title
        st.tanks[0].quit_hold = 0
        st.tanks[1].quit_hold = 0
        st.quit_hold_global = 0
    }
}

update_round_over :: proc(dt: f32) {
    // tick world a bit so smoke/etc. animate, but no scoring
    for i in 0..<2 do update_tank(&st.tanks[i], i, dt * 0.4)
    update_shells(dt)
    st.intermission -= dt
    if st.intermission <= 0 {
        st.cur_round += 1
        start_round()
    }
    if st.tanks[0].quit_hold >= QUIT_HOLD || st.tanks[1].quit_hold >= QUIT_HOLD {
        st.mode = .Title
        st.tanks[0].quit_hold = 0
        st.tanks[1].quit_hold = 0
    }
}

update_match_over :: proc(dt: f32) {
    for i in 0..<2 do update_tank(&st.tanks[i], i, dt * 0.3)
    update_shells(dt)
    // any FIRE begins a new match
    if rl.IsKeyPressed(KEYS_ATK[1]) || rl.IsKeyPressed(KEYS_ATK[3]) {
        start_match()
    }
    if st.tanks[0].quit_hold >= QUIT_HOLD || st.tanks[1].quit_hold >= QUIT_HOLD {
        st.mode = .Title
        st.tanks[0].quit_hold = 0
        st.tanks[1].quit_hold = 0
    }
}

// ── main ───────────────────────────────────────────────────────────────────
main :: proc() {
    rl.SetConfigFlags({.MSAA_4X_HINT, .VSYNC_HINT, .FULLSCREEN_MODE})
    rl.InitWindow(W, H, "Breach")
    rl.SetTargetFPS(60)
    rl.SetExitKey(.KEY_NULL)
    rl.HideCursor()
    init_audio()

    st.cube_mesh = rl.GenMeshCube(1, 1, 1)
    st.cube_mat  = rl.LoadMaterialDefault()
    build_terrain()
    gen_obstacles()
    for i in 0..<2 {
        st.rt[i] = rl.LoadRenderTexture(VW, VH)
        rl.SetTextureFilter(st.rt[i].texture, .BILINEAR)
    }
    st.mode = .Title

    defer {
        if st.audio_ok {
            rl.UnloadSound(st.snd_load)
            rl.UnloadSound(st.snd_powder)
            rl.UnloadSound(st.snd_breach)
            rl.UnloadSound(st.snd_fire)
            rl.UnloadSound(st.snd_hit)
            rl.UnloadSound(st.snd_clank)
            rl.UnloadSound(st.snd_dud)
            rl.UnloadSound(st.snd_explode)
            rl.CloseAudioDevice()
        }
        for i in 0..<2 do rl.UnloadRenderTexture(st.rt[i])
        rl.UnloadModel(st.terrain_model)
        rl.CloseWindow()
    }

    for !rl.WindowShouldClose() {
        dt := rl.GetFrameTime()
        if dt > 0.05 do dt = 0.05
        st.time_total += dt

        switch st.mode {
        case .Title:       update_title(dt)
        case .Playing:     update_play(dt)
        case .Round_Over:  update_round_over(dt)
        case .Match_Over:  update_match_over(dt)
        }

        if st.mode != .Title {
            for i in 0..<2 do render_player_view(i)
        }
        draw_frame()

        free_all(context.temp_allocator)
    }
}
