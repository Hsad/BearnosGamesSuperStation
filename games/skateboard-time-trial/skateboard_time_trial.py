#!/usr/bin/env python3
"""
SKATEBOARD TIME TRIAL — solo race through outdoor terrain.
LEFT/RIGHT=steer  JUMP=hop obstacles  ATTACK=boost (cooldown)
Hold JUMP+ATTACK on any menu to quit.
"""
import pygame, sys, math, random, os, time, json

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
W, H = screen.get_size()
clock = pygame.time.Clock()
pygame.display.set_caption("SKATEBOARD TIME TRIAL")

_FONT_PATH = os.path.expanduser("~/.local/share/fonts/DepartureMono-Regular.otf")
def _f(sz):
    return (pygame.font.Font(_FONT_PATH, sz) if os.path.exists(_FONT_PATH)
            else pygame.font.SysFont("monospace", sz, bold=True))
FONTS = {s: _f(s) for s in (120, 96, 72, 48, 36, 24, 18, 14, 11)}

def blit(surf, text, size, color, pos, anchor="center"):
    s = FONTS[size].render(str(text), False, color)
    surf.blit(s, s.get_rect(**{anchor: pos}))

# ── Palette ───────────────────────────────────────────────────────────────────
WHITE     = (245, 245, 240)
SKY_TOP   = (110, 175, 220)
SKY_HOR   = (245, 205, 170)
HILL_FAR  = ( 95, 125,  95)
HILL_NEAR = ( 60, 100,  60)
GRASS_A   = ( 80, 145,  70)
GRASS_B   = ( 95, 160,  80)
ROAD_A    = (180, 160, 120)
ROAD_B    = (190, 170, 130)
ROAD_EDGE = (250, 245, 230)
SHADOW    = ( 35,  50,  35)
TRUNK     = ( 80,  55,  35)
LEAF_A    = ( 50,  95,  50)
LEAF_B    = ( 65, 115,  65)
ROCK_C    = (130, 125, 115)
ROCK_E    = ( 95,  90,  80)
SKIN      = (240, 200, 165)
SHIRT     = (230,  80,  80)
PANTS     = ( 60,  80, 130)
BOARD     = (180,  95,  50)
WHEEL     = ( 40,  40,  40)
GRAY      = (140, 140, 140)
DGRAY     = ( 50,  50,  60)
BOOST_C   = (255, 180,  30)
DANGER    = (220,  80,  60)
FINISH_C  = (250, 220,  60)

# ── World geometry ────────────────────────────────────────────────────────────
HORIZON_Y    = int(H * 0.42)
CAM_NEAR     = 8.0
CAM_FOV      = 380.0
CAM_HEIGHT   = 90.0
ROAD_HALFW   = 110.0
WORLD_HALFW  = 700.0

FINISH_Z     = 3200.0
SCROLL_BASE  = 130.0
SCROLL_MIN   = 60.0
BOOST_MULT   = 1.7
BOOST_DUR    = 1.6
BOOST_CD     = 4.0
STEER_SPEED  = 145.0

JUMP_DUR     = 0.65
JUMP_H       = 110.0

CRASH_DUR    = 1.3

SEG_LEN      = 18.0   # road stripe segment length in world z

SCORE_PATH   = os.path.join(os.path.dirname(__file__), "skateboard_scores.json")


