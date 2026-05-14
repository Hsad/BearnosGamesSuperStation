package lodestar

// LODESTAR — magnetic-field arena for 1-4 players on the cabinet.
//
// Each player is a "lodestar": a tiny ship that emits a magnetic field over
// a cloud of iron shards. Move with stick, HOLD JUMP to flip from attract to
// repel, tap ATTACK for a radial pulse. Knock charged shards into opponents
// to score.
//
// Build: launch.sh handles it. Single file by design.

import rl "vendor:raylib"
import "core:math"
import "core:math/rand"
import "core:fmt"
import "core:os"
import "core:strings"
import "core:strconv"
import "core:c"

// ── Window / arena ──────────────────────────────────────────────────────────
W :: 1920
H :: 1080

ARENA_LEFT   : f32 :  100
ARENA_RIGHT  : f32 : 1820
ARENA_TOP    : f32 :  130   // 30px bezel + 100px HUD
ARENA_BOTTOM : f32 : 1050

MAX_PLAYERS  :: 4

// ── Physics ─────────────────────────────────────────────────────────────────
PLAYER_R          : f32 :  22.0
PLAYER_THRUST     : f32 : 1400.0
PLAYER_DAMP       : f32 :    2.4
PLAYER_MAX_V      : f32 :  620.0

// Field force on a shard from one player: F = pol * K / (r^2 + r0^2), direction
// toward (attract) or away (repel) from player. r0 keeps the singularity tame.
// Tuned so close-range coupling is strong (tight orbits, sharp flings on flip)
// but force tails off fast with distance — positioning matters.
FIELD_K           : f32 : 900000.0
FIELD_R0          : f32 :    35.0
FIELD_MAX_REACH   : f32 :   650.0
FIELD_F_CAP       : f32 :  3400.0

// Player-on-player magnetic force (weaker than on shards, otherwise the arena
// devolves to a bowling game and stops feeling like control).
P2P_K             : f32 : 140000.0
P2P_R0            : f32 :   90.0
P2P_F_CAP         : f32 :  1200.0
P2P_REACH         : f32 :  500.0

SHARD_R           : f32 :    7.0
SHARD_DAMP        : f32 :    0.18   // light damping — momentum lingers
SHARD_BOUNCE      : f32 :    0.78
SHARD_MAX_V       : f32 : 1500.0
SHARD_HIT_V       : f32 :  230.0   // below this a shard touches you, doesn't hurt

PULSE_RADIUS      : f32 :  360.0
PULSE_IMPULSE     : f32 :  1100.0   // applied at radius 0; falls off linearly
PULSE_P2P_IMPULSE : f32 :  420.0
PULSE_CD          : f32 :    2.4
PULSE_DUR         : f32 :    0.35  // visible ring duration

SHARD_COUNT       :: 42

ROUND_DURATION    : f32 :  90.0
RESPAWN_T         : f32 :   1.8
HIT_INVULN        : f32 :   0.7

QUIT_HOLD         : f32 :   1.0

// ── Solo mode ───────────────────────────────────────────────────────────────
SOLO_TARGET_HP    : f32 :   3.5    // hp drained by total impact energy
SOLO_TARGET_MAX   :: 5
SOLO_SPAWN_T_MIN  : f32 :   1.6
SOLO_SPAWN_T_MAX  : f32 :   3.2

// ── Colors ──────────────────────────────────────────────────────────────────
COL_BG       := rl.Color{  9,  10,  22, 255}
COL_BG2      := rl.Color{ 18,  20,  36, 255}
COL_GRID     := rl.Color{ 28,  34,  60, 255}
COL_WALL     := rl.Color{ 60,  72, 120, 255}
COL_WALL_HI  := rl.Color{120, 145, 220, 255}
COL_SHARD    := rl.Color{210, 220, 240, 255}
COL_SHARD_DK := rl.Color{120, 130, 160, 200}
COL_WHITE    := rl.Color{245, 245, 250, 255}
COL_DIM      := rl.Color{140, 150, 180, 255}
COL_HUDBG    := rl.Color{  6,   8,  18, 220}

// One per player slot.
P_COLORS := [MAX_PLAYERS]rl.Color{
    rl.Color{ 90, 220, 255, 255},   // P1 cyan
    rl.Color{255, 140, 100, 255},   // P2 amber
    rl.Color{180, 255, 130, 255},   // P3 lime
    rl.Color{240, 130, 240, 255},   // P4 magenta
}
P_COLORS_DIM := [MAX_PLAYERS]rl.Color{
    rl.Color{ 40, 110, 140, 255},
    rl.Color{140,  80,  55, 255},
    rl.Color{ 95, 140,  70, 255},
    rl.Color{130,  70, 130, 255},
}

// ── Input mappings (must mirror config/controllers.json) ────────────────────
KEYS_LEFT  := [?]rl.KeyboardKey{.LEFT, .D, .J, .V}
KEYS_RIGHT := [?]rl.KeyboardKey{.RIGHT, .G, .L, .U}
KEYS_UP    := [?]rl.KeyboardKey{.UP, .R, .I, .Y}
KEYS_DOWN  := [?]rl.KeyboardKey{.DOWN, .F, .K, .N}
KEYS_JUMP  := [?]rl.KeyboardKey{.LEFT_CONTROL, .A, .RIGHT_CONTROL, .B}
KEYS_ATK   := [?]rl.KeyboardKey{.LEFT_ALT,     .S, .RIGHT_SHIFT,    .E}

// ── Types ───────────────────────────────────────────────────────────────────
Vec2 :: rl.Vector2

Player :: struct {
    active:       bool,    // joined this match
    alive:        bool,    // not in respawn limbo
    pos:          Vec2,
    vel:          Vec2,
    repel:        bool,    // JUMP held → repel mode
    pulse_cd:     f32,
    pulse_ring:   f32,     // visible expanding pulse timer
    respawn_t:    f32,
    invuln_t:     f32,
    score:        i32,
    hit_flash:    f32,
    quit_hold:    f32,
    last_polarity_t: f32,  // for visual lerp on flip
    halo_phase:   f32,
}

Shard :: struct {
    pos:    Vec2,
    vel:    Vec2,
    // last player whose force significantly accelerated this shard. -1 = none.
    owner:  i32,
    owner_t: f32, // time since owner was tagged
    trail:  [6]Vec2,
    trail_n: i32,
    energy_glow: f32,
}

Target :: struct {
    pos:  Vec2,
    hp:   f32,
    max_hp: f32,
    pulse: f32,
}

Particle :: struct {
    pos: Vec2,
    vel: Vec2,
    life: f32,
    max_life: f32,
    color: rl.Color,
    size: f32,
}

