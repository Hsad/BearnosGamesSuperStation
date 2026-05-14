package skateboard

import rl "vendor:raylib"
import "core:math"
import "core:math/rand"
import "core:fmt"
import "core:os"
import "core:strings"
import "core:strconv"

// ── Window ──────────────────────────────────────────────────────────────────
W :: 1920
H :: 1080

// ── World ───────────────────────────────────────────────────────────────────
TRAIL_HALFW   : f32 :  6.0
TRAIL_WALLW   : f32 :  9.5
FINISH_Z      : f32 :  700.0
SCENE_AHEAD   : f32 :  170.0
SCENE_BEHIND  : f32 :   30.0
DRAW_AHEAD    : f32 :  150.0  // tighter cull for drawing only

// ── Physics ─────────────────────────────────────────────────────────────────
SPEED_MIN     : f32 :  6.5
SPEED_MAX     : f32 : 30.0
SPEED_BASE    : f32 : 13.0
ACCEL         : f32 :  4.0
FRICTION      : f32 :  1.4
LATERAL_ACC   : f32 : 26.0
LATERAL_FRIC  : f32 :  9.0
LATERAL_MAX   : f32 : 10.0
GRAVITY       : f32 : 30.0
OLLIE_VY      : f32 :  9.5
RAMP_LAUNCH   : f32 : 14.5
BOOST_MULT    : f32 :  1.65
BOOST_DUR     : f32 :  2.5
BOOST_CD      : f32 :  6.0
CRASH_DUR     : f32 :  1.2
CRASH_PEN     : f32 :  0.45

QUIT_HOLD_DUR : f32 :  3.0
QUIT_WARN_T   : f32 :  1.0

// ── Camera ──────────────────────────────────────────────────────────────────
CAM_BACK      : f32 :  7.5
CAM_UP        : f32 :  3.4
CAM_LOOK_FWD  : f32 :  6.0

OBS_GAP_MIN   : f32 : 22.0
OBS_GAP_MAX   : f32 : 42.0

// ── Scoring ─────────────────────────────────────────────────────────────────
PT_OLLIE      :: 50
PT_GRAB       :: 100
PT_FLIP       :: 150
PT_AIR_PER_S  :: 30

SCORE_FILE :: "scores.txt"
IDLE_TIMEOUT  : f32 : 60.0

// ── Colors ──────────────────────────────────────────────────────────────────
COL_SKY      := rl.Color{125, 185, 230, 255}
COL_FOG      := rl.Color{180, 205, 220, 255}
COL_GRASS    := rl.Color{ 82, 145,  70, 255}
COL_GRASS_DK := rl.Color{ 65, 120,  55, 255}
COL_TRAIL    := rl.Color{180, 160, 120, 255}
COL_TRAIL_DK := rl.Color{160, 140, 100, 255}
COL_TRAIL_E  := rl.Color{240, 235, 220, 255}
COL_TRUNK    := rl.Color{ 80,  55,  35, 255}
COL_LEAF_A   := rl.Color{ 55, 100,  55, 255}
COL_LEAF_B   := rl.Color{ 70, 120,  65, 255}
COL_ROCK     := rl.Color{130, 125, 115, 255}
COL_ROCK_DK  := rl.Color{ 95,  90,  80, 255}
COL_CONE     := rl.Color{240, 130,  40, 255}
COL_LOG      := rl.Color{ 95,  65,  40, 255}
COL_RAMP     := rl.Color{170, 110,  60, 255}
COL_RAMP_DK  := rl.Color{130,  85,  45, 255}
COL_RAMP_FR  := rl.Color{120,  75,  35, 255}
COL_SHIRT    := rl.Color{230,  80,  80, 255}
COL_PANTS    := rl.Color{ 60,  80, 130, 255}
COL_SKIN     := rl.Color{240, 200, 165, 255}
COL_BOARD    := rl.Color{180,  95,  50, 255}
COL_WHITE    := rl.Color{245, 245, 240, 255}
COL_BLACK    := rl.Color{ 18,  18,  22, 255}
COL_SHADOW   := rl.Color{ 30,  60,  30, 140}
COL_FINISH   := rl.Color{250, 220,  60, 255}
COL_BOOST    := rl.Color{255, 180,  30, 255}
COL_DANGER   := rl.Color{220,  80,  60, 255}
COL_GRAY     := rl.Color{140, 140, 140, 255}
COL_HUDBG    := rl.Color{ 15,  18,  28, 200}
COL_CAP      := rl.Color{ 40,  60, 110, 255}

// ── Input — physical mappings for the four cabinet players ─────────────────
// (Mirrors config/controllers.json. Solo game, but any player's buttons work.)
KEYS_LEFT  := [?]rl.KeyboardKey{.LEFT, .D, .J, .V}
KEYS_RIGHT := [?]rl.KeyboardKey{.RIGHT, .G, .L, .U}
KEYS_UP    := [?]rl.KeyboardKey{.UP, .R, .I, .Y}
KEYS_DOWN  := [?]rl.KeyboardKey{.DOWN, .F, .K, .N}
KEYS_JUMP  := [?]rl.KeyboardKey{.LEFT_CONTROL, .A, .RIGHT_CONTROL, .B}
KEYS_ATK   := [?]rl.KeyboardKey{.LEFT_ALT,     .S, .RIGHT_SHIFT,    .E}

any_down :: proc(keys: []rl.KeyboardKey) -> bool {
    for k in keys do if rl.IsKeyDown(k) do return true
    return false
}
any_pressed :: proc(keys: []rl.KeyboardKey) -> bool {
    for k in keys do if rl.IsKeyPressed(k) do return true
    return false
}
steer_input :: proc() -> f32 {
    s: f32 = 0
    if any_down(KEYS_LEFT[:])  do s -= 1
    if any_down(KEYS_RIGHT[:]) do s += 1
    return s
}
quit_held :: proc() -> bool {
    return any_down(KEYS_JUMP[:]) && any_down(KEYS_ATK[:])
}
any_input_pressed :: proc() -> bool {
    return any_pressed(KEYS_LEFT[:])  || any_pressed(KEYS_RIGHT[:]) ||
           any_pressed(KEYS_UP[:])    || any_pressed(KEYS_DOWN[:])  ||
           any_pressed(KEYS_JUMP[:])  || any_pressed(KEYS_ATK[:])
}

// ── Types ───────────────────────────────────────────────────────────────────
Obs_Kind  :: enum u8 { CONE, LOG, ROCK, RAMP }
Tree_Kind :: enum u8 { TREE, BUSH, ROCK }
Trick     :: enum { OLLIE, GRAB, FLIP }
Trick_Set :: bit_set[Trick]