# ── Input ─────────────────────────────────────────────────────────────────────
class Input:
    INACTIVITY_TIMEOUT = 60.0

    def __init__(self):
        self.maps  = []
        self._prev = set()
        self._curr = set()
        self._last_activity = time.monotonic()
        candidates = [
            os.path.join(os.path.dirname(__file__), "controllers.json"),
            os.path.join(os.path.dirname(__file__), "..", "..", "config", "controllers.json"),
        ]
        loaded = False
        for path in candidates:
            try:
                data = json.load(open(path))
                self.maps = [{a: v["key"] for a,v in p["inputs"].items()
                              if v["type"]=="key"} for p in data["players"]]
                loaded = True
                break
            except Exception:
                continue
        if not loaded:
            self.maps = [
                {"UP":1073741906,"DOWN":1073741905,"LEFT":1073741904,
                 "RIGHT":1073741903,"ATTACK":1073742050,"JUMP":1073742048},
                {"UP":ord('r'),"DOWN":ord('f'),"LEFT":ord('d'),
                 "RIGHT":ord('g'),"ATTACK":ord('s'),"JUMP":ord('a')},
                {"UP":ord('i'),"DOWN":ord('k'),"LEFT":ord('j'),
                 "RIGHT":ord('l'),"ATTACK":1073742053,"JUMP":1073742052},
                {"UP":ord('y'),"DOWN":ord('n'),"LEFT":ord('v'),
                 "RIGHT":ord('u'),"ATTACK":ord('e'),"JUMP":ord('b')},
            ]

    def pump(self, events):
        self._prev = set(self._curr)
        for e in events:
            if e.type == pygame.KEYDOWN:
                self._curr.add(e.key)
                self._last_activity = time.monotonic()
            elif e.type == pygame.KEYUP:
                self._curr.discard(e.key)

    def reset_activity(self):
        self._last_activity = time.monotonic()

    def timed_out(self):
        return time.monotonic() - self._last_activity > self.INACTIVITY_TIMEOUT

    def held(self, pid, act):
        k = self.maps[pid].get(act) if pid < len(self.maps) else None
        return k is not None and k in self._curr

    def just(self, pid, act):
        k = self.maps[pid].get(act) if pid < len(self.maps) else None
        return k is not None and k in self._curr and k not in self._prev

    def any_held(self, act):
        return any(self.held(p, act) for p in range(len(self.maps)))

    def any_just(self, act):
        return any(self.just(p, act) for p in range(len(self.maps)))

    def steer(self):
        """-1 left, +1 right, 0 idle. Aggregates across players."""
        s = 0
        for p in range(len(self.maps)):
            if self.held(p, "LEFT"):  s -= 1
            if self.held(p, "RIGHT"): s += 1
        return max(-1, min(1, s))

    def any_just_any(self):
        return any(self.just(p, a) for p in range(len(self.maps))
                   for a in ("UP","DOWN","LEFT","RIGHT","JUMP","ATTACK"))

    def quit_combo(self):
        return self.any_held("JUMP") and self.any_held("ATTACK")


# ── Pseudo-3D projection ──────────────────────────────────────────────────────
def proj_y(z):
    z = max(0.01, z)
    return HORIZON_Y + CAM_HEIGHT * CAM_FOV / (z + CAM_NEAR)

def proj_scale(z):
    z = max(0.01, z)
    return CAM_FOV / (z + CAM_NEAR)

def proj(world_x, z, cam_x=0.0):
    s = proj_scale(z)
    sx = W / 2 + (world_x - cam_x) * s
    sy = proj_y(z)
    return sx, sy, s


# ── Scenery (trees / rocks alongside) ─────────────────────────────────────────
class Scenery:
    def __init__(self, world_x, z, kind):
        self.x, self.z, self.kind = world_x, z, kind

    def draw(self, surf, cam_x):
        if self.z <= 0.1: return
        sx, sy, s = proj(self.x, self.z, cam_x)
        if sx < -200 or sx > W + 200: return
        if self.kind == "tree":
            trunk_w = max(1, int(8 * s))
            trunk_h = max(2, int(28 * s))
            crown_r = max(3, int(34 * s))
            pygame.draw.rect(surf, TRUNK,
                             (int(sx - trunk_w/2), int(sy - trunk_h),
                              trunk_w, trunk_h))
            pygame.draw.circle(surf, LEAF_A,
                               (int(sx), int(sy - trunk_h - crown_r*0.4)),
                               crown_r)
            pygame.draw.circle(surf, LEAF_B,
                               (int(sx - crown_r*0.4),
                                int(sy - trunk_h - crown_r*0.6)),
                               int(crown_r*0.6))
        elif self.kind == "rock":
            r = max(3, int(22 * s))
            pygame.draw.ellipse(surf, ROCK_C,
                                (int(sx - r), int(sy - r*0.7), r*2, int(r*1.2)))
            pygame.draw.ellipse(surf, ROCK_E,
                                (int(sx - r), int(sy - r*0.7), r*2, int(r*1.2)), 2)
        else:  # bush
            r = max(3, int(18 * s))
            pygame.draw.circle(surf, LEAF_A, (int(sx), int(sy - r*0.5)), r)
            pygame.draw.circle(surf, LEAF_B,
                               (int(sx - r*0.3), int(sy - r*0.7)), int(r*0.6))