Mode :: enum {
    Menu_Mode_Select,
    Menu_Join,
    Playing,
    Game_Over,
}

GameMode :: enum {
    Solo,
    Versus,
}

State :: struct {
    mode:       Mode,
    game_mode:  GameMode,
    players:    [MAX_PLAYERS]Player,
    shards:     [SHARD_COUNT]Shard,
    targets:    [SOLO_TARGET_MAX]Target,
    target_used:[SOLO_TARGET_MAX]bool,
    particles:  [256]Particle,
    pcount:     int,
    round_t:    f32,
    time_total: f32,
    solo_spawn_t: f32,
    solo_score:  i32,
    quit_hold_global: f32,
    winners:    [MAX_PLAYERS]i32,
    win_count:  i32,
    high_winner: i32,

    // audio
    snd_pulse:  rl.Sound,
    snd_flip:   rl.Sound,
    snd_hit:    rl.Sound,
    snd_score:  rl.Sound,
    snd_spawn:  rl.Sound,
    audio_ok:   bool,
}

st: State

// ── Helpers ─────────────────────────────────────────────────────────────────
v2 :: proc(x, y: f32) -> Vec2 { return Vec2{x, y} }
v2_len :: proc(v: Vec2) -> f32 { return math.sqrt(v.x*v.x + v.y*v.y) }
v2_len2 :: proc(v: Vec2) -> f32 { return v.x*v.x + v.y*v.y }
v2_norm :: proc(v: Vec2) -> Vec2 {
    l := v2_len(v)
    if l < 0.0001 do return v2(0, 0)
    return v2(v.x/l, v.y/l)
}
clampf :: proc(x, a, b: f32) -> f32 {
    if x < a do return a
    if x > b do return b
    return x
}
lerpf :: proc(a, b, t: f32) -> f32 { return a + (b - a) * t }
lerpc :: proc(a, b: rl.Color, t: f32) -> rl.Color {
    return rl.Color{
        u8(lerpf(f32(a.r), f32(b.r), t)),
        u8(lerpf(f32(a.g), f32(b.g), t)),
        u8(lerpf(f32(a.b), f32(b.b), t)),
        u8(lerpf(f32(a.a), f32(b.a), t)),
    }
}
fade_color :: proc(c: rl.Color, a: f32) -> rl.Color {
    return rl.Color{c.r, c.g, c.b, u8(clampf(a, 0, 1) * 255)}
}
rand_f :: proc(a, b: f32) -> f32 { return a + rand.float32() * (b - a) }
rand_in_arena :: proc() -> Vec2 {
    return v2(rand_f(ARENA_LEFT+40, ARENA_RIGHT-40), rand_f(ARENA_TOP+40, ARENA_BOTTOM-40))
}

// ── Audio synthesis ─────────────────────────────────────────────────────────
// Each "sound" is built as a 16-bit mono PCM buffer at 22050 Hz, loaded as a
// Wave and converted to a Sound. raylib copies the wave data on load, so the
// local buffer can be released after.
SR :: 22050

synth :: proc(dur_s: f32, gen: proc(t: f32, i: int) -> f32) -> rl.Sound {
    frames := int(f32(SR) * dur_s)
    buf := make([]i16, frames)
    defer delete(buf)
    for i in 0..<frames {
        t := f32(i) / f32(SR)
        s := gen(t, i)
        s = clampf(s, -1, 1)
        buf[i] = i16(s * 32000)
    }
    w := rl.Wave{
        frameCount = c.uint(frames),
        sampleRate = c.uint(SR),
        sampleSize = 16,
        channels   = 1,
        data       = raw_data(buf),
    }
    snd := rl.LoadSoundFromWave(w)
    return snd
}

// envelope helpers
env_ad :: proc(t, dur, attack: f32) -> f32 {
    if t < attack do return t / max(attack, 0.0001)
    return clampf(1.0 - (t - attack) / max(dur - attack, 0.0001), 0, 1)
}

gen_pulse :: proc(t: f32, i: int) -> f32 {
    // descending sine from 220→60 Hz with noise grit
    dur :: f32(0.55)
    if t >= dur do return 0
    freq := lerpf(220, 60, t / dur)
    phase := freq * t * 2 * math.PI
    s := math.sin(phase) * 0.7
    s += (rand.float32() * 2 - 1) * 0.25 * (1 - t/dur)
    return s * env_ad(t, dur, 0.005) * 0.85
}

gen_flip :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.10)
    if t >= dur do return 0
    s := math.sin(t * 2 * math.PI * 880)
    s += math.sin(t * 2 * math.PI * 1320) * 0.5
    return s * env_ad(t, dur, 0.002) * 0.4
}

gen_hit :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.22)
    if t >= dur do return 0
    freq := lerpf(1400, 350, t/dur)
    s := math.sin(t * 2 * math.PI * freq)
    s += (rand.float32() * 2 - 1) * 0.4
    return s * env_ad(t, dur, 0.003) * 0.7
}

gen_score :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.35)
    if t >= dur do return 0
    f1 := f32(660)
    f2 := f32(990)
    s := math.sin(t * 2 * math.PI * f1) * 0.5
    s += math.sin(t * 2 * math.PI * f2) * 0.4
    return s * env_ad(t, dur, 0.01) * 0.55
}

gen_spawn :: proc(t: f32, i: int) -> f32 {
    dur :: f32(0.30)
    if t >= dur do return 0
    freq := lerpf(80, 320, t/dur)
    s := math.sin(t * 2 * math.PI * freq)
    return s * env_ad(t, dur, 0.02) * 0.45
}

init_audio :: proc() {
    rl.InitAudioDevice()
    if !rl.IsAudioDeviceReady() {
        st.audio_ok = false
        return
    }
    st.audio_ok = true
    st.snd_pulse = synth(0.55, gen_pulse)
    st.snd_flip  = synth(0.10, gen_flip)
    st.snd_hit   = synth(0.22, gen_hit)
    st.snd_score = synth(0.35, gen_score)
    st.snd_spawn = synth(0.30, gen_spawn)
}

play :: proc(s: rl.Sound, pitch: f32 = 1.0, vol: f32 = 1.0) {
    if !st.audio_ok do return
    rl.SetSoundPitch(s, pitch)
    rl.SetSoundVolume(s, vol)
    rl.PlaySound(s)
}

// ── Particles ───────────────────────────────────────────────────────────────
spawn_particle :: proc(pos, vel: Vec2, color: rl.Color, life: f32, size: f32) {
    if st.pcount >= len(st.particles) {
        // overwrite oldest by rotating: shift first out
        for i in 0..<len(st.particles)-1 {
            st.particles[i] = st.particles[i+1]
        }
        st.pcount = len(st.particles) - 1
    }
    st.particles[st.pcount] = Particle{
        pos = pos, vel = vel, life = life, max_life = life,
        color = color, size = size,
    }
    st.pcount += 1
}