Obstacle :: struct {
    kind: Obs_Kind,
    pos:  rl.Vector3,
    half: rl.Vector3,
}

Tree :: struct {
    pos:   rl.Vector3,
    scale: f32,
    kind:  Tree_Kind,
}

Floater :: struct {
    text:  string,
    pos:   rl.Vector3,
    age:   f32,
    color: rl.Color,
}

Skater :: struct {
    pos:        rl.Vector3,
    vy:         f32,
    lateral_v:  f32,
    forward_v:  f32,
    on_ground:  bool,
    on_ramp:    bool,
    air_t:      f32,
    air_score:  int,
    tilt:       f32,
    crash_t:    f32,
    crashes:    int,
    boost_t:    f32,
    boost_cd:   f32,
    tricks:     Trick_Set,
    combo_mult: int,
    score:      int,
    last_combo: int,
}

Game_State :: enum { TITLE, COUNTDOWN, PLAY, FINISH, END }

Game :: struct {
    state:        Game_State,
    state_t:      f32,
    elapsed:      f32,
    last_activity: f32,

    skater:       Skater,
    obstacles:    [dynamic]Obstacle,
    trees:        [dynamic]Tree,
    floaters:     [dynamic]Floater,
    next_obs_z:   f32,
    next_tree_z:  f32,

    cam:          rl.Camera3D,

    runs:         int,
    best_time:    f32,
    best_score:   int,
    pb_new:       bool,
    hi_new:       bool,
    last_elapsed: f32,
    last_score:   int,
    last_crashes: int,
    end_sel:      int,

    quit_hold_t:  f32,
}

g: Game

// ── Scores ──────────────────────────────────────────────────────────────────
load_scores :: proc() {
    g.best_time = 0
    g.best_score = 0
    g.runs = 0
    data, err := os.read_entire_file_from_path(SCORE_FILE, context.allocator)
    if err != nil do return
    defer delete(data)
    parts := strings.split(string(data), "\n", context.temp_allocator)
    if len(parts) >= 1 do g.best_time,  _ = strconv.parse_f32(strings.trim_space(parts[0]))
    if len(parts) >= 2 do g.best_score, _ = strconv.parse_int(strings.trim_space(parts[1]))
    if len(parts) >= 3 do g.runs,       _ = strconv.parse_int(strings.trim_space(parts[2]))
}

save_scores :: proc() {
    s := fmt.tprintf("%v\n%d\n%d\n", g.best_time, g.best_score, g.runs)
    _ = os.write_entire_file_from_string(SCORE_FILE, s)
}

// ── State transitions ───────────────────────────────────────────────────────
enter_title :: proc() {
    g.state = .TITLE
    g.state_t = 0
    clear_dyn()
    g.skater = Skater{}
    g.skater.forward_v = SPEED_BASE * 0.55
    g.skater.combo_mult = 1
    g.skater.on_ground = true
    g.next_obs_z = 30
    g.next_tree_z = -SCENE_BEHIND
    populate_initial_scene()
    g.elapsed = 0
    g.last_activity = f32(rl.GetTime())
}

enter_countdown :: proc() {
    g.state = .COUNTDOWN
    g.state_t = 0
    clear_dyn()
    g.skater = Skater{}
    g.skater.forward_v = SPEED_BASE
    g.skater.combo_mult = 1
    g.skater.on_ground = true
    g.next_obs_z = 28
    g.next_tree_z = -SCENE_BEHIND
    populate_initial_scene()
    g.elapsed = 0
    g.last_activity = f32(rl.GetTime())
}

enter_finish :: proc() {
    g.state = .FINISH
    g.state_t = 0
    g.last_elapsed = g.elapsed
    g.last_score   = g.skater.score
    g.last_crashes = g.skater.crashes
    g.runs += 1
    g.pb_new = false
    g.hi_new = false
    if g.best_time == 0 || g.elapsed < g.best_time {
        g.best_time = g.elapsed
        g.pb_new = true
    }
    if g.skater.score > g.best_score {
        g.best_score = g.skater.score
        g.hi_new = true
    }
    save_scores()
    g.last_activity = f32(rl.GetTime())
}

enter_end :: proc() {
    g.state = .END
    g.state_t = 0
    g.end_sel = 0
    g.last_activity = f32(rl.GetTime())
}

clear_dyn :: proc() {
    clear(&g.obstacles)
    clear(&g.trees)
    for &f in g.floaters do delete(f.text)
    clear(&g.floaters)
}

// ── Scene populate / recycle ────────────────────────────────────────────────
spawn_tree_row :: proc(z: f32) {
    n := 1 + rand.int_max(3)
    for _ in 0..<n {
        side: f32 = -1 if rand.int_max(2) == 0 else 1
        off := TRAIL_HALFW + 2 + rand.float32() * 18
        k: Tree_Kind = .TREE
        r := rand.float32()
        if      r < 0.20 do k = .BUSH
        else if r < 0.34 do k = .ROCK
        append(&g.trees, Tree{
            pos = {side * off, 0, z + rand.float32() * 6},
            scale = 0.7 + rand.float32() * 1.0,
            kind = k,
        })
    }
}

spawn_obstacle :: proc(z: f32) {
    if z >= FINISH_Z - 12 do return
    r := rand.float32()
    x := (rand.float32() * 2 - 1) * (TRAIL_HALFW - 1.4)
    k: Obs_Kind = .CONE
    half: rl.Vector3
    if r < 0.32 {
        k = .CONE
        half = {0.5, 0.65, 0.5}
    } else if r < 0.62 {
        k = .LOG
        half = {1.4, 0.35, 0.5}
    } else if r < 0.80 {
        k = .ROCK
        half = {0.9, 0.55, 0.7}
    } else {
        k = .RAMP
        half = {1.5, 0.85, 2.4}
    }
    append(&g.obstacles, Obstacle{kind = k, pos = {x, 0, z}, half = half})
}

populate_initial_scene :: proc() {
    z: f32 = -SCENE_BEHIND
    for z < SCENE_AHEAD {
        spawn_tree_row(z)
        z += 5 + rand.float32() * 4
    }
    g.next_tree_z = z
    z = 28
    for z < SCENE_AHEAD - 20 {
        spawn_obstacle(z)
        z += OBS_GAP_MIN + rand.float32() * (OBS_GAP_MAX - OBS_GAP_MIN)
    }
    g.next_obs_z = z
}