# ── Obstacle (in the player's lane) ───────────────────────────────────────────
class Obstacle:
    """world_x in [-ROAD_HALFW, +ROAD_HALFW]. Hittable when z passes the player."""
    HIT_W = 32.0   # world half-width to count as collision
    HIT_Z = 8.0    # z-band thickness for collision

    def __init__(self, world_x, z, kind):
        self.x, self.z, self.kind = world_x, z, kind
        self.alive = True

    def passed(self):
        return self.z < -10.0

    def draw(self, surf, cam_x):
        if self.z <= 0.1: return
        sx, sy, s = proj(self.x, self.z, cam_x)
        if self.kind == "log":
            ww = max(6, int(60 * s))
            hh = max(3, int(14 * s))
            r = (int(sx - ww/2), int(sy - hh), ww, hh)
            pygame.draw.ellipse(surf, TRUNK, r)
            pygame.draw.ellipse(surf, (50, 35, 22), r, 2)
            # end rings
            pygame.draw.circle(surf, (135, 95, 60),
                               (int(sx - ww/2 + hh/2), int(sy - hh/2)),
                               max(1, hh//2))
        elif self.kind == "rock":
            r = max(4, int(28 * s))
            pygame.draw.ellipse(surf, ROCK_C,
                                (int(sx - r), int(sy - r*0.7), r*2, int(r*1.0)))
            pygame.draw.ellipse(surf, ROCK_E,
                                (int(sx - r), int(sy - r*0.7), r*2, int(r*1.0)), 2)
        else:  # cone
            ww = max(4, int(22 * s))
            hh = max(6, int(32 * s))
            pts = [(int(sx), int(sy - hh)),
                   (int(sx - ww/2), int(sy)),
                   (int(sx + ww/2), int(sy))]
            pygame.draw.polygon(surf, (240, 130, 40), pts)
            pygame.draw.line(surf, WHITE,
                             (int(sx - ww/2 + 2), int(sy - hh*0.45)),
                             (int(sx + ww/2 - 2), int(sy - hh*0.45)),
                             max(1, int(2*s)))


# ── Skater ────────────────────────────────────────────────────────────────────
class Skater:
    def __init__(self):
        self.x = 0.0
        self.jump_t = 0.0   # 0..JUMP_DUR while airborne
        self.air = False
        self.tilt = 0.0
        self.crash_t = 0.0
        self.boost_t = 0.0   # remaining boost seconds
        self.boost_cd = 0.0
        self.run_dist = 0.0   # world z covered (course progress)
        self.crashes = 0

    @property
    def air_h(self):
        if not self.air: return 0.0
        # parabola peaking at JUMP_DUR/2
        t = self.jump_t / JUMP_DUR
        return JUMP_H * 4 * t * (1 - t)

    def can_boost(self):
        return self.crash_t <= 0 and self.boost_cd <= 0 and self.boost_t <= 0

    def trigger_jump(self):
        if self.crash_t > 0: return
        if not self.air:
            self.air = True
            self.jump_t = 0.0

    def trigger_boost(self):
        if self.can_boost():
            self.boost_t = BOOST_DUR
            self.boost_cd = BOOST_CD + BOOST_DUR

    def crash(self):
        if self.crash_t > 0: return
        self.crash_t = CRASH_DUR
        self.boost_t = 0.0
        self.crashes += 1
        self.air = False
        self.jump_t = 0.0

    def update(self, dt, steer):
        if self.crash_t > 0:
            self.crash_t = max(0.0, self.crash_t - dt)
            # tumble: sway side to side
            self.tilt = math.sin(self.crash_t * 18) * 0.9
        else:
            target = steer * 0.6
            self.tilt += (target - self.tilt) * min(1.0, dt * 7)
            self.x += steer * STEER_SPEED * dt
            self.x = max(-ROAD_HALFW - 30, min(ROAD_HALFW + 30, self.x))
        if self.air:
            self.jump_t += dt
            if self.jump_t >= JUMP_DUR:
                self.air = False
                self.jump_t = 0.0
        self.boost_t  = max(0.0, self.boost_t - dt)
        self.boost_cd = max(0.0, self.boost_cd - dt)

    def speed_mult(self, run_factor):
        if self.crash_t > 0: return 0.55
        m = 1.0 + 0.45 * run_factor
        if self.boost_t > 0: m *= BOOST_MULT
        return m

    def draw(self, surf, t):
        # fixed screen position; vertical offset from jump
        cx = W // 2
        baseline = H - 250
        air_off = self.air_h
        cy = int(baseline - air_off)
        S = 6  # pixel block size
        tilt = self.tilt
        # shadow on ground (gets smaller / further from skater while airborne)
        shadow_y = baseline + 30
        shadow_w = max(20, int(80 * (1 - 0.55 * (air_off / JUMP_H))))
        pygame.draw.ellipse(surf, SHADOW,
                            (cx - shadow_w, shadow_y - 8,
                             shadow_w * 2, 16))
        if self.crash_t > 0:
            self._draw_ragdoll(surf, cx, cy, t, S)
            return

        # back-view skater: board at bottom, legs, torso, head
        # tilt skews legs/torso horizontally
        dx = int(tilt * 12)

        # board
        bw = 14 * S
        bh = 2  * S
        pygame.draw.rect(surf, BOARD, (cx - bw//2, cy + 4*S, bw, bh))
        pygame.draw.rect(surf, (90, 50, 25), (cx - bw//2, cy + 4*S, bw, bh), 2)
        # wheels
        for wx in (-bw//2 + 2*S, bw//2 - 3*S):
            pygame.draw.rect(surf, WHEEL,
                             (cx + wx, cy + 4*S + bh, 2*S, S))
        # legs
        pygame.draw.rect(surf, PANTS,
                         (cx - 4*S + dx, cy + S, 3*S, 4*S))
        pygame.draw.rect(surf, PANTS,
                         (cx + S + dx, cy + S, 3*S, 4*S))
        # torso
        pygame.draw.rect(surf, SHIRT,
                         (cx - 4*S + dx, cy - 4*S, 8*S, 5*S))
        # arms out (for balance)
        arm_drop = int(tilt * 2*S)
        pygame.draw.rect(surf, SHIRT,
                         (cx - 6*S + dx, cy - 3*S - arm_drop, 2*S, 4*S))
        pygame.draw.rect(surf, SHIRT,
                         (cx + 4*S + dx, cy - 3*S + arm_drop, 2*S, 4*S))
        # head (back of)
        pygame.draw.circle(surf, SKIN,
                           (cx + dx, cy - 5*S - S), int(2.5*S))
        # cap
        pygame.draw.rect(surf, (40, 60, 110),
                         (cx - 3*S + dx, cy - 8*S, 6*S, 2*S))
        # speed lines if boosting
        if self.boost_t > 0:
            for i in range(6):
                ly = cy + random.randint(-6*S, 6*S)
                lx = cx + (-1 if random.random() < 0.5 else 1) * random.randint(8*S, 14*S)
                pygame.draw.line(surf, BOOST_C,
                                 (lx, ly), (lx + random.randint(-30, -10), ly),
                                 3)

    def _draw_ragdoll(self, surf, cx, cy, t, S):
        rot = math.sin(self.crash_t * 22) * 1.4
        dx = int(math.cos(t * 12) * 30)
        dy = int(math.sin(t * 9) * 8)
        # board off to side, spinning
        bw = 12 * S
        bh = 2  * S
        br = pygame.Surface((bw, bh), pygame.SRCALPHA)
        br.fill((0, 0, 0, 0))
        pygame.draw.rect(br, BOARD, (0, 0, bw, bh))
        rb = pygame.transform.rotate(br, math.degrees(rot)*2)
        surf.blit(rb, rb.get_rect(center=(cx + dx, cy + 2*S + dy)))
        # body parts scattered
        pygame.draw.rect(surf, SHIRT,
                         (cx - 4*S + int(math.sin(t*8)*15),
                          cy - 2*S + int(math.cos(t*7)*12), 8*S, 4*S))
        pygame.draw.rect(surf, PANTS,
                         (cx - 3*S + int(math.cos(t*10)*18),
                          cy + 2*S + int(math.sin(t*11)*10), 6*S, 4*S))
        pygame.draw.circle(surf, SKIN,
                           (cx + int(math.sin(t*9)*25),
                            cy - 5*S + int(math.cos(t*8)*14)),
                           int(2.5*S))
        # stars/owie
        for i in range(4):
            ang = t * 6 + i * math.pi/2
            sx = int(cx + math.cos(ang) * 36)
            sy = int(cy - 6*S + math.sin(ang) * 18)
            pygame.draw.circle(surf, FINISH_C, (sx, sy), 4)


# ── Course ────────────────────────────────────────────────────────────────────
class Course:
    def __init__(self, run_count):
        self.scroll = 0.0      # cumulative world distance traveled
        self.run    = run_count
        self.run_factor = min(1.0, run_count * 0.18)
        # populate scenery (paired left/right with z offsets)
        self.scenery = []
        for z in range(80, 1200, 35):
            self._spawn_scenery(z + random.uniform(-10, 10))
        self.obstacles = []
        self._next_obs_z = 220.0
        self._spawn_initial_obs()
        self.finished = False

    def _spawn_scenery(self, z):
        # pick a side and an offset beyond the road
        side = random.choice((-1, 1))
        off = random.uniform(ROAD_HALFW + 40, WORLD_HALFW)
        kind = random.choices(("tree", "rock", "bush"),
                              weights=(0.6, 0.15, 0.25))[0]
        self.scenery.append(Scenery(side * off, z, kind))

    def _spawn_initial_obs(self):
        z = 260.0
        while z < 900:
            self._add_obstacle(z)
            z += random.uniform(85, 140)
        self._next_obs_z = z

    def _add_obstacle(self, z):
        x = random.uniform(-ROAD_HALFW + 25, ROAD_HALFW - 25)
        # progressively meaner: tighter clusters become more common late
        kind = random.choices(("log", "rock", "cone"),
                              weights=(0.45, 0.30, 0.25))[0]
        self.obstacles.append(Obstacle(x, z, kind))

    def advance(self, dz):
        """Move camera forward by dz; world recedes."""
        self.scroll += dz
        for s in self.scenery: s.z -= dz
        for o in self.obstacles: o.z -= dz
        # recycle scenery: when something passes camera, respawn far ahead
        far = 1100.0
        for s in self.scenery:
            if s.z < -20:
                s.z = far + random.uniform(0, 80)
                side = random.choice((-1, 1))
                s.x  = side * random.uniform(ROAD_HALFW + 40, WORLD_HALFW)
                s.kind = random.choices(("tree", "rock", "bush"),
                                        weights=(0.6, 0.15, 0.25))[0]
        # spawn new obstacles ahead, stop once we're near finish
        course_remaining = FINISH_Z - self.scroll
        if course_remaining > 250:
            while self._next_obs_z - dz < 950:
                self._add_obstacle(self._next_obs_z)
                self._next_obs_z += random.uniform(
                    max(70, 130 - 30 * self.run_factor),
                    max(110, 180 - 30 * self.run_factor))
            self._next_obs_z -= dz
        else:
            self._next_obs_z -= dz
        # cull passed obstacles
        self.obstacles = [o for o in self.obstacles if not o.passed()]
        # finish line crossing
        if self.scroll >= FINISH_Z:
            self.finished = True

    def finish_z(self):
        """Z distance from camera to finish line; <=0 once crossed."""
        return FINISH_Z - self.scroll


# ── Drawing ───────────────────────────────────────────────────────────────────
def draw_sky(surf):
    # vertical gradient: SKY_TOP at y=0 → SKY_HOR at horizon
    bands = 24
    for i in range(bands):
        y0 = i * HORIZON_Y // bands
        y1 = (i + 1) * HORIZON_Y // bands
        t = i / max(1, bands - 1)
        c = (int(SKY_TOP[0] + (SKY_HOR[0]-SKY_TOP[0])*t),
             int(SKY_TOP[1] + (SKY_HOR[1]-SKY_TOP[1])*t),
             int(SKY_TOP[2] + (SKY_HOR[2]-SKY_TOP[2])*t))
        pygame.draw.rect(surf, c, (0, y0, W, y1 - y0))

def draw_hills(surf, scroll, cam_x):
    """Two layers of rolling hills above the horizon."""
    # far hills
    pts_far = [(0, HORIZON_Y)]
    base = HORIZON_Y - 40
    for x in range(0, W + 80, 80):
        h = math.sin((x + scroll * 0.04 - cam_x * 0.5) * 0.006) * 18
        h += math.sin((x + scroll * 0.02) * 0.0028) * 12
        pts_far.append((x, base - h))
    pts_far.append((W, HORIZON_Y))
    pygame.draw.polygon(surf, HILL_FAR, pts_far)
    # near hills
    pts_near = [(0, HORIZON_Y)]
    base = HORIZON_Y - 18
    for x in range(0, W + 80, 60):
        h = math.sin((x + scroll * 0.08 - cam_x * 1.0) * 0.012) * 22
        h += math.cos((x + scroll * 0.05) * 0.005) * 14
        pts_near.append((x, base - h))
    pts_near.append((W, HORIZON_Y))
    pygame.draw.polygon(surf, HILL_NEAR, pts_near)

def draw_ground(surf, scroll, cam_x):
    """Per-row stripes of grass + road. Iterate y from horizon to bottom."""
    # background grass fill
    pygame.draw.rect(surf, GRASS_A, (0, HORIZON_Y, W, H - HORIZON_Y))
    step = 2
    cy = W / 2
    for y in range(HORIZON_Y + 1, H, step):
        z = CAM_HEIGHT * CAM_FOV / (y - HORIZON_Y) - CAM_NEAR
        if z <= 0: continue
        s = CAM_FOV / (z + CAM_NEAR)
        hw = ROAD_HALFW * s
        cx = cy - cam_x * s
        # grass stripes
        seg = int((z + scroll) / SEG_LEN) % 2
        g = GRASS_B if seg == 0 else GRASS_A
        pygame.draw.rect(surf, g, (0, y, W, step))
        # road
        rx0 = int(cx - hw)
        rx1 = int(cx + hw)
        if rx1 > 0 and rx0 < W:
            road_col = ROAD_B if seg == 0 else ROAD_A
            pygame.draw.rect(surf, road_col,
                             (max(0, rx0), y, min(W, rx1) - max(0, rx0), step))
            # edge stripes
            edge_w = max(1, int(3 * s))
            pygame.draw.rect(surf, ROAD_EDGE,
                             (rx0, y, edge_w, step))
            pygame.draw.rect(surf, ROAD_EDGE,
                             (rx1 - edge_w, y, edge_w, step))
            # center dashes only on alternate segments
            if seg == 0:
                cw = max(1, int(2 * s))
                pygame.draw.rect(surf, ROAD_EDGE,
                                 (int(cx - cw/2), y, cw, step))

def draw_finish(surf, finish_z, cam_x):
    if finish_z <= 0 or finish_z > 800: return
    # render a checkerboard banner at finish_z, slightly above road plane
    sy = proj_y(finish_z)
    s = proj_scale(finish_z)
    hw = (ROAD_HALFW + 30) * s
    cx = W / 2 - cam_x * s
    bh = max(6, int(28 * s))
    pole_h = max(20, int(140 * s))
    # poles
    for sign in (-1, 1):
        px = int(cx + sign * hw)
        pygame.draw.rect(surf, WHITE,
                         (px - max(1, int(3*s)), int(sy - pole_h),
                          max(2, int(6*s)), pole_h))
    # banner with checker
    bx0 = int(cx - hw)
    bx1 = int(cx + hw)
    by0 = int(sy - pole_h)
    by1 = by0 + bh
    pygame.draw.rect(surf, WHITE, (bx0, by0, bx1 - bx0, bh))
    cells = 16
    for i in range(cells):
        if i % 2 == 0: continue
        x0 = bx0 + (bx1 - bx0) * i // cells
        x1 = bx0 + (bx1 - bx0) * (i+1) // cells
        pygame.draw.rect(surf, (20, 20, 20), (x0, by0, x1 - x0, bh))
    blit(surf, "FINISH", max(14, min(48, int(36*s))), FINISH_C,
         (int(cx), int(by0 - 20)))


# ── HUD ───────────────────────────────────────────────────────────────────────
def fmt_time(secs):
    m = int(secs // 60)
    s = secs - m * 60
    return f"{m:01d}:{s:06.3f}"

def draw_hud(surf, elapsed, skater, course, best):
    # Important UI must clear top 30px (cabinet bezel)
    # Timer top-center
    bg = pygame.Surface((420, 70), pygame.SRCALPHA)
    bg.fill((10, 12, 22, 170))
    surf.blit(bg, (W//2 - 210, 36))
    blit(surf, fmt_time(elapsed), 48, WHITE, (W//2, 60), anchor="center")
    blit(surf, "TIME", 14, GRAY, (W//2, 92))

    # Best time, top-right
    if best is not None:
        blit(surf, "BEST", 14, GRAY, (W - 36, 40), anchor="topright")
        blit(surf, fmt_time(best), 24, FINISH_C,
             (W - 36, 56), anchor="topright")

    # Boost meter, top-left
    box_x, box_y, box_w, box_h = 36, 40, 260, 48
    pygame.draw.rect(surf, (10, 12, 22), (box_x, box_y, box_w, box_h))
    pygame.draw.rect(surf, GRAY, (box_x, box_y, box_w, box_h), 2)
    if skater.boost_t > 0:
        frac = skater.boost_t / BOOST_DUR
        pygame.draw.rect(surf, BOOST_C,
                         (box_x + 4, box_y + 4,
                          int((box_w - 8) * frac), box_h - 8))
        blit(surf, "BOOST!", 18, (15, 15, 25),
             (box_x + box_w//2, box_y + box_h//2))
    elif skater.boost_cd > 0:
        frac = 1 - (skater.boost_cd / (BOOST_CD + BOOST_DUR))
        pygame.draw.rect(surf, DGRAY,
                         (box_x + 4, box_y + 4,
                          int((box_w - 8) * frac), box_h - 8))
        blit(surf, f"COOLING  {skater.boost_cd:0.1f}s", 18, GRAY,
             (box_x + box_w//2, box_y + box_h//2))
    else:
        pygame.draw.rect(surf, BOOST_C,
                         (box_x + 4, box_y + 4, box_w - 8, box_h - 8))
        blit(surf, "ATTACK = BOOST", 18, (15, 15, 25),
             (box_x + box_w//2, box_y + box_h//2))

    # Course progress bar, bottom
    bar_w, bar_h = 800, 10
    bx = W//2 - bar_w//2
    by = H - 40
    pygame.draw.rect(surf, DGRAY, (bx, by, bar_w, bar_h))
    frac = min(1.0, course.scroll / FINISH_Z)
    pygame.draw.rect(surf, WHITE, (bx, by, int(bar_w * frac), bar_h))
    pygame.draw.rect(surf, FINISH_C,
                     (bx + bar_w - 4, by - 2, 4, bar_h + 4))
    blit(surf, "START", 11, GRAY, (bx, by - 14), anchor="topleft")
    blit(surf, "FINISH", 11, FINISH_C, (bx + bar_w, by - 14), anchor="topright")

    # crash indicator
    if skater.crash_t > 0:
        blit(surf, "WIPEOUT!", 72, DANGER, (W//2, H//2 - 100))


# ── Score persistence ─────────────────────────────────────────────────────────
def load_scores():
    try:
        return json.load(open(SCORE_PATH))
    except Exception:
        return {"best": None, "runs": 0}

def save_scores(data):
    try:
        json.dump(data, open(SCORE_PATH, "w"), indent=2)
    except Exception:
        pass


# ── Title screen ──────────────────────────────────────────────────────────────
def title_screen(inp, scores):
    inp.reset_activity()
    t0 = time.monotonic()
    while True:
        dt = clock.tick(60) / 1000.0
        events = pygame.event.get()
        inp.pump(events)
        if inp.timed_out(): return False
        for e in events:
            if e.type == pygame.QUIT: return False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE: return False
        if inp.quit_combo(): return False
        if inp.any_just("ATTACK") or inp.any_just("JUMP"): return True

        t = time.monotonic() - t0
        # background animation: scrolling demo course
        screen.fill(SKY_TOP)
        draw_sky(screen)
        draw_hills(screen, t * 40, math.sin(t*0.5) * 30)
        draw_ground(screen, t * 80, math.sin(t*0.5) * 30)

        # title
        blit(screen, "SKATEBOARD", 120, WHITE, (W//2, 180))
        blit(screen, "TIME  TRIAL", 96, FINISH_C, (W//2, 290))
        # tagline
        blit(screen, "ride the trail.   wipe out.   chase your best.",
             24, WHITE, (W//2, 380))

        # demo skater
        demo_x = math.sin(t * 1.4) * 60
        s = Skater()
        s.x = demo_x
        s.tilt = -math.cos(t * 1.4) * 0.6
        s.draw(screen, t)

        # controls
        ox = W // 2 - 300
        cy = H - 240
        pygame.draw.rect(screen, (10, 12, 22, 200),
                         (ox - 30, cy - 30, 660, 180))
        pygame.draw.rect(screen, WHITE,
                         (ox - 30, cy - 30, 660, 180), 2)
        blit(screen, "HOW  TO  RIDE", 24, FINISH_C, (W//2, cy - 6))
        blit(screen, "LEFT / RIGHT   steer the board",
             24, WHITE, (W//2, cy + 28))
        blit(screen, "JUMP           hop over obstacles",
             24, WHITE, (W//2, cy + 58))
        blit(screen, "ATTACK         speed boost (cooldown)",
             24, WHITE, (W//2, cy + 88))

        # best time
        if scores.get("best") is not None:
            blit(screen, f"BEST TIME   {fmt_time(scores['best'])}",
                 36, FINISH_C, (W//2, H - 130))
        blit(screen, f"RUNS  {scores.get('runs', 0)}",
             18, GRAY, (W//2, H - 90))

        # press to start (blink)
        if int(t * 2) % 2 == 0:
            blit(screen, "PRESS  ATTACK  TO  START",
                 36, WHITE, (W//2, H - 60))
        blit(screen, "hold JUMP + ATTACK to quit", 14, GRAY,
             (W - 20, H - 16), anchor="bottomright")

        pygame.display.flip()


# ── Gameplay ──────────────────────────────────────────────────────────────────
def play(inp, scores):
    inp.reset_activity()
    course  = Course(scores.get("runs", 0))
    skater  = Skater()
    elapsed = 0.0
    t_total = 0.0
    cdwn    = 3.0
    finished = False
    finished_t = 0.0

    while True:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        t_total += dt
        events = pygame.event.get()
        inp.pump(events)
        if inp.timed_out(): return None
        for e in events:
            if e.type == pygame.QUIT: return None
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE: return None
        if inp.quit_combo(): return None

        # ── countdown ──
        if cdwn > 0:
            cdwn -= dt
            screen.fill(SKY_TOP)
            draw_sky(screen)
            draw_hills(screen, 0, 0)
            draw_ground(screen, 0, 0)
            # static scene with skater waiting
            for s in sorted(course.scenery, key=lambda x: -x.z):
                s.draw(screen, 0)
            skater.draw(screen, t_total)
            label = str(int(math.ceil(cdwn))) if cdwn > 0.6 else "GO!"
            blit(screen, label, 120, WHITE, (W//2, H//2 - 60))
            blit(screen, "get ready", 24, GRAY, (W//2, H//2 + 60))
            pygame.display.flip()
            continue

        # ── inputs ──
        steer = inp.steer()
        if not finished:
            if inp.any_just("JUMP"):   skater.trigger_jump()
            if inp.any_just("ATTACK"): skater.trigger_boost()

        skater.update(dt, steer if not finished else 0)

        # ── advance world ──
        mult = skater.speed_mult(course.run_factor)
        if finished:
            mult *= max(0.0, 1.0 - finished_t * 0.5)
        dz = SCROLL_BASE * mult * dt
        course.advance(dz)

        if not finished:
            elapsed += dt
            # ── collisions: any obstacle in the player z-band, on lane, not airborne
            if skater.crash_t <= 0 and not skater.air:
                for o in course.obstacles:
                    if -Obstacle.HIT_Z < o.z < Obstacle.HIT_Z:
                        if abs(o.x - skater.x) < Obstacle.HIT_W:
                            skater.crash()
                            break
            # finish?
            if course.finished:
                finished = True
                finished_t = 0.0
                # save
                prev_best = scores.get("best")
                scores["runs"] = scores.get("runs", 0) + 1
                if prev_best is None or elapsed < prev_best:
                    scores["best"] = elapsed
                    scores["pb_new"] = True
                else:
                    scores["pb_new"] = False
                save_scores({k: v for k, v in scores.items() if k != "pb_new"})
        else:
            finished_t += dt
            if finished_t > 2.6:
                return ("finish", elapsed, skater.crashes, scores)

        # ── render ──
        screen.fill(SKY_TOP)
        draw_sky(screen)
        draw_hills(screen, course.scroll, skater.x)
        draw_ground(screen, course.scroll, skater.x)
        # depth-sort drawables: scenery + obstacles + finish, back to front
        drawables = []
        for s in course.scenery:
            if s.z > 0: drawables.append((s.z, "sc", s))
        for o in course.obstacles:
            if o.z > 0.1: drawables.append((o.z, "ob", o))
        drawables.sort(key=lambda t: -t[0])
        for _, kind, item in drawables:
            item.draw(screen, skater.x)
        # finish banner
        fz = course.finish_z()
        if fz > 0:
            draw_finish(screen, fz, skater.x)
        # skater
        skater.draw(screen, t_total)

        draw_hud(screen, elapsed, skater, course, scores.get("best"))

        if finished:
            blit(screen, "FINISH!", 120, FINISH_C, (W//2, H//2 - 80))
            blit(screen, fmt_time(elapsed), 72, WHITE, (W//2, H//2 + 20))

        pygame.display.flip()


# ── End screen ────────────────────────────────────────────────────────────────
def end_screen(inp, elapsed, crashes, scores):
    inp.reset_activity()
    sel = 0
    t0 = time.monotonic()
    pb_new = scores.get("pb_new", False)

    while True:
        dt = clock.tick(60) / 1000.0
        events = pygame.event.get()
        inp.pump(events)
        if inp.timed_out(): return False
        for e in events:
            if e.type == pygame.QUIT: return False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE: return False
        if inp.quit_combo(): return False

        if inp.any_just("LEFT") or inp.any_just("RIGHT") \
           or inp.any_just("UP") or inp.any_just("DOWN"):
            sel = 1 - sel
        if inp.any_just("ATTACK") or inp.any_just("JUMP"):
            return sel == 0

        t = time.monotonic() - t0

        screen.fill(SKY_TOP)
        draw_sky(screen)
        draw_hills(screen, t * 30, 0)
        draw_ground(screen, t * 50, 0)

        if pb_new:
            blit(screen, "NEW PERSONAL BEST!", 96, FINISH_C, (W//2, 160))
        else:
            blit(screen, "RUN COMPLETE", 96, WHITE, (W//2, 160))

        blit(screen, "your time", 24, GRAY, (W//2, 280))
        blit(screen, fmt_time(elapsed), 120, WHITE, (W//2, 360))

        if scores.get("best") is not None:
            blit(screen, "best", 18, GRAY, (W//2, 470))
            blit(screen, fmt_time(scores["best"]), 48, FINISH_C, (W//2, 510))

        blit(screen, f"wipeouts  {crashes}", 24, GRAY, (W//2, 600))
        blit(screen, f"runs  {scores.get('runs', 0)}", 18, GRAY, (W//2, 640))

        for opt, label, oy in ((0, "RIDE AGAIN", H - 280),
                               (1, "QUIT",       H - 220)):
            col = WHITE if sel == opt else GRAY
            txt = f"> {label} <" if sel == opt else f"  {label}  "
            blit(screen, txt, 48, col, (W//2, oy))

        blit(screen, "ATTACK to choose · LEFT/RIGHT to switch · hold JUMP+ATTACK to quit",
             14, GRAY, (W//2, H - 60))

        pygame.display.flip()


# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    inp = Input()
    try:
        while True:
            scores = load_scores()
            if not title_screen(inp, scores):
                break
            result = play(inp, scores)
            if result is None:
                break
            _, elapsed, crashes, scores = result
            if not end_screen(inp, elapsed, crashes, scores):
                break
    finally:
        pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