burst :: proc(pos: Vec2, color: rl.Color, n: int, speed: f32, life: f32, size: f32 = 3.5) {
    for _ in 0..<n {
        a := rand_f(0, 2 * math.PI)
        sp := rand_f(speed * 0.4, speed)
        spawn_particle(pos, v2(math.cos(a)*sp, math.sin(a)*sp), color, life, size)
    }
}

update_particles :: proc(dt: f32) {
    i := 0
    for i < st.pcount {
        p := &st.particles[i]
        p.life -= dt
        if p.life <= 0 {
            st.particles[i] = st.particles[st.pcount-1]
            st.pcount -= 1
            continue
        }
        p.pos.x += p.vel.x * dt
        p.pos.y += p.vel.y * dt
        p.vel.x *= math.exp(-1.5 * dt)
        p.vel.y *= math.exp(-1.5 * dt)
        i += 1
    }
}

// ── Input ───────────────────────────────────────────────────────────────────
read_stick :: proc(slot: int) -> Vec2 {
    x: f32 = 0
    y: f32 = 0
    if rl.IsKeyDown(KEYS_LEFT[slot])  do x -= 1
    if rl.IsKeyDown(KEYS_RIGHT[slot]) do x += 1
    if rl.IsKeyDown(KEYS_UP[slot])    do y -= 1
    if rl.IsKeyDown(KEYS_DOWN[slot])  do y += 1
    if x != 0 && y != 0 {
        x *= 0.7071
        y *= 0.7071
    }
    return v2(x, y)
}

both_held :: proc(slot: int) -> bool {
    return rl.IsKeyDown(KEYS_JUMP[slot]) && rl.IsKeyDown(KEYS_ATK[slot])
}

any_both_held :: proc() -> bool {
    for i in 0..<MAX_PLAYERS {
        if both_held(i) do return true
    }
    return false
}

// ── Game setup ──────────────────────────────────────────────────────────────
respawn_player :: proc(p: ^Player, slot: int) {
    // Place in a corner-ish spot based on slot
    spots := [4]Vec2{
        v2(ARENA_LEFT  + 200, ARENA_TOP    + 200),
        v2(ARENA_RIGHT - 200, ARENA_BOTTOM - 200),
        v2(ARENA_RIGHT - 200, ARENA_TOP    + 200),
        v2(ARENA_LEFT  + 200, ARENA_BOTTOM - 200),
    }
    p.pos = spots[slot]
    p.vel = v2(0, 0)
    p.repel = false
    p.alive = true
    p.invuln_t = HIT_INVULN
    p.hit_flash = 0
}

reset_shards :: proc() {
    for i in 0..<SHARD_COUNT {
        s := &st.shards[i]
        s.pos = rand_in_arena()
        a := rand_f(0, 2 * math.PI)
        sp := rand_f(40, 120)
        s.vel = v2(math.cos(a)*sp, math.sin(a)*sp)
        s.owner = -1
        s.owner_t = 0
        s.trail_n = 0
        for j in 0..<len(s.trail) do s.trail[j] = s.pos
        s.energy_glow = 0
    }
}

start_round :: proc() {
    st.mode = .Playing
    st.round_t = ROUND_DURATION
    st.solo_score = 0
    st.solo_spawn_t = 0.4
    for i in 0..<MAX_PLAYERS {
        p := &st.players[i]
        if p.active {
            p.score = 0
            respawn_player(p, i)
        }
    }
    for i in 0..<SOLO_TARGET_MAX do st.target_used[i] = false
    reset_shards()
    st.pcount = 0
    st.win_count = 0
    play(st.snd_spawn, 0.9, 0.6)
}

go_to_join :: proc() {
    st.mode = .Menu_Join
    for i in 0..<MAX_PLAYERS {
        st.players[i].active = false
        st.players[i].score = 0
    }
}

// ── Physics step ────────────────────────────────────────────────────────────
clamp_speed :: proc(v: Vec2, m: f32) -> Vec2 {
    l := v2_len(v)
    if l > m do return v2(v.x/l * m, v.y/l * m)
    return v
}

apply_pulse :: proc(p: ^Player, slot: int) {
    p.pulse_cd = PULSE_CD
    p.pulse_ring = PULSE_DUR
    // Push shards and other players radially
    for i in 0..<SHARD_COUNT {
        s := &st.shards[i]
        d := v2(s.pos.x - p.pos.x, s.pos.y - p.pos.y)
        r := v2_len(d)
        if r < PULSE_RADIUS && r > 0.1 {
            falloff := 1.0 - r / PULSE_RADIUS
            imp := PULSE_IMPULSE * falloff
            n := v2(d.x/r, d.y/r)
            s.vel.x += n.x * imp
            s.vel.y += n.y * imp
            s.owner = i32(slot)
            s.owner_t = 0
            s.energy_glow = max(s.energy_glow, 0.8)
        }
    }
    for i in 0..<MAX_PLAYERS {
        if i == slot do continue
        o := &st.players[i]
        if !o.active || !o.alive do continue
        d := v2(o.pos.x - p.pos.x, o.pos.y - p.pos.y)
        r := v2_len(d)
        if r < PULSE_RADIUS && r > 0.1 {
            falloff := 1.0 - r / PULSE_RADIUS
            imp := PULSE_P2P_IMPULSE * falloff
            n := v2(d.x/r, d.y/r)
            o.vel.x += n.x * imp
            o.vel.y += n.y * imp
        }
    }
    // visual burst
    burst(p.pos, P_COLORS[slot], 24, 380, 0.55, 3.0)
    play(st.snd_pulse, rand_f(0.92, 1.08), 0.9)
}