recycle_scene :: proc() {
    cam_z := g.skater.pos.z
    behind := cam_z - SCENE_BEHIND

    i := 0
    for i < len(g.obstacles) {
        if g.obstacles[i].pos.z < behind {
            g.obstacles[i] = g.obstacles[len(g.obstacles)-1]
            pop(&g.obstacles)
        } else { i += 1 }
    }
    i = 0
    for i < len(g.trees) {
        if g.trees[i].pos.z < behind {
            g.trees[i] = g.trees[len(g.trees)-1]
            pop(&g.trees)
        } else { i += 1 }
    }

    for g.next_obs_z < cam_z + SCENE_AHEAD {
        spawn_obstacle(g.next_obs_z)
        g.next_obs_z += OBS_GAP_MIN + rand.float32() * (OBS_GAP_MAX - OBS_GAP_MIN)
    }
    for g.next_tree_z < cam_z + SCENE_AHEAD {
        spawn_tree_row(g.next_tree_z)
        g.next_tree_z += 5 + rand.float32() * 4
    }
}

// ── Floaters ────────────────────────────────────────────────────────────────
add_floater :: proc(text: string, pos: rl.Vector3, color: rl.Color) {
    append(&g.floaters, Floater{
        text  = strings.clone(text),
        pos   = {pos.x, pos.y + 2.0, pos.z},
        age   = 0,
        color = color,
    })
}

update_floaters :: proc(dt: f32) {
    i := 0
    for i < len(g.floaters) {
        f := &g.floaters[i]
        f.age += dt
        f.pos.y += dt * 1.6
        if f.age > 1.4 {
            delete(f.text)
            g.floaters[i] = g.floaters[len(g.floaters)-1]
            pop(&g.floaters)
        } else { i += 1 }
    }
}

// ── Skater update ───────────────────────────────────────────────────────────
crash_skater :: proc(reason: string) {
    s := &g.skater
    if s.crash_t > 0 do return
    s.crash_t   = CRASH_DUR
    s.crashes  += 1
    s.combo_mult = 1
    s.air_score = 0
    s.air_t     = 0
    s.tricks    = {}
    s.on_ground = true
    s.on_ramp   = false
    s.pos.y     = 0
    s.vy        = 0
    s.forward_v *= CRASH_PEN
    add_floater(reason, s.pos, COL_DANGER)
}

land_skater :: proc() {
    s := &g.skater
    if s.crash_t > 0 do return
    was_air := !s.on_ground
    s.on_ground = true
    s.vy = 0
    if was_air && s.air_score > 0 {
        air_pts := int(f32(PT_AIR_PER_S) * s.air_t)
        total := (s.air_score + air_pts) * s.combo_mult
        s.score += total
        s.last_combo = total
        add_floater(fmt.tprintf("x%d  +%d", s.combo_mult, total), s.pos, COL_FINISH)
        s.combo_mult = min(9, s.combo_mult + 1)
    }
    s.air_score = 0
    s.air_t     = 0
    s.tricks    = {}
}

update_skater :: proc(dt: f32) {
    s := &g.skater
    crashed := s.crash_t > 0
    steer := steer_input()

    // ── Inputs ──
    if !crashed {
        if s.on_ground {
            // Boost only available on flat ground, not while riding a ramp.
            if !s.on_ramp && any_pressed(KEYS_ATK[:]) &&
               s.boost_cd <= 0 && s.boost_t <= 0 {
                s.boost_t  = BOOST_DUR
                s.boost_cd = BOOST_CD + BOOST_DUR
                add_floater("BOOST!", s.pos, COL_BOOST)
            }
            // JUMP gives a regular ollie on flat ground, a bigger launch off a ramp.
            if any_pressed(KEYS_JUMP[:]) {
                if s.on_ramp {
                    s.vy = RAMP_LAUNCH
                    s.air_score = PT_OLLIE * 2
                    add_floater("LAUNCH!", s.pos, COL_BOOST)
                } else {
                    s.vy = OLLIE_VY
                    s.air_score = PT_OLLIE
                    add_floater("OLLIE", s.pos, COL_WHITE)
                }
                s.on_ground = false
                s.on_ramp   = false
                s.air_t = 0
                s.tricks = {.OLLIE}
            }
        } else if !s.on_ground {
            if any_pressed(KEYS_ATK[:]) && !(.GRAB in s.tricks) {
                s.tricks += {.GRAB}
                s.air_score += PT_GRAB
                add_floater("GRAB!", s.pos, COL_BOOST)
            }
            if any_pressed(KEYS_JUMP[:]) && !(.FLIP in s.tricks) {
                s.tricks += {.FLIP}
                s.air_score += PT_FLIP
                label := "KICKFLIP!" if steer < 0 else "SHUVIT!"
                add_floater(label, s.pos, COL_FINISH)
            }
        }
    } else {
        s.crash_t -= dt
        if s.crash_t <= 0 do s.crash_t = 0
    }

    // ── Forward velocity ──
    target := SPEED_BASE
    if !crashed && s.boost_t > 0 do target *= BOOST_MULT
    if crashed                   do target *= 0.55
    if s.forward_v < target {
        s.forward_v += ACCEL * dt
        if s.forward_v > target do s.forward_v = target
    } else {
        s.forward_v -= FRICTION * dt
        if s.forward_v < target do s.forward_v = target
    }
    s.forward_v = clamp(s.forward_v, SPEED_MIN * CRASH_PEN, SPEED_MAX)

    // ── Lateral velocity ──
    if !crashed {
        s.lateral_v += steer * LATERAL_ACC * dt
        if steer == 0 ||
           (steer > 0 && s.lateral_v < 0) ||
           (steer < 0 && s.lateral_v > 0) {
            d := LATERAL_FRIC * dt
            if abs(s.lateral_v) <= d {
                s.lateral_v = 0
            } else {
                s.lateral_v -= d * (1 if s.lateral_v > 0 else -1)
            }
        }
        s.lateral_v = clamp(s.lateral_v, -LATERAL_MAX, LATERAL_MAX)
    } else {
        s.lateral_v *= 0.94
    }

    // ── Position ──
    s.pos.x += s.lateral_v * dt
    s.pos.z += s.forward_v * dt

    // Off-trail = wipeout
    if abs(s.pos.x) > TRAIL_WALLW && !crashed {
        s.pos.x = clamp(s.pos.x, -TRAIL_WALLW, TRAIL_WALLW)
        s.lateral_v = 0
        crash_skater("off trail!")
    }

    // ── Vertical motion + ramp interaction ──
    was_on_ramp := s.on_ramp
    s.on_ramp = false
    if s.on_ground {
        // Riding a ramp surface: pos.y tracks the slope. Stepping off the front
        // or sides doesn't snap to the floor — gravity takes over from current
        // height so the player falls off the edge naturally.
        ramp_y, ramped, _ := ramp_surface_at(s.pos.x, s.pos.z)
        if ramped {
            s.pos.y = ramp_y
            s.on_ramp = true
        } else if was_on_ramp && s.pos.y > 0.05 {
            // Rolled off without jumping — become airborne, inherit no upward
            // velocity (no "trick" credit either).
            s.on_ground = false
            s.vy = 0
            s.air_t = 0
            s.air_score = 0
            s.tricks = {}
        } else {
            s.pos.y = 0
        }
    } else {
        s.vy -= GRAVITY * dt
        s.pos.y += s.vy * dt
        s.air_t += dt
        if s.pos.y <= 0 {
            s.pos.y = 0
            land_skater()
        }
    }

    // Boost timers
    if s.boost_t  > 0 { s.boost_t  -= dt; if s.boost_t  < 0 do s.boost_t  = 0 }
    if s.boost_cd > 0 { s.boost_cd -= dt; if s.boost_cd < 0 do s.boost_cd = 0 }

    // Tilt visual
    target_tilt: f32 = 0
    if crashed {
        target_tilt = math.sin(s.crash_t * 20) * 1.0
    } else if s.on_ground {
        target_tilt = clamp(s.lateral_v / LATERAL_MAX, -1, 1) * 0.5
    } else {
        target_tilt = clamp(s.lateral_v / LATERAL_MAX, -1, 1) * 0.3
    }
    s.tilt += (target_tilt - s.tilt) * min(1.0, dt * 7)
}