step_players :: proc(dt: f32) {
    for i in 0..<MAX_PLAYERS {
        p := &st.players[i]
        if !p.active do continue
        p.pulse_cd = max(0, p.pulse_cd - dt)
        p.pulse_ring = max(0, p.pulse_ring - dt)
        p.invuln_t = max(0, p.invuln_t - dt)
        p.hit_flash = max(0, p.hit_flash - dt)
        p.halo_phase += dt
        if both_held(i) {
            p.quit_hold += dt
        } else {
            p.quit_hold = 0
        }
        if !p.alive {
            p.respawn_t -= dt
            if p.respawn_t <= 0 do respawn_player(p, i)
            continue
        }
        // polarity (HOLD JUMP = repel)
        new_repel := rl.IsKeyDown(KEYS_JUMP[i])
        if new_repel != p.repel {
            p.last_polarity_t = 0
            play(st.snd_flip, new_repel ? 0.85 : 1.15, 0.45)
        }
        p.repel = new_repel
        p.last_polarity_t += dt

        // pulse
        if rl.IsKeyPressed(KEYS_ATK[i]) && p.pulse_cd <= 0 {
            apply_pulse(p, i)
        }
        // thrust
        stk := read_stick(i)
        p.vel.x += stk.x * PLAYER_THRUST * dt
        p.vel.y += stk.y * PLAYER_THRUST * dt
        // damping
        damp := math.exp(-PLAYER_DAMP * dt)
        p.vel.x *= damp
        p.vel.y *= damp
        p.vel = clamp_speed(p.vel, PLAYER_MAX_V)
        p.pos.x += p.vel.x * dt
        p.pos.y += p.vel.y * dt
        // arena walls
        if p.pos.x < ARENA_LEFT  + PLAYER_R { p.pos.x = ARENA_LEFT  + PLAYER_R; p.vel.x = abs(p.vel.x) * 0.6 }
        if p.pos.x > ARENA_RIGHT - PLAYER_R { p.pos.x = ARENA_RIGHT - PLAYER_R; p.vel.x = -abs(p.vel.x) * 0.6 }
        if p.pos.y < ARENA_TOP    + PLAYER_R { p.pos.y = ARENA_TOP    + PLAYER_R; p.vel.y = abs(p.vel.y) * 0.6 }
        if p.pos.y > ARENA_BOTTOM - PLAYER_R { p.pos.y = ARENA_BOTTOM - PLAYER_R; p.vel.y = -abs(p.vel.y) * 0.6 }
    }
    // player-on-player magnetism
    for i in 0..<MAX_PLAYERS {
        a := &st.players[i]
        if !a.active || !a.alive do continue
        for j in i+1..<MAX_PLAYERS {
            b := &st.players[j]
            if !b.active || !b.alive do continue
            d := v2(b.pos.x - a.pos.x, b.pos.y - a.pos.y)
            r := v2_len(d)
            if r > P2P_REACH || r < 0.1 do continue
            // attract if opposite polarity, repel if same
            same_pol := a.repel == b.repel
            mag := P2P_K / (r*r + P2P_R0*P2P_R0)
            if mag > P2P_F_CAP do mag = P2P_F_CAP
            n := v2(d.x/r, d.y/r)
            sign : f32 = same_pol ? -1.0 : 1.0
            // a feels force toward b if attracting (sign=+1)
            a.vel.x += n.x * mag * sign * dt
            a.vel.y += n.y * mag * sign * dt
            b.vel.x -= n.x * mag * sign * dt
            b.vel.y -= n.y * mag * sign * dt
        }
    }
}

step_shards :: proc(dt: f32) {
    for i in 0..<SHARD_COUNT {
        s := &st.shards[i]
        s.energy_glow = max(0, s.energy_glow - dt * 1.2)
        s.owner_t += dt
        // Sum forces from each active+alive player.
        ax: f32 = 0
        ay: f32 = 0
        strongest_force: f32 = 0
        strongest_owner: i32 = -1
        for j in 0..<MAX_PLAYERS {
            p := &st.players[j]
            if !p.active || !p.alive do continue
            d := v2(p.pos.x - s.pos.x, p.pos.y - s.pos.y)
            r := v2_len(d)
            if r > FIELD_MAX_REACH || r < 0.1 do continue
            mag := FIELD_K / (r*r + FIELD_R0*FIELD_R0)
            if mag > FIELD_F_CAP do mag = FIELD_F_CAP
            n := v2(d.x/r, d.y/r)
            sign : f32 = p.repel ? -1.0 : 1.0
            ax += n.x * mag * sign
            ay += n.y * mag * sign
            if mag > strongest_force {
                strongest_force = mag
                strongest_owner = i32(j)
            }
        }
        // Tag owner only when force is significant (so passive drift doesn't
        // re-assign credit constantly).
        if strongest_force > 220 {
            s.owner = strongest_owner
            s.owner_t = 0
        } else if s.owner_t > 1.2 {
            // ownership lapses after a beat
            s.owner = -1
        }
        s.vel.x += ax * dt
        s.vel.y += ay * dt
        // damping
        damp := math.exp(-SHARD_DAMP * dt)
        s.vel.x *= damp
        s.vel.y *= damp
        s.vel = clamp_speed(s.vel, SHARD_MAX_V)
        s.pos.x += s.vel.x * dt
        s.pos.y += s.vel.y * dt
        // walls
        if s.pos.x < ARENA_LEFT  + SHARD_R { s.pos.x = ARENA_LEFT  + SHARD_R; s.vel.x = -s.vel.x * SHARD_BOUNCE }
        if s.pos.x > ARENA_RIGHT - SHARD_R { s.pos.x = ARENA_RIGHT - SHARD_R; s.vel.x = -s.vel.x * SHARD_BOUNCE }
        if s.pos.y < ARENA_TOP    + SHARD_R { s.pos.y = ARENA_TOP    + SHARD_R; s.vel.y = -s.vel.y * SHARD_BOUNCE }
        if s.pos.y > ARENA_BOTTOM - SHARD_R { s.pos.y = ARENA_BOTTOM - SHARD_R; s.vel.y = -s.vel.y * SHARD_BOUNCE }

        // trail (sample every few frames roughly)
        if int(s.trail_n) % 2 == 0 {
            for j := len(s.trail)-1; j > 0; j -= 1 do s.trail[j] = s.trail[j-1]
            s.trail[0] = s.pos
        }
        s.trail_n += 1

        // collide with players
        speed := v2_len(s.vel)
        for j in 0..<MAX_PLAYERS {
            p := &st.players[j]
            if !p.active || !p.alive do continue
            d := v2(p.pos.x - s.pos.x, p.pos.y - s.pos.y)
            r := v2_len(d)
            if r < PLAYER_R + SHARD_R {
                // resolve overlap by pushing shard back along normal
                n := v2_norm(d)
                push := (PLAYER_R + SHARD_R) - r
                s.pos.x -= n.x * push
                s.pos.y -= n.y * push
                // reflect shard velocity
                vn := s.vel.x*n.x + s.vel.y*n.y
                if vn < 0 {
                    // moving toward player — reflect
                    s.vel.x -= 2 * vn * n.x
                    s.vel.y -= 2 * vn * n.y
                    s.vel.x *= 0.85
                    s.vel.y *= 0.85
                }
                // damage / scoring
                if speed > SHARD_HIT_V && p.invuln_t <= 0 {
                    hit_owner := s.owner
                    if i32(j) != hit_owner {
                        if hit_owner >= 0 && st.players[hit_owner].active {
                            // versus: knock-out + score
                            if st.game_mode == .Versus {
                                st.players[hit_owner].score += 1
                                play(st.snd_score, rand_f(0.95, 1.10), 0.55)
                                burst(p.pos, P_COLORS[hit_owner], 28, 380, 0.45)
                                burst(p.pos, P_COLORS[j], 16, 220, 0.4)
                                // knock victim and respawn
                                p.alive = false
                                p.respawn_t = RESPAWN_T
                            }
                        }
                        play(st.snd_hit, rand_f(0.9, 1.1), 0.75)
                        burst(s.pos, COL_WHITE, 8, 260, 0.25, 2.0)
                        p.hit_flash = 0.3
                        p.invuln_t = HIT_INVULN
                    }
                }
            }
        }

        // collide with solo targets
        if st.game_mode == .Solo && st.mode == .Playing {
            for ti in 0..<SOLO_TARGET_MAX {
                if !st.target_used[ti] do continue
                t := &st.targets[ti]
                d := v2(t.pos.x - s.pos.x, t.pos.y - s.pos.y)
                r := v2_len(d)
                tr : f32 = 28
                if r < tr + SHARD_R {
                    n := v2_norm(d)
                    push := (tr + SHARD_R) - r
                    s.pos.x -= n.x * push
                    s.pos.y -= n.y * push
                    vn := s.vel.x*n.x + s.vel.y*n.y
                    if vn < 0 {
                        s.vel.x -= 2 * vn * n.x
                        s.vel.y -= 2 * vn * n.y
                    }
                    if speed > 60 {
                        dmg := (speed - 60) / 800.0
                        t.hp -= dmg
                        t.pulse = 0.25
                        // award score = energy delivered, attribute to owner if any
                        gain := i32(speed / 25)
                        st.solo_score += gain
                        burst(s.pos, COL_SHARD, 6, 200, 0.2, 2.0)
                        if t.hp <= 0 {
                            burst(t.pos, rl.Color{255, 220, 100, 255}, 32, 380, 0.6, 3.5)
                            play(st.snd_score, rand_f(0.85, 1.05), 0.7)
                            st.target_used[ti] = false
                            st.solo_score += 200
                        }
                    }
                }
            }
        }
    }
}

step_solo :: proc(dt: f32) {
    if st.game_mode != .Solo do return
    if st.mode != .Playing do return
    st.solo_spawn_t -= dt
    if st.solo_spawn_t <= 0 {
        // spawn into a free slot
        for i in 0..<SOLO_TARGET_MAX {
            if !st.target_used[i] {
                st.target_used[i] = true
                st.targets[i] = Target{
                    pos = rand_in_arena(),
                    hp = SOLO_TARGET_HP,
                    max_hp = SOLO_TARGET_HP,
                    pulse = 0.0,
                }
                play(st.snd_spawn, rand_f(1.0, 1.15), 0.45)
                break
            }
        }
        st.solo_spawn_t = rand_f(SOLO_SPAWN_T_MIN, SOLO_SPAWN_T_MAX)
    }
    for i in 0..<SOLO_TARGET_MAX {
        if !st.target_used[i] do continue
        st.targets[i].pulse = max(0, st.targets[i].pulse - dt)
    }
}

// ── Drawing ─────────────────────────────────────────────────────────────────
draw_arena_bg :: proc() {
    rl.ClearBackground(COL_BG)
    // subtle radial gradient
    rl.DrawRectangleGradientV(0, 0, W, H, COL_BG, COL_BG2)
    // grid inside arena
    gs := f32(80)
    x := ARENA_LEFT
    for x <= ARENA_RIGHT {
        rl.DrawLineV(v2(x, ARENA_TOP), v2(x, ARENA_BOTTOM), COL_GRID)
        x += gs
    }
    y := ARENA_TOP
    for y <= ARENA_BOTTOM {
        rl.DrawLineV(v2(ARENA_LEFT, y), v2(ARENA_RIGHT, y), COL_GRID)
        y += gs
    }
    // walls
    rl.DrawRectangleLinesEx(rl.Rectangle{ARENA_LEFT, ARENA_TOP, ARENA_RIGHT-ARENA_LEFT, ARENA_BOTTOM-ARENA_TOP}, 3, COL_WALL)
    // corner accents
    cn := f32(40)
    rl.DrawLineEx(v2(ARENA_LEFT, ARENA_TOP+cn), v2(ARENA_LEFT, ARENA_TOP), 3, COL_WALL_HI)
    rl.DrawLineEx(v2(ARENA_LEFT, ARENA_TOP), v2(ARENA_LEFT+cn, ARENA_TOP), 3, COL_WALL_HI)
    rl.DrawLineEx(v2(ARENA_RIGHT-cn, ARENA_TOP), v2(ARENA_RIGHT, ARENA_TOP), 3, COL_WALL_HI)
    rl.DrawLineEx(v2(ARENA_RIGHT, ARENA_TOP), v2(ARENA_RIGHT, ARENA_TOP+cn), 3, COL_WALL_HI)
    rl.DrawLineEx(v2(ARENA_LEFT, ARENA_BOTTOM-cn), v2(ARENA_LEFT, ARENA_BOTTOM), 3, COL_WALL_HI)
    rl.DrawLineEx(v2(ARENA_LEFT, ARENA_BOTTOM), v2(ARENA_LEFT+cn, ARENA_BOTTOM), 3, COL_WALL_HI)
    rl.DrawLineEx(v2(ARENA_RIGHT-cn, ARENA_BOTTOM), v2(ARENA_RIGHT, ARENA_BOTTOM), 3, COL_WALL_HI)
    rl.DrawLineEx(v2(ARENA_RIGHT, ARENA_BOTTOM), v2(ARENA_RIGHT, ARENA_BOTTOM-cn), 3, COL_WALL_HI)
}

draw_field_halo :: proc(p: ^Player, slot: int) {
    base := P_COLORS[slot]
    // halo lerps from attract (soft blue tint) to repel (sharp warm tint)
    rings := 4
    inner := PLAYER_R + 6
    spacing : f32 = 14
    for k in 0..<rings {
        rr := inner + f32(k) * spacing + math.sin(p.halo_phase*2 + f32(k)) * 2
        alpha := (0.32 - f32(k)*0.06)
        if p.repel {
            // expanding rings outward — show as bolder, wider
            alpha *= 1.2
            rr += 4
        }
        c := fade_color(base, alpha)
        rl.DrawCircleLinesV(p.pos, rr, c)
    }
    // polarity indicator: a small +/- glyph
    if p.repel {
        rl.DrawLineEx(v2(p.pos.x-7, p.pos.y), v2(p.pos.x+7, p.pos.y), 3, COL_WHITE)
    } else {
        rl.DrawLineEx(v2(p.pos.x-7, p.pos.y), v2(p.pos.x+7, p.pos.y), 3, COL_WHITE)
        rl.DrawLineEx(v2(p.pos.x, p.pos.y-7), v2(p.pos.x, p.pos.y+7), 3, COL_WHITE)
    }
}