// Returns (y_on_ramp_surface, riding_a_ramp, just_launched_off_top)
ramp_surface_at :: proc(x, z: f32) -> (f32, bool, bool) {
    for &o in g.obstacles {
        if o.kind != .RAMP do continue
        if abs(x - o.pos.x) > o.half.x do continue
        z_back  := o.pos.z - o.half.z
        z_front := o.pos.z + o.half.z
        if z < z_back || z > z_front + 0.3 do continue
        frac := clamp((z - z_back) / (z_front - z_back), 0, 1)
        y := o.half.y * 2 * frac
        if frac >= 0.99 do return y, true, true
        return y, true, false
    }
    return 0, false, false
}

// ── Collisions with obstacles (cones/logs/rocks) ────────────────────────────
check_collisions :: proc() {
    s := &g.skater
    if s.crash_t > 0 do return
    for &o in g.obstacles {
        if o.kind == .RAMP do continue
        dz := o.pos.z - s.pos.z
        if dz < -2 || dz > o.half.z + 1 do continue
        if abs(s.pos.x - o.pos.x) > o.half.x + 0.45 do continue
        // Inside obstacle XZ band. Did we clear it via jump?
        clear_height: f32
        reason: string
        switch o.kind {
        case .CONE: clear_height = o.half.y * 2.0;  reason = "wipeout!"
        case .LOG:  clear_height = o.half.y * 2.3;  reason = "tripped!"
        case .ROCK: clear_height = o.half.y * 2.0;  reason = "rocks!"
        case .RAMP: continue
        }
        if s.pos.y < clear_height {
            crash_skater(reason)
            return
        }
    }
}

// ── Camera update ───────────────────────────────────────────────────────────
update_camera :: proc(dt: f32) {
    s := g.skater
    target_pos := rl.Vector3{s.pos.x * 0.45, max(s.pos.y, 0) + CAM_UP, s.pos.z - CAM_BACK}
    target_tgt := rl.Vector3{s.pos.x * 0.7,  max(s.pos.y, 0) + 1.2,    s.pos.z + CAM_LOOK_FWD}
    lerp_xy: f32 = min(1.0, dt * 6)
    g.cam.position.x += (target_pos.x - g.cam.position.x) * lerp_xy
    g.cam.position.y += (target_pos.y - g.cam.position.y) * min(1.0, dt * 5)
    g.cam.position.z = target_pos.z
    g.cam.target.x += (target_tgt.x - g.cam.target.x) * lerp_xy
    g.cam.target.y += (target_tgt.y - g.cam.target.y) * min(1.0, dt * 5)
    g.cam.target.z = target_tgt.z
}

// ── 3D Drawing ──────────────────────────────────────────────────────────────
draw_ground :: proc() {
    cam_z := g.skater.pos.z
    GRID :: f32(24.0)
    z0 := math.floor((cam_z - SCENE_BEHIND) / GRID) * GRID
    z1 := math.floor((cam_z + SCENE_AHEAD) / GRID) * GRID + GRID
    z  := z0
    for z < z1 {
        even := int(z / GRID) % 2 == 0
        gcol := COL_GRASS if even else COL_GRASS_DK
        tcol := COL_TRAIL if even else COL_TRAIL_DK
        rl.DrawCube({-60, -0.05, z + GRID/2}, 100, 0.10, GRID, gcol)
        rl.DrawCube({ 60, -0.05, z + GRID/2}, 100, 0.10, GRID, gcol)
        rl.DrawCube({  0, -0.04, z + GRID/2}, TRAIL_HALFW*2, 0.08, GRID, tcol)
        rl.DrawCube({-TRAIL_HALFW + 0.10, -0.02, z + GRID/2}, 0.22, 0.04, GRID, COL_TRAIL_E)
        rl.DrawCube({ TRAIL_HALFW - 0.10, -0.02, z + GRID/2}, 0.22, 0.04, GRID, COL_TRAIL_E)
        z += GRID
    }
}

draw_tri_both :: proc(a, b, c: rl.Vector3, col: rl.Color) {
    rl.DrawTriangle3D(a, b, c, col)
    rl.DrawTriangle3D(a, c, b, col)
}

// Pi's GLES2 pipeline hates raylib's default 16x16 sphere segments; a few dozen
// trees per frame at that density tanks framerate. 4 rings × 6 slices is ugly
// up close but at scene distances it reads fine and is ~10x cheaper.
draw_sphere_lo :: #force_inline proc(pos: rl.Vector3, r: f32, col: rl.Color) {
    rl.DrawSphereEx(pos, r, 4, 6, col)
}

draw_tree :: proc(t: Tree) {
    s := t.scale
    switch t.kind {
    case .TREE:
        rl.DrawCylinder(t.pos, 0.22*s, 0.28*s, 1.8*s, 8, COL_TRUNK)
        draw_sphere_lo({t.pos.x,         t.pos.y + 1.8*s + 0.6*s, t.pos.z},         0.95*s, COL_LEAF_A)
        draw_sphere_lo({t.pos.x - 0.4*s, t.pos.y + 1.8*s + 1.1*s, t.pos.z + 0.2*s}, 0.70*s, COL_LEAF_B)
    case .BUSH:
        draw_sphere_lo({t.pos.x,         t.pos.y + 0.4*s, t.pos.z},         0.55*s, COL_LEAF_A)
        draw_sphere_lo({t.pos.x + 0.3*s, t.pos.y + 0.6*s, t.pos.z - 0.1*s}, 0.35*s, COL_LEAF_B)
    case .ROCK:
        draw_sphere_lo({t.pos.x,         t.pos.y + 0.25*s, t.pos.z},          0.45*s, COL_ROCK)
        draw_sphere_lo({t.pos.x + 0.3*s, t.pos.y + 0.20*s, t.pos.z + 0.2*s},  0.30*s, COL_ROCK_DK)
    }
}

draw_obstacle :: proc(o: Obstacle) {
    switch o.kind {
    case .CONE:
        rl.DrawCylinder({o.pos.x, o.pos.y, o.pos.z}, 0.0, o.half.x, o.half.y*2, 6, COL_CONE)
        rl.DrawCube({o.pos.x, o.pos.y + 0.04, o.pos.z}, o.half.x*2, 0.08, o.half.x*2, COL_BLACK)
        rl.DrawCylinder({o.pos.x, o.pos.y + o.half.y*0.9, o.pos.z}, o.half.x*0.55, o.half.x*0.6, 0.12, 6, COL_WHITE)
    case .LOG:
        rl.DrawCube({o.pos.x, o.pos.y + o.half.y, o.pos.z}, o.half.x*2, o.half.y*2, o.half.z*2, COL_LOG)
        rl.DrawCubeWires({o.pos.x, o.pos.y + o.half.y, o.pos.z}, o.half.x*2, o.half.y*2, o.half.z*2, COL_BLACK)
        // bark detail stripes
        for i in 0..<3 {
            yo := f32(i) * o.half.y * 0.6 - o.half.y*0.4
            rl.DrawCube({o.pos.x, o.pos.y + o.half.y + yo, o.pos.z + 0.01},
                        o.half.x*2 - 0.04, 0.05, 0.02, rl.Color{60, 40, 22, 255})
        }
    case .ROCK:
        draw_sphere_lo({o.pos.x, o.pos.y + o.half.y*0.7, o.pos.z}, o.half.x, COL_ROCK)
        draw_sphere_lo({o.pos.x + o.half.x*0.4, o.pos.y + o.half.y*0.4, o.pos.z - o.half.z*0.3}, o.half.x*0.55, COL_ROCK_DK)
    case .RAMP:
        hx := o.half.x; hy := o.half.y; hz := o.half.z
        x  := o.pos.x;  z  := o.pos.z
        bl_back  := rl.Vector3{x-hx, 0,    z-hz}
        br_back  := rl.Vector3{x+hx, 0,    z-hz}
        bl_front := rl.Vector3{x-hx, 0,    z+hz}
        br_front := rl.Vector3{x+hx, 0,    z+hz}
        tl_front := rl.Vector3{x-hx, hy*2, z+hz}
        tr_front := rl.Vector3{x+hx, hy*2, z+hz}
        // sloped top
        draw_tri_both(bl_back, br_back, tr_front, COL_RAMP)
        draw_tri_both(bl_back, tr_front, tl_front, COL_RAMP)
        // sides
        draw_tri_both(br_back, br_front, tr_front, COL_RAMP_DK)
        draw_tri_both(bl_back, tl_front, bl_front, COL_RAMP_DK)
        // front wall
        draw_tri_both(bl_front, br_front, tr_front, COL_RAMP_FR)
        draw_tri_both(bl_front, tr_front, tl_front, COL_RAMP_FR)
        // top edge stripe
        rl.DrawCube({x, hy*2 + 0.02, z + hz + 0.01}, hx*2, 0.04, 0.10, COL_WHITE)
    }
}

draw_skater :: proc(t: f32) {
    s := g.skater
    p := s.pos
    tilt := s.tilt
    // shadow on ground
    rl.DrawCylinder({p.x, 0.005, p.z}, 0.55, 0.55, 0.01, 10, COL_SHADOW)
    if s.crash_t > 0 {
        // ragdoll scattered parts
        rl.DrawCube({p.x + math.sin(t*9)*0.6, 0.4,
                     p.z + math.cos(t*7)*0.3}, 0.5, 0.4, 0.3, COL_SHIRT)
        rl.DrawCube({p.x + math.cos(t*10)*0.7, 0.3,
                     p.z + math.sin(t*8)*0.3}, 0.3, 0.4, 0.3, COL_PANTS)
        draw_sphere_lo({p.x + math.sin(t*8)*0.9,
                       0.5 + math.cos(t*7)*0.3,
                       p.z + math.cos(t*9)*0.4}, 0.18, COL_SKIN)
        rl.DrawCube({p.x + math.cos(t*5)*1.0, 0.05,
                     p.z - 0.3 + math.sin(t*6)*0.3}, 1.2, 0.08, 0.4, COL_BOARD)
        return
    }
    tilt_off := tilt * 0.35
    // board
    rl.DrawCube({p.x, p.y + 0.06, p.z}, 1.3, 0.08, 0.4, COL_BOARD)
    rl.DrawCubeWires({p.x, p.y + 0.06, p.z}, 1.3, 0.08, 0.4, COL_BLACK)
    rl.DrawCube({p.x, p.y + 0.02, p.z - 0.45}, 1.0, 0.06, 0.08, COL_BLACK)
    rl.DrawCube({p.x, p.y + 0.02, p.z + 0.45}, 1.0, 0.06, 0.08, COL_BLACK)
    // legs
    rl.DrawCube({p.x - 0.18, p.y + 0.45, p.z}, 0.20, 0.70, 0.20, COL_PANTS)
    rl.DrawCube({p.x + 0.18, p.y + 0.45, p.z}, 0.20, 0.70, 0.20, COL_PANTS)
    // torso (back-facing)
    rl.DrawCube({p.x + tilt_off, p.y + 1.15, p.z}, 0.65, 0.70, 0.32, COL_SHIRT)
    // arms (slight tilt drop)
    arm_drop := tilt * 0.12
    rl.DrawCube({p.x - 0.45 + tilt_off, p.y + 1.10 - arm_drop, p.z}, 0.18, 0.50, 0.18, COL_SHIRT)
    rl.DrawCube({p.x + 0.45 + tilt_off, p.y + 1.10 + arm_drop, p.z}, 0.18, 0.50, 0.18, COL_SHIRT)
    // head + cap
    draw_sphere_lo({p.x + tilt_off, p.y + 1.65, p.z}, 0.20, COL_SKIN)
    rl.DrawCube({p.x + tilt_off, p.y + 1.78, p.z - 0.04}, 0.42, 0.13, 0.42, COL_CAP)
    // boost streaks
    if s.boost_t > 0 {
        for i in 0..<6 {
            xo := (rand.float32() - 0.5) * 1.0
            yo := f32(i) * 0.18 - 0.4
            zo := (rand.float32() - 0.5) * 0.8
            rl.DrawCube({p.x + xo, p.y + 0.9 + yo, p.z - 0.7 + zo}, 0.06, 0.06, 0.5, COL_BOOST)
        }
    }
}