draw_player :: proc(p: ^Player, slot: int) {
    if !p.active do return
    if !p.alive {
        // respawn marker
        t := 1.0 - p.respawn_t / RESPAWN_T
        rr := PLAYER_R * (0.4 + t * 0.6)
        rl.DrawCircleLinesV(p.pos, rr, fade_color(P_COLORS[slot], 0.35))
        return
    }
    draw_field_halo(p, slot)
    // body
    rl.DrawCircleV(p.pos, PLAYER_R - 4, P_COLORS_DIM[slot])
    rl.DrawCircleLinesV(p.pos, PLAYER_R, P_COLORS[slot])
    rl.DrawCircleLinesV(p.pos, PLAYER_R - 2, P_COLORS[slot])
    if p.hit_flash > 0 {
        rl.DrawCircleV(p.pos, PLAYER_R + 4, fade_color(rl.Color{255,255,255,255}, p.hit_flash * 0.8))
    }
    // pulse ring (visible while expanding)
    if p.pulse_ring > 0 {
        t := 1.0 - p.pulse_ring / PULSE_DUR
        rr := lerpf(PLAYER_R + 8, PULSE_RADIUS, t)
        a := (1.0 - t) * 0.8
        rl.DrawCircleLinesV(p.pos, rr, fade_color(P_COLORS[slot], a))
        rl.DrawCircleLinesV(p.pos, rr - 2, fade_color(P_COLORS[slot], a * 0.6))
    }
    // pulse cooldown arc (small under body)
    if p.pulse_cd > 0 {
        frac := p.pulse_cd / PULSE_CD
        rl.DrawCircleSectorLines(p.pos, PLAYER_R + 4, -90, -90 + 360 * (1 - frac), 20, fade_color(COL_DIM, 0.6))
    } else {
        // ready indicator: tiny bright dot
        rl.DrawCircleV(v2(p.pos.x, p.pos.y - PLAYER_R - 10), 3, P_COLORS[slot])
    }
}

draw_shards :: proc() {
    for i in 0..<SHARD_COUNT {
        s := &st.shards[i]
        // trail
        for j in 0..<len(s.trail)-1 {
            a := 0.55 * (1.0 - f32(j)/f32(len(s.trail)))
            tc := COL_SHARD
            if s.owner >= 0 {
                tc = lerpc(COL_SHARD, P_COLORS[s.owner], 0.55)
            }
            rl.DrawLineEx(s.trail[j], s.trail[j+1], 2, fade_color(tc, a))
        }
        // body — brighter when fast
        speed := v2_len(s.vel)
        bright := clampf(speed / 600.0, 0.2, 1.0)
        base := COL_SHARD
        if s.owner >= 0 {
            base = lerpc(COL_SHARD, P_COLORS[s.owner], 0.7)
        }
        r := SHARD_R + s.energy_glow * 3
        rl.DrawCircleV(s.pos, r, fade_color(base, bright))
        if speed > SHARD_HIT_V {
            // hot shard halo
            rl.DrawCircleLinesV(s.pos, r + 2, fade_color(base, 0.6))
        }
    }
}

draw_targets :: proc() {
    for i in 0..<SOLO_TARGET_MAX {
        if !st.target_used[i] do continue
        t := &st.targets[i]
        frac := t.hp / t.max_hp
        base := rl.Color{255, 220, 100, 255}
        rl.DrawCircleV(t.pos, 28 + t.pulse * 20, fade_color(base, 0.2))
        rl.DrawCircleV(t.pos, 22, fade_color(base, 0.85))
        rl.DrawCircleV(t.pos, 14, rl.Color{40, 30, 10, 255})
        // hp ring
        rl.DrawCircleSectorLines(t.pos, 26, -90, -90 + 360 * frac, 24, base)
    }
}

draw_particles :: proc() {
    for i in 0..<st.pcount {
        p := st.particles[i]
        a := p.life / p.max_life
        rl.DrawCircleV(p.pos, p.size * (0.4 + a * 0.6), fade_color(p.color, a))
    }
}

draw_hud :: proc() {
    // top bar
    rl.DrawRectangle(0, 0, W, 100, COL_HUDBG)
    rl.DrawLineEx(v2(0, 100), v2(W, 100), 2, COL_WALL)
    // title (small)
    rl.DrawText("LODESTAR", 30, 38, 36, fade_color(COL_WHITE, 0.85))
    // timer center
    secs := i32(math.ceil(st.round_t))
    if secs < 0 do secs = 0
    timer_str := fmt.ctprintf("%02d:%02d", secs/60, secs%60)
    tw := rl.MeasureText(timer_str, 56)
    rl.DrawText(timer_str, W/2 - tw/2, 30, 56, COL_WHITE)
    // per-player score panels
    active_count := 0
    for i in 0..<MAX_PLAYERS do if st.players[i].active do active_count += 1
    if active_count == 0 do return
    panel_w := f32(300)
    gap := f32(20)
    total_w := f32(active_count) * panel_w + f32(active_count - 1) * gap
    start_x := f32(W)/2 - total_w/2
    if st.game_mode == .Solo {
        // single big score panel right
        rl.DrawText(fmt.ctprintf("SCORE  %d", st.solo_score), W - 380, 38, 40, COL_WHITE)
        return
    }
    idx := 0
    for i in 0..<MAX_PLAYERS {
        p := &st.players[i]
        if !p.active do continue
        x := start_x + f32(idx) * (panel_w + gap)
        rl.DrawRectangleRec(rl.Rectangle{x, 105, panel_w, 38}, fade_color(P_COLORS_DIM[i], 0.6))
        rl.DrawRectangleLinesEx(rl.Rectangle{x, 105, panel_w, 38}, 2, P_COLORS[i])
        label := fmt.ctprintf("P%d  %d", i+1, p.score)
        rl.DrawText(label, i32(x) + 14, 110, 28, COL_WHITE)
        // polarity tag
        pol_str : cstring = p.repel ? "REPEL" : "ATTRACT"
        rl.DrawText(pol_str, i32(x) + 160, 114, 22, fade_color(P_COLORS[i], 0.95))
        idx += 1
    }
}