draw_finish_banner :: proc() {
    z := FINISH_Z
    if g.skater.pos.z > z + 5 || g.skater.pos.z < z - 240 do return
    rl.DrawCube({-TRAIL_HALFW - 0.6, 2.5, z}, 0.3, 5.0, 0.3, COL_WHITE)
    rl.DrawCube({ TRAIL_HALFW + 0.6, 2.5, z}, 0.3, 5.0, 0.3, COL_WHITE)
    rl.DrawCube({0, 4.8, z}, (TRAIL_HALFW + 0.5)*2, 0.6, 0.10, COL_WHITE)
    cells := 18
    for i in 0..<cells {
        if i % 2 == 0 do continue
        cw := (TRAIL_HALFW + 0.5) * 2 / f32(cells)
        cx := -(TRAIL_HALFW + 0.5) + (f32(i) + 0.5) * cw
        rl.DrawCube({cx, 4.8, z + 0.06}, cw, 0.6, 0.04, COL_BLACK)
    }
    rl.DrawCube({0, 0.02, z}, TRAIL_HALFW * 2, 0.04, 0.4, COL_FINISH)
}

draw_floaters_3d :: proc() {
    for f in g.floaters {
        // Project to 2D to render text overlay later (we do this in 2D pass)
        _ = f
    }
}

draw_floaters_2d :: proc() {
    for f in g.floaters {
        sp := rl.GetWorldToScreen(f.pos, g.cam)
        if sp.x < -100 || sp.x > W + 100 do continue
        if sp.y < -100 || sp.y > H + 100 do continue
        alpha: u8 = u8(clamp(int(255 * (1 - f.age / 1.4)), 0, 255))
        c := f.color; c.a = alpha
        size: i32 = 36
        ct := strings.clone_to_cstring(f.text, context.temp_allocator)
        tw := rl.MeasureText(ct, size)
        rl.DrawText(ct, i32(sp.x) - tw/2, i32(sp.y) - size, size, c)
    }
}

// ── 2D HUD ──────────────────────────────────────────────────────────────────
fmt_time :: proc(t: f32) -> string {
    m := int(t / 60)
    sec := t - f32(m)*60
    return fmt.tprintf("%d:%06.3f", m, sec)
}

draw_text_centered :: proc(text: cstring, x, y, size: i32, color: rl.Color) {
    tw := rl.MeasureText(text, size)
    rl.DrawText(text, x - tw/2, y, size, color)
}

draw_hud_play :: proc() {
    s := g.skater
    // Timer top-center (>30px from top)
    rl.DrawRectangle(W/2 - 240, 36, 480, 80, COL_HUDBG)
    draw_text_centered(fmt.ctprintf("%s", fmt_time(g.elapsed)), W/2, 52, 56, COL_WHITE)
    draw_text_centered("TIME", W/2, 100, 16, COL_GRAY)

    // Score top-right
    rl.DrawText("SCORE", W - 360, 38, 18, COL_GRAY)
    rl.DrawText(fmt.ctprintf("%d", s.score), W - 360, 60, 48, COL_WHITE)
    rl.DrawText("BEST", W - 360, 116, 14, COL_GRAY)
    rl.DrawText(fmt.ctprintf("%d", g.best_score), W - 360, 134, 22, COL_FINISH)

    // Boost meter top-left
    bx, by, bw, bh: i32 = 36, 40, 300, 52
    rl.DrawRectangle(bx, by, bw, bh, COL_HUDBG)
    rl.DrawRectangleLines(bx, by, bw, bh, COL_GRAY)
    if s.boost_t > 0 {
        frac := s.boost_t / BOOST_DUR
        rl.DrawRectangle(bx + 4, by + 4, i32(f32(bw - 8) * frac), bh - 8, COL_BOOST)
        draw_text_centered("BOOST!", bx + bw/2, by + bh/2 - 12, 24, COL_BLACK)
    } else if s.boost_cd > 0 {
        frac := 1 - (s.boost_cd / (BOOST_CD + BOOST_DUR))
        rl.DrawRectangle(bx + 4, by + 4, i32(f32(bw - 8) * frac), bh - 8, rl.Color{60,60,70,255})
        draw_text_centered(fmt.ctprintf("COOLING %.1fs", s.boost_cd), bx + bw/2, by + bh/2 - 10, 20, COL_GRAY)
    } else {
        rl.DrawRectangle(bx + 4, by + 4, bw - 8, bh - 8, COL_BOOST)
        draw_text_centered("ATTACK = BOOST", bx + bw/2, by + bh/2 - 10, 20, COL_BLACK)
    }

    // Combo (below boost) if airborne or recent
    if !s.on_ground || s.combo_mult > 1 {
        rl.DrawText(fmt.ctprintf("COMBO  x%d", s.combo_mult), bx, by + bh + 14, 22, COL_FINISH)
        if !s.on_ground && s.air_score > 0 {
            rl.DrawText(fmt.ctprintf("+%d  (air %.1fs)", s.air_score, s.air_t),
                        bx, by + bh + 42, 18, COL_WHITE)
        }
    }

    // Progress bar bottom
    bar_w: i32 = 800
    bar_x := W/2 - bar_w/2
    bar_y: i32 = H - 50
    rl.DrawRectangle(bar_x, bar_y, bar_w, 10, rl.Color{50, 50, 60, 255})
    frac := clamp(g.skater.pos.z / FINISH_Z, 0, 1)
    rl.DrawRectangle(bar_x, bar_y, i32(f32(bar_w) * frac), 10, COL_WHITE)
    rl.DrawRectangle(bar_x + bar_w - 4, bar_y - 2, 4, 14, COL_FINISH)
    rl.DrawText("START",  bar_x, bar_y - 20, 14, COL_GRAY)
    tw := rl.MeasureText("FINISH", 14)
    rl.DrawText("FINISH", bar_x + bar_w - tw, bar_y - 20, 14, COL_FINISH)

    // Wipeout label
    if s.crash_t > 0 {
        draw_text_centered("WIPEOUT!", W/2, H/2 - 120, 96, COL_DANGER)
    }
}