draw_quit_hint :: proc() {
    // global quit (in menus only); during play quit is per-player
    if st.quit_hold_global > 0.05 {
        frac := clampf(st.quit_hold_global / QUIT_HOLD, 0, 1)
        bw := i32(400)
        bh := i32(28)
        bx := i32(W/2) - bw/2
        by := i32(H - 60)
        rl.DrawRectangle(bx-2, by-2, bw+4, bh+4, COL_HUDBG)
        rl.DrawRectangle(bx, by, i32(f32(bw) * frac), bh, rl.Color{220, 80, 60, 255})
        rl.DrawText("HOLD BOTH BUTTONS TO QUIT", bx + 50, by + 4, 20, COL_WHITE)
    }
}

draw_quit_warn_per_player :: proc() {
    // shown bottom-center: list of players currently holding both buttons
    any := false
    for i in 0..<MAX_PLAYERS {
        p := &st.players[i]
        if p.active && p.quit_hold > 0.15 {
            any = true
            break
        }
    }
    if !any do return
    for i in 0..<MAX_PLAYERS {
        p := &st.players[i]
        if !p.active || p.quit_hold <= 0.15 do continue
        frac := clampf(p.quit_hold / QUIT_HOLD, 0, 1)
        bw := i32(360)
        bh := i32(22)
        bx := i32(W/2) - bw/2
        by := i32(H - 50) - i32(i) * 30
        rl.DrawRectangle(bx-2, by-2, bw+4, bh+4, COL_HUDBG)
        rl.DrawRectangle(bx, by, i32(f32(bw) * frac), bh, P_COLORS_DIM[i])
        rl.DrawText(fmt.ctprintf("P%d holding QUIT…", i+1), bx + 100, by + 2, 18, COL_WHITE)
    }
}

// ── Menus ───────────────────────────────────────────────────────────────────
menu_select_cur: int = 0   // 0 = versus, 1 = solo

update_menu_select :: proc(dt: f32) {
    // any player can navigate up/down and confirm with ATTACK
    for i in 0..<MAX_PLAYERS {
        if rl.IsKeyPressed(KEYS_UP[i])   do menu_select_cur = (menu_select_cur + 1) % 2
        if rl.IsKeyPressed(KEYS_DOWN[i]) do menu_select_cur = (menu_select_cur + 1) % 2
        if rl.IsKeyPressed(KEYS_ATK[i]) {
            st.game_mode = menu_select_cur == 0 ? .Versus : .Solo
            if st.game_mode == .Solo {
                // single player slot
                for j in 0..<MAX_PLAYERS do st.players[j].active = false
                st.players[i].active = true
                start_round()
            } else {
                go_to_join()
                st.players[i].active = true   // auto-join the requester
            }
            play(st.snd_score, 1.1, 0.5)
            return
        }
    }
    // global quit hold from menu
    if any_both_held() {
        st.quit_hold_global += dt
        if st.quit_hold_global >= QUIT_HOLD {
            rl.CloseWindow()
            os.exit(0)
        }
    } else {
        st.quit_hold_global = 0
    }
}

update_menu_join :: proc(dt: f32) {
    // each player joins by pressing ATTACK; once 2+ have joined, any joined
    // player can press JUMP to start.
    joined_count := 0
    for i in 0..<MAX_PLAYERS {
        if st.players[i].active {
            joined_count += 1
            // joined players can also press ATTACK to start when ≥2
            if joined_count >= 2 && rl.IsKeyPressed(KEYS_JUMP[i]) {
                start_round()
                return
            }
        } else {
            if rl.IsKeyPressed(KEYS_ATK[i]) {
                st.players[i].active = true
                play(st.snd_flip, 1.2, 0.6)
            }
        }
    }
    if any_both_held() {
        st.quit_hold_global += dt
        if st.quit_hold_global >= QUIT_HOLD {
            // back to mode select
            st.quit_hold_global = 0
            for i in 0..<MAX_PLAYERS do st.players[i].active = false
            st.mode = .Menu_Mode_Select
        }
    } else {
        st.quit_hold_global = 0
    }
}

update_game_over :: proc(dt: f32) {
    for i in 0..<MAX_PLAYERS {
        if rl.IsKeyPressed(KEYS_ATK[i]) {
            st.mode = .Menu_Mode_Select
            for j in 0..<MAX_PLAYERS do st.players[j].active = false
            return
        }
    }
    if any_both_held() {
        st.quit_hold_global += dt
        if st.quit_hold_global >= QUIT_HOLD {
            rl.CloseWindow()
            os.exit(0)
        }
    } else {
        st.quit_hold_global = 0
    }
}

draw_menu_select :: proc() {
    draw_arena_bg()
    title := cstring("L O D E S T A R")
    tw := rl.MeasureText(title, 110)
    rl.DrawText(title, W/2 - tw/2, 200, 110, COL_WHITE)
    sub := cstring("magnetic-field arena")
    sw := rl.MeasureText(sub, 36)
    rl.DrawText(sub, W/2 - sw/2, 330, 36, COL_DIM)

    // mode options
    opts := [2]cstring{"VERSUS  (2 - 4 PLAYERS)", "SOLO  (TARGET PRACTICE)"}
    descs := [2]cstring{
        "Smash charged shards into rivals. 90 seconds. High score wins.",
        "Wreck spawning targets with momentum. Score by impact energy.",
    }
    y0 := i32(500)
    for i in 0..<2 {
        sel := i == menu_select_cur
        c := sel ? COL_WHITE : COL_DIM
        size: i32 = sel ? 56 : 46
        ow := rl.MeasureText(opts[i], size)
        rl.DrawText(opts[i], W/2 - ow/2, y0 + i32(i)*130, size, c)
        if sel {
            dw := rl.MeasureText(descs[i], 26)
            rl.DrawText(descs[i], W/2 - dw/2, y0 + i32(i)*130 + 70, 26, fade_color(COL_WHITE, 0.7))
            // arrows
            rl.DrawText(">", W/2 - ow/2 - 50, y0 + i32(i)*130, size, P_COLORS[0])
            rl.DrawText("<", W/2 + ow/2 + 20, y0 + i32(i)*130, size, P_COLORS[0])
        }
    }
    hint := cstring("UP/DOWN to choose · ATTACK to select · HOLD BOTH = QUIT")
    hw := rl.MeasureText(hint, 24)
    rl.DrawText(hint, W/2 - hw/2, H - 90, 24, fade_color(COL_WHITE, 0.6))
    draw_quit_hint()
}