// ── Frame: 3D world render shared by all states ─────────────────────────────
render_world :: proc(t: f32) {
    rl.ClearBackground(COL_SKY)
    rl.BeginMode3D(g.cam)

    // distant low band of "fog" — a big horizontal rectangle far ahead
    rl.DrawCube({0, 12, g.skater.pos.z + SCENE_AHEAD - 10},
                400, 24, 1, COL_FOG)

    draw_ground()
    cam_z  := g.skater.pos.z
    cull_z := cam_z + DRAW_AHEAD
    near_z := cam_z - 6
    for tr in g.trees     do if tr.pos.z >= near_z && tr.pos.z <= cull_z do draw_tree(tr)
    for o  in g.obstacles do if o.pos.z  >= near_z && o.pos.z  <= cull_z do draw_obstacle(o)
    draw_finish_banner()
    draw_skater(t)

    rl.EndMode3D()

    draw_floaters_2d()
}

// ── Title ───────────────────────────────────────────────────────────────────
update_title :: proc(dt: f32) {
    g.state_t += dt
    // gently scroll the demo skater forward & sway lateral
    g.skater.pos.z   += g.skater.forward_v * dt
    g.skater.pos.x    = math.sin(g.state_t * 1.4) * 3.0
    g.skater.lateral_v = math.cos(g.state_t * 1.4) * 3.0
    recycle_scene()
    update_floaters(dt)
    update_camera(dt)

    if any_input_pressed() do g.last_activity = f32(rl.GetTime())
    if any_pressed(KEYS_ATK[:]) || any_pressed(KEYS_JUMP[:]) {
        enter_countdown()
    }
}

draw_title :: proc(t: f32) {
    render_world(t)
    // big title
    draw_text_centered("SKATEBOARD",   W/2, 130, 120, COL_WHITE)
    draw_text_centered("TIME  TRIAL",  W/2, 240,  96, COL_FINISH)
    draw_text_centered("[ v2 - odin + raylib ]", W/2, 350, 18, COL_GRAY)

    // controls panel
    px, py: i32 = W/2 - 320, H - 290
    rl.DrawRectangle(px, py, 640, 200, COL_HUDBG)
    rl.DrawRectangleLines(px, py, 640, 200, COL_WHITE)
    draw_text_centered("HOW  TO  RIDE", W/2, py + 14, 28, COL_FINISH)
    rl.DrawText("LEFT / RIGHT   steer",                 px + 30, py +  60, 26, COL_WHITE)
    rl.DrawText("JUMP           ollie / flip in air",   px + 30, py +  95, 26, COL_WHITE)
    rl.DrawText("ATTACK         boost / grab in air",   px + 30, py + 130, 26, COL_WHITE)
    rl.DrawText("land tricks to combo your score",      px + 30, py + 165, 18, COL_GRAY)

    // best
    if g.best_time > 0 {
        draw_text_centered(fmt.ctprintf("BEST  %s    HIGH SCORE  %d",
                                        fmt_time(g.best_time), g.best_score),
                           W/2, H - 70, 28, COL_FINISH)
    }
    if int(t * 2) % 2 == 0 {
        draw_text_centered("PRESS  ATTACK  TO  START", W/2, H - 36, 32, COL_WHITE)
    }
}

// ── Countdown ───────────────────────────────────────────────────────────────
update_countdown :: proc(dt: f32) {
    g.state_t += dt
    update_camera(dt)
    update_floaters(dt)
    if g.state_t >= 3.0 {
        g.state = .PLAY
        g.state_t = 0
        g.last_activity = f32(rl.GetTime())
    }
}

draw_countdown :: proc(t: f32) {
    render_world(t)
    remaining := 3.0 - g.state_t
    label := fmt.ctprintf("%d", int(math.ceil(remaining)))
    if remaining < 0.6 do label = "GO!"
    draw_text_centered(label, W/2, H/2 - 80, 160, COL_WHITE)
    draw_text_centered("get ready", W/2, H/2 + 80, 28, COL_GRAY)
}

// ── Play ────────────────────────────────────────────────────────────────────
update_play :: proc(dt: f32) {
    g.elapsed += dt
    update_skater(dt)
    check_collisions()
    recycle_scene()
    update_floaters(dt)
    update_camera(dt)
    if any_input_pressed() do g.last_activity = f32(rl.GetTime())
    if g.skater.pos.z >= FINISH_Z {
        enter_finish()
    }
}

// ── Finish (brief celebration) ──────────────────────────────────────────────
update_finish :: proc(dt: f32) {
    g.state_t += dt
    // glide to a stop
    g.skater.forward_v = max(0, g.skater.forward_v - 4.0 * dt)
    g.skater.pos.z    += g.skater.forward_v * dt
    g.skater.lateral_v *= 0.9
    g.skater.pos.x    += g.skater.lateral_v * dt
    recycle_scene()
    update_floaters(dt)
    update_camera(dt)
    if g.state_t > 2.6 {
        enter_end()
    }
}

draw_finish :: proc(t: f32) {
    render_world(t)
    draw_text_centered("FINISH!", W/2, H/2 - 120, 140, COL_FINISH)
    draw_text_centered(fmt.ctprintf("%s", fmt_time(g.elapsed)),
                       W/2, H/2 + 30, 80, COL_WHITE)
    draw_text_centered(fmt.ctprintf("SCORE  %d", g.skater.score),
                       W/2, H/2 + 120, 40, COL_FINISH)
}

// ── End screen ──────────────────────────────────────────────────────────────
update_end :: proc(dt: f32) {
    g.state_t += dt
    update_camera(dt)
    update_floaters(dt)
    if any_input_pressed() do g.last_activity = f32(rl.GetTime())

    if any_pressed(KEYS_LEFT[:])  || any_pressed(KEYS_RIGHT[:]) ||
       any_pressed(KEYS_UP[:])    || any_pressed(KEYS_DOWN[:]) {
        g.end_sel = 1 - g.end_sel
    }
    if any_pressed(KEYS_ATK[:]) || any_pressed(KEYS_JUMP[:]) {
        if g.end_sel == 0 do enter_countdown()
        else              do rl.CloseWindow()
    }
}