draw_menu_join :: proc() {
    draw_arena_bg()
    title := cstring("PRESS  ATTACK  TO  JOIN")
    tw := rl.MeasureText(title, 72)
    rl.DrawText(title, W/2 - tw/2, 200, 72, COL_WHITE)

    pw := i32(360)
    gap := i32(40)
    total := pw*4 + gap*3
    sx := i32(W)/2 - total/2
    for i in 0..<MAX_PLAYERS {
        x := sx + i32(i) * (pw + gap)
        y := i32(420)
        col := st.players[i].active ? P_COLORS[i] : fade_color(P_COLORS[i], 0.25)
        rl.DrawRectangleLinesEx(rl.Rectangle{f32(x), f32(y), f32(pw), 260}, 3, col)
        // big P# label
        plabel := fmt.ctprintf("P%d", i+1)
        plw := rl.MeasureText(plabel, 110)
        rl.DrawText(plabel, x + pw/2 - plw/2, y + 30, 110, col)
        status : cstring = st.players[i].active ? "JOINED" : "..."
        sw := rl.MeasureText(status, 36)
        rl.DrawText(status, x + pw/2 - sw/2, y + 180, 36, fade_color(col, 0.85))
    }
    joined := 0
    for i in 0..<MAX_PLAYERS do if st.players[i].active do joined += 1
    if joined >= 2 {
        hint := cstring("ANY JOINED PLAYER: PRESS JUMP TO START")
        hw := rl.MeasureText(hint, 36)
        rl.DrawText(hint, W/2 - hw/2, 740, 36, P_COLORS[0])
    } else {
        hint := cstring("at least 2 players to start")
        hw := rl.MeasureText(hint, 28)
        rl.DrawText(hint, W/2 - hw/2, 740, 28, COL_DIM)
    }
    sub := cstring("HOLD BOTH BUTTONS to go back")
    sw := rl.MeasureText(sub, 22)
    rl.DrawText(sub, W/2 - sw/2, H - 80, 22, fade_color(COL_WHITE, 0.5))
    draw_quit_hint()
}

draw_game_over :: proc() {
    draw_arena_bg()
    draw_shards()
    draw_particles()
    rl.DrawRectangle(0, 0, W, H, fade_color(COL_BG, 0.78))
    title : cstring = "TIME"
    if st.game_mode == .Versus do title = "ROUND OVER"
    if st.game_mode == .Solo   do title = "RUN OVER"
    tw := rl.MeasureText(title, 86)
    rl.DrawText(title, W/2 - tw/2, 160, 86, COL_WHITE)

    if st.game_mode == .Solo {
        scr := fmt.ctprintf("SCORE   %d", st.solo_score)
        sw := rl.MeasureText(scr, 100)
        rl.DrawText(scr, W/2 - sw/2, 380, 100, P_COLORS[0])
    } else {
        // scoreboard
        // determine winner(s)
        top: i32 = -1
        for i in 0..<MAX_PLAYERS {
            if !st.players[i].active do continue
            if st.players[i].score > top do top = st.players[i].score
        }
        y := i32(340)
        for i in 0..<MAX_PLAYERS {
            p := &st.players[i]
            if !p.active do continue
            winner := p.score == top && top > 0
            color := winner ? COL_WHITE : COL_DIM
            label := fmt.ctprintf("P%d   %d%s", i+1, p.score, winner ? "  ★" : "")
            lw := rl.MeasureText(label, 64)
            rl.DrawText(label, W/2 - lw/2, y, 64, color)
            // color chip
            rl.DrawRectangle(W/2 - lw/2 - 70, y + 8, 40, 40, P_COLORS[i])
            y += 90
        }
    }
    hint := cstring("ATTACK to play again · HOLD BOTH to quit")
    hw := rl.MeasureText(hint, 28)
    rl.DrawText(hint, W/2 - hw/2, H - 120, 28, fade_color(COL_WHITE, 0.7))
    draw_quit_hint()
}

// ── Game tick ───────────────────────────────────────────────────────────────
update_play :: proc(dt: f32) {
    st.round_t -= dt
    if st.round_t <= 0 {
        st.mode = .Game_Over
        play(st.snd_score, 0.7, 0.8)
        return
    }
    step_players(dt)
    step_shards(dt)
    step_solo(dt)
    update_particles(dt)

    // Quit during play: any single player holding both buttons for QUIT_HOLD
    // sends the match back to game-over (so the cabinet can move on without
    // requiring all four to agree).
    quit_now := false
    for i in 0..<MAX_PLAYERS {
        if st.players[i].active && st.players[i].quit_hold >= QUIT_HOLD {
            quit_now = true
            break
        }
    }
    if quit_now {
        st.mode = .Game_Over
        for j in 0..<MAX_PLAYERS do st.players[j].quit_hold = 0
    }
}

draw_play :: proc() {
    draw_arena_bg()
    draw_shards()
    if st.game_mode == .Solo do draw_targets()
    // players drawn over shards
    for i in 0..<MAX_PLAYERS {
        draw_player(&st.players[i], i)
    }
    draw_particles()
    draw_hud()
    draw_quit_warn_per_player()
}

// ── main ────────────────────────────────────────────────────────────────────
main :: proc() {
    rl.SetConfigFlags({.MSAA_4X_HINT, .VSYNC_HINT, .FULLSCREEN_MODE})
    rl.InitWindow(W, H, "Lodestar")
    rl.SetTargetFPS(60)
    rl.SetExitKey(.KEY_NULL)
    rl.HideCursor()
    init_audio()
    defer {
        if st.audio_ok {
            rl.UnloadSound(st.snd_pulse)
            rl.UnloadSound(st.snd_flip)
            rl.UnloadSound(st.snd_hit)
            rl.UnloadSound(st.snd_score)
            rl.UnloadSound(st.snd_spawn)
            rl.CloseAudioDevice()
        }
        rl.CloseWindow()
    }

    st.mode = .Menu_Mode_Select
    st.game_mode = .Versus
    reset_shards()

    for !rl.WindowShouldClose() {
        dt := rl.GetFrameTime()
        if dt > 0.05 do dt = 0.05  // clamp to avoid physics explosions on stalls
        st.time_total += dt

        switch st.mode {
        case .Menu_Mode_Select: update_menu_select(dt)
        case .Menu_Join:        update_menu_join(dt)
        case .Playing:          update_play(dt)
        case .Game_Over:        update_game_over(dt)
        }

        rl.BeginDrawing()
        switch st.mode {
        case .Menu_Mode_Select: draw_menu_select()
        case .Menu_Join:        draw_menu_join()
        case .Playing:          draw_play()
        case .Game_Over:        draw_game_over()
        }
        rl.EndDrawing()

        free_all(context.temp_allocator)
    }
}