draw_end :: proc(t: f32) {
    render_world(t)
    rl.DrawRectangle(0, 0, W, H, rl.Color{0, 0, 0, 140})

    if g.pb_new {
        draw_text_centered("NEW  PERSONAL  BEST!", W/2, 100, 80, COL_FINISH)
    } else if g.hi_new {
        draw_text_centered("NEW  HIGH  SCORE!", W/2, 100, 80, COL_FINISH)
    } else {
        draw_text_centered("RUN  COMPLETE", W/2, 100, 80, COL_WHITE)
    }

    draw_text_centered("time", W/2 - 280, 240, 24, COL_GRAY)
    draw_text_centered(fmt.ctprintf("%s", fmt_time(g.last_elapsed)),
                       W/2 - 280, 280, 64, COL_WHITE)
    draw_text_centered("score", W/2 + 280, 240, 24, COL_GRAY)
    draw_text_centered(fmt.ctprintf("%d", g.last_score),
                       W/2 + 280, 280, 64, COL_WHITE)

    draw_text_centered("best time", W/2 - 280, 400, 16, COL_GRAY)
    draw_text_centered(fmt.ctprintf("%s", fmt_time(g.best_time)),
                       W/2 - 280, 430, 32, COL_FINISH)
    draw_text_centered("high score", W/2 + 280, 400, 16, COL_GRAY)
    draw_text_centered(fmt.ctprintf("%d", g.best_score),
                       W/2 + 280, 430, 32, COL_FINISH)

    draw_text_centered(fmt.ctprintf("wipeouts %d  ·  runs %d", g.last_crashes, g.runs),
                       W/2, 510, 24, COL_GRAY)

    // menu
    for opt in 0..<2 {
        label := "RIDE  AGAIN" if opt == 0 else "QUIT"
        y := i32(H - 280 + opt * 70)
        col := COL_WHITE if opt == g.end_sel else COL_GRAY
        text := fmt.ctprintf("> %s <", label) if opt == g.end_sel else fmt.ctprintf("  %s  ", label)
        draw_text_centered(text, W/2, y, 56, col)
    }
    draw_text_centered("ATTACK to choose · LEFT/RIGHT to switch · hold JUMP+ATTACK to quit",
                       W/2, H - 50, 16, COL_GRAY)
}

// ── Quit-hold overlay ───────────────────────────────────────────────────────
draw_quit_warning :: proc() {
    if g.quit_hold_t < QUIT_WARN_T do return
    progress := (g.quit_hold_t - QUIT_WARN_T) / (QUIT_HOLD_DUR - QUIT_WARN_T)
    progress  = clamp(progress, 0, 1)
    // Flashing border that fills as the hold continues.
    flash: f32 = 0.55 + 0.45 * math.sin(g.quit_hold_t * 18)
    col := COL_DANGER
    col.a = u8(clamp(int(255 * (0.45 + 0.55 * progress) * flash), 0, 255))
    border: i32 = i32(8 + 28 * progress)
    rl.DrawRectangle(0,            0,              W, border, col)
    rl.DrawRectangle(0,            H - border,     W, border, col)
    rl.DrawRectangle(0,            0,              border, H, col)
    rl.DrawRectangle(W - border,   0,              border, H, col)
    // Banner with countdown.
    bx, by, bw, bh: i32 = W/2 - 360, H/2 - 90, 720, 180
    rl.DrawRectangle(bx, by, bw, bh, rl.Color{15, 18, 28, 220})
    rl.DrawRectangleLines(bx, by, bw, bh, COL_DANGER)
    draw_text_centered("HOLD  TO  QUIT", W/2, by + 28, 44, COL_DANGER)
    remaining := QUIT_HOLD_DUR - g.quit_hold_t
    if remaining < 0 do remaining = 0
    draw_text_centered(fmt.ctprintf("%.1f", remaining), W/2, by + 86, 64, COL_WHITE)
    // Progress bar.
    pad: i32 = 36
    bar_w := bw - pad*2
    bar_h: i32 = 12
    bar_x := bx + pad
    bar_y := by + bh - pad
    rl.DrawRectangle(bar_x, bar_y, bar_w, bar_h, rl.Color{40, 40, 50, 255})
    rl.DrawRectangle(bar_x, bar_y, i32(f32(bar_w) * progress), bar_h, COL_DANGER)
}

// ── Main loop ───────────────────────────────────────────────────────────────
main :: proc() {
    rl.SetConfigFlags({.VSYNC_HINT, .FULLSCREEN_MODE})
    rl.InitWindow(W, H, "Skateboard Time Trial v2")
    defer rl.CloseWindow()
    rl.SetTargetFPS(60)
    rl.SetExitKey(.KEY_NULL)
    rl.HideCursor()

    g.cam = rl.Camera3D{
        position   = {0, CAM_UP, -CAM_BACK},
        target     = {0, 1.2,    CAM_LOOK_FWD},
        up         = {0, 1, 0},
        fovy       = 60,
        projection = .PERSPECTIVE,
    }

    g.obstacles = make([dynamic]Obstacle)
    g.trees     = make([dynamic]Tree)
    g.floaters  = make([dynamic]Floater)

    load_scores()
    enter_title()

    for !rl.WindowShouldClose() {
        dt := rl.GetFrameTime()
        if dt > 0.05 do dt = 0.05
        t := f32(rl.GetTime())

        if quit_held() {
            g.quit_hold_t += dt
            if g.quit_hold_t >= QUIT_HOLD_DUR do break
        } else {
            g.quit_hold_t = 0
        }
        if t - g.last_activity > IDLE_TIMEOUT do break

        switch g.state {
        case .TITLE:     update_title(dt)
        case .COUNTDOWN: update_countdown(dt)
        case .PLAY:      update_play(dt)
        case .FINISH:    update_finish(dt)
        case .END:       update_end(dt)
        }

        rl.BeginDrawing()
        switch g.state {
        case .TITLE:     draw_title(t)
        case .COUNTDOWN: draw_countdown(t)
        case .PLAY:      render_world(t); draw_hud_play()
        case .FINISH:    draw_finish(t)
        case .END:       draw_end(t)
        }
        draw_quit_warning()
        rl.EndDrawing()

        free_all(context.temp_allocator)
    }
}
