#!/usr/bin/env python3
"""
ORBITAL BREAKER
Laser satellite brick-breaker set in space.
4 players, orbital rings of solar panel satellites, shared ball pool.
"""
import pygame
import sys
import json
import math
import random
import os
import time

pygame.init()

screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
W, H   = screen.get_size()
CX, CY = W // 2, H // 2
clock  = pygame.time.Clock()
pygame.display.set_caption("ORBITAL BREAKER")

# ── Font ──────────────────────────────────────────────────────────────────────
_FONT_PATH = os.path.expanduser("~/.local/share/fonts/DepartureMono-Regular.otf")
def _f(size):
    if os.path.exists(_FONT_PATH):
        return pygame.font.Font(_FONT_PATH, size)
    return pygame.font.SysFont("monospace", size, bold=True)

FONTS = {s: _f(s) for s in (60, 36, 24, 18, 14, 11)}

def blit(surf, text, size, color, pos, anchor="center"):
    s = FONTS[size].render(str(text), False, color)
    r = s.get_rect(**{anchor: pos})
    surf.blit(s, r)

# ── Constants ─────────────────────────────────────────────────────────────────
EARTH_R      = 45
PLAY_R       = min(CX, CY) - 40        # ~490px on 1080p
ZONE_R       = PLAY_R * 0.5            # inner/outer split

PLAYER_MIN_R = int(ZONE_R) + 70   # must exceed ZONE_R + BRICK_COL_R (26) + kill margin (20)
PLAYER_MAX_R = min(CX, CY) - 30        # almost to screen edge
PLAYER_ANG_SPD = 1.8                   # rad/s rotation
PLAYER_RAD_SPD = 65                    # px/s raise/lower

BALL_R         = 4
BALL_SPEED     = 130                   # px/s (slower)
BALL_SMASH     = 1.55                  # speed multiplier on button hit
BALL_MAX_SPD   = 260

PLAYER_HW      = 10                   # satellite half-width  (radial,     20px total)
PLAYER_HH      = 30                   # satellite half-height (tangential, 60px total)

BALL_LIVES     = 3                     # shared lives pool

BRICK_W        = 44
BRICK_H        = 14
CORE_W         = 14
WING_W         = 15
BRICK_COL_R    = 26                    # collision circle radius

RING_RADII     = [110, 175, 240]       # fixed ring positions (px from center)
ARC_SPACING    = 75                    # arc-length between brick centers

TRANSIT_SPD    = 80                    # px/s — bricks reach ring in ~2s

LASER_DUR      = 0.5                   # seconds

START_MONEY    = 10
RESPAWN_COSTS  = [0, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# Colors
BLACK    = (  0,   0,   0)
WHITE    = (255, 255, 255)
DIM      = ( 25,  25,  35)
DGRAY    = ( 50,  50,  60)
GRAY     = ( 90,  90, 100)
EARTH_C  = ( 20,  80, 180)
GLOW_C   = ( 60, 140, 255)
PANEL_C  = ( 40, 100, 200)
FRAME_C  = (160, 160,  50)
SPEC_C   = ( 80, 220, 120)
STAR_C   = (150, 150, 180)

PCOLORS  = [
    ( 34,  85, 255),  # P0 blue
    (255, 215,   0),  # P1 yellow
    (155,  48, 255),  # P2 purple
    (255,  48,  48),  # P3 red
]
TEAM_COL = (255, 149, 0)

CFG      = os.path.expanduser("~/Arcade")
SCORES_F = os.path.join(os.path.dirname(__file__), "orbital_breaker_scores.json")
CTRL_F   = os.path.join(CFG, "controllers.json")

# ── Helpers ───────────────────────────────────────────────────────────────────
def polar(angle, radius):
    return (CX + math.cos(angle) * radius, CY + math.sin(angle) * radius)

def dist2(ax, ay, bx, by):
    return (ax-bx)**2 + (ay-by)**2

def reflect(vx, vy, nx, ny):
    ln = math.hypot(nx, ny)
    if ln < 0.001:
        return -vx, -vy
    nx, ny = nx/ln, ny/ln
    dot = vx*nx + vy*ny
    return vx - 2*dot*nx, vy - 2*dot*ny

def largest_gap_angle(angles):
    """Return the angle in the middle of the largest gap in a circle."""
    if not angles:
        return random.uniform(0, math.tau)
    angles = sorted(a % math.tau for a in angles)
    best, best_mid = -1, 0
    n = len(angles)
    for i in range(n):
        a1 = angles[i]
        a2 = angles[(i+1) % n]
        gap = (a2 - a1) % math.tau
        if gap > best:
            best = gap
            best_mid = (a1 + gap/2) % math.tau
    return best_mid

def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i]-a[i])*t) for i in range(3))

def add_col(c, amt):
    return tuple(min(255, v + amt) for v in c)

# ── Stars ─────────────────────────────────────────────────────────────────────
random.seed(42)
STARS = [(random.randint(0,W), random.randint(0,H),
          random.randint(1,2), random.randint(70,200)) for _ in range(220)]
random.seed()

# ── Input ─────────────────────────────────────────────────────────────────────
INACTIVITY_TIMEOUT = 60.0

class Input:
    ACTIONS = ("UP","DOWN","LEFT","RIGHT","ATTACK","JUMP")

    def __init__(self):
        self.maps = []
        self._prev = set()
        self._curr = set()
        self._last_activity = time.monotonic()
        self._load()

    def _load(self):
        try:
            with open(CTRL_F) as f:
                data = json.load(f)
            for p in data["players"]:
                m = {}
                for action, info in p["inputs"].items():
                    if info["type"] == "key":
                        m[action] = info["key"]
                self.maps.append(m)
        except Exception:
            # Fallback for 2 players
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

    def update(self, events):
        self._prev = set(self._curr)
        for e in events:
            if e.type == pygame.KEYDOWN:
                self._curr.add(e.key)
                self._last_activity = time.monotonic()
            elif e.type == pygame.KEYUP:
                self._curr.discard(e.key)

    def timed_out(self):
        return time.monotonic() - self._last_activity > INACTIVITY_TIMEOUT

    def held(self, pid, action):
        if pid >= len(self.maps): return False
        k = self.maps[pid].get(action)
        return k is not None and k in self._curr

    def just(self, pid, action):
        if pid >= len(self.maps): return False
        k = self.maps[pid].get(action)
        return k is not None and k in self._curr and k not in self._prev

    def both_buttons(self, pid):
        return self.held(pid,"ATTACK") and self.held(pid,"JUMP")

    def either_button(self, pid):
        return self.held(pid,"ATTACK") or self.held(pid,"JUMP")

    def just_either(self, pid):
        return self.just(pid,"ATTACK") or self.just(pid,"JUMP")

# ── Particles ─────────────────────────────────────────────────────────────────
class Particle:
    __slots__ = ("x","y","vx","vy","life","max_life","color","w","h")
    def __init__(self, x, y, color):
        self.x, self.y = float(x), float(y)
        a = random.uniform(0, math.tau)
        s = random.uniform(50, 210)
        self.vx, self.vy = math.cos(a)*s, math.sin(a)*s
        self.life = self.max_life = random.uniform(0.5, 1.3)
        self.color = color
        self.w = random.randint(3, 7)
        self.h = random.randint(2, 5)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, surf):
        t = max(0, self.life / self.max_life)
        col = tuple(int(c*t) for c in self.color)
        pygame.draw.rect(surf, col, (int(self.x), int(self.y), self.w, self.h))

# ── Laser Beam ────────────────────────────────────────────────────────────────
class Laser:
    def __init__(self, x1, y1, x2, y2, color):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.color = color
        self.life  = LASER_DUR

    def update(self, dt): self.life -= dt
    def alive(self): return self.life > 0

    def draw(self, surf):
        t = max(0.0, self.life / LASER_DUR)
        col = tuple(int(c*t) for c in self.color)
        pygame.draw.line(surf, col,
            (int(self.x1),int(self.y1)), (int(self.x2),int(self.y2)), 2)
        # bright core
        if t > 0.5:
            w_col = tuple(int(min(255, c + 100)*t) for c in self.color)
            pygame.draw.line(surf, w_col,
                (int(self.x1),int(self.y1)), (int(self.x2),int(self.y2)), 1)

# ── Ball ──────────────────────────────────────────────────────────────────────
class Ball:
    def __init__(self):
        a = random.uniform(0, math.tau)
        self.x  = CX + math.cos(a) * (EARTH_R + 2)
        self.y  = CY + math.sin(a) * (EARTH_R + 2)
        self.vx = math.cos(a) * BALL_SPEED
        self.vy = math.sin(a) * BALL_SPEED
        self.color    = WHITE
        self.owner_pid = -1
        self.owner_x   = CX
        self.owner_y   = CY
        self.bounces   = 0
        self.bonus     = False   # spawned from special brick

    def clamp_speed(self):
        s = math.hypot(self.vx, self.vy)
        if s > BALL_MAX_SPD:
            self.vx = self.vx/s * BALL_MAX_SPD
            self.vy = self.vy/s * BALL_MAX_SPD
        elif s < 80:
            f = 80/max(s,0.01)
            self.vx *= f
            self.vy *= f

    def move(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt

    def bounce_earth(self):
        dx = self.x - CX
        dy = self.y - CY
        d  = math.hypot(dx, dy)
        if d < EARTH_R + BALL_R:
            self.vx, self.vy = reflect(self.vx, self.vy, dx, dy)
            if d > 0:
                push = (EARTH_R + BALL_R - d) / d
                self.x += dx * push
                self.y += dy * push
            self.bounces += 1
            return True
        return False

    def alive(self):
        return math.hypot(self.x-CX, self.y-CY) <= PLAY_R + BALL_R * 2

    def draw(self, surf):
        ix, iy = int(self.x), int(self.y)
        pygame.draw.circle(surf, self.color, (ix, iy), BALL_R)
        # soft glow
        gs = BALL_R * 3
        gsurf = pygame.Surface((gs*2, gs*2), pygame.SRCALPHA)
        col_a = (*self.color, 55)
        pygame.draw.circle(gsurf, col_a, (gs, gs), gs)
        surf.blit(gsurf, (ix-gs, iy-gs), special_flags=pygame.BLEND_ADD)

# ── Brick ─────────────────────────────────────────────────────────────────────
class Brick:
    def __init__(self, target_ring, orbit_angle, special=False):
        self.ring        = target_ring
        self.orbit_angle = orbit_angle
        self.special     = special
        self.hp          = 2 if special else 1
        self.max_hp      = self.hp
        self.value       = 3 if special else 1
        self.current_r   = float(EARTH_R + 2)
        self.transiting  = True
        self.glow        = 0.0    # seconds of glow remaining after hit

    def update(self, dt):
        if self.transiting:
            self.current_r = min(self.ring.radius, self.current_r + TRANSIT_SPD * dt)
            if self.current_r >= self.ring.radius:
                self.transiting = False
        if self.glow > 0:
            self.glow = max(0, self.glow - dt)

    def hit(self):
        """Returns True if destroyed."""
        self.hp -= 1
        self.glow = 0.6
        return self.hp <= 0

    def draw_solar_panel(self, surf, x, y, rot, glowing):
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        def pt(lx, ly):
            return (int(x + cos_r*lx - sin_r*ly),
                    int(y + sin_r*lx + cos_r*ly))

        panel_c = add_col(PANEL_C, 60) if glowing else PANEL_C
        frame_c = add_col(FRAME_C, 40) if glowing else FRAME_C

        for side in (-1, 1):
            bx = side * (CORE_W//2)
            wx = side * (CORE_W//2 + WING_W)
            wp = [pt(bx,-BRICK_H//2), pt(wx,-BRICK_H//2),
                  pt(wx, BRICK_H//2), pt(bx, BRICK_H//2)]
            pygame.draw.polygon(surf, panel_c, wp)
            pygame.draw.polygon(surf, frame_c, wp, 1)
            # panel grid lines
            for gy in (-BRICK_H//4, BRICK_H//4):
                pygame.draw.line(surf, frame_c, pt(bx+2, gy), pt(wx-2, gy), 1)

        core = [pt(-CORE_W//2,-BRICK_H//2), pt(CORE_W//2,-BRICK_H//2),
                pt(CORE_W//2, BRICK_H//2), pt(-CORE_W//2, BRICK_H//2)]
        pygame.draw.polygon(surf, GRAY, core)
        pygame.draw.polygon(surf, WHITE, core, 1)

    def draw_special(self, surf, x, y, rot, glowing):
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        def pt(lx, ly):
            return (int(x + cos_r*lx - sin_r*ly),
                    int(y + sin_r*lx + cos_r*ly))

        powered = self.hp < self.max_hp
        body_c  = (150,255,150) if powered else SPEC_C
        panel_c = add_col(PANEL_C, 60) if glowing else PANEL_C

        # body sphere
        pygame.draw.circle(surf, body_c, (int(x),int(y)), 10)
        pygame.draw.circle(surf, WHITE,  (int(x),int(y)), 10, 2)

        # glow ring if powered
        if powered:
            gs = pygame.Surface((52,52), pygame.SRCALPHA)
            pygame.draw.circle(gs, (150,255,150,70), (26,26), 22)
            surf.blit(gs, (int(x)-26, int(y)-26), special_flags=pygame.BLEND_ADD)

        # wings
        for side in (-1, 1):
            ox = side * 12
            ex = side * (12 + WING_W)
            wp = [pt(ox,-7), pt(ex,-7), pt(ex,7), pt(ox,7)]
            pygame.draw.polygon(surf, panel_c, wp)
            pygame.draw.polygon(surf, FRAME_C, wp, 1)
            pygame.draw.line(surf, FRAME_C, pt(ox+WING_W//2,-7), pt(ox+WING_W//2,7), 1)

    def draw(self, surf):
        r = self.current_r if self.transiting else self.ring.radius
        x, y = polar(self.orbit_angle, r)
        rot   = self.orbit_angle
        glow  = self.glow > 0

        if self.special:
            self.draw_special(surf, x, y, rot, glow)
        else:
            self.draw_solar_panel(surf, x, y, rot, glow)

        # glow overlay
        if glow:
            t = self.glow / 0.6
            gs = pygame.Surface((60,60), pygame.SRCALPHA)
            gc = (255,200,100,int(80*t))
            pygame.draw.circle(gs, gc, (30,30), 26)
            surf.blit(gs, (int(x)-30, int(y)-30), special_flags=pygame.BLEND_ADD)

# ── Ring ──────────────────────────────────────────────────────────────────────
class Ring:
    def __init__(self, radius, ang_spd, direction):
        self.radius    = float(radius)
        self.ang_spd   = ang_spd
        self.direction = direction
        self.bricks    = []
        self._cooldown = 0.0
        self._spawn_first()

    def _spawn_first(self):
        count = max(2, int(math.tau * self.radius / ARC_SPACING))
        offset = random.uniform(0, math.tau)
        for i in range(count):
            angle = offset + math.tau * i / count
            is_special = random.random() < 0.12
            self.bricks.append(Brick(self, angle % math.tau, special=is_special))

    def _target_count(self):
        return max(1, int(math.tau * self.radius / ARC_SPACING))

    def update(self, dt):
        ang_delta = self.ang_spd * self.direction * dt
        for b in self.bricks:
            b.orbit_angle = (b.orbit_angle + ang_delta) % math.tau
            b.update(dt)

        # refill destroyed bricks
        self._cooldown -= dt
        if self._cooldown <= 0 and len(self.bricks) < self._target_count():
            angle = largest_gap_angle([b.orbit_angle for b in self.bricks])
            is_special = random.random() < 0.12
            self.bricks.append(Brick(self, angle, special=is_special))
            self._cooldown = 1.8

    def draw(self, surf):
        pygame.draw.circle(surf, DGRAY, (CX,CY), int(self.radius), 1)
        for b in self.bricks:
            b.draw(surf)

# ── Player ────────────────────────────────────────────────────────────────────
class Player:
    def __init__(self, pid, team):
        self.pid     = pid
        self.team    = team
        self.color   = TEAM_COL if team else PCOLORS[pid]
        self.angle   = math.tau * pid / 4
        self.radius  = float(PLAYER_MIN_R)
        self.cur_r   = float(EARTH_R + 2)
        self.transit = True
        self.alive   = True
        self.deaths  = 0
        self.bricks_hit = 0
        self._hit_cd = 0.0

    def respawn_cost(self):
        idx = min(self.deaths, len(RESPAWN_COSTS)-1)
        return RESPAWN_COSTS[idx]

    def pos(self):
        r = self.cur_r if self.transit else self.radius
        return polar(self.angle, r)

    def update(self, dt, inp):
        if not self.alive:
            return
        if self.transit:
            self.cur_r = min(PLAYER_MIN_R, self.cur_r + 40*dt)
            if self.cur_r >= PLAYER_MIN_R:
                self.transit = False
            return

        self._hit_cd = max(0, self._hit_cd - dt)

        if inp.held(self.pid,"LEFT"):
            self.angle += PLAYER_ANG_SPD * dt
        if inp.held(self.pid,"RIGHT"):
            self.angle -= PLAYER_ANG_SPD * dt
        if inp.held(self.pid,"UP"):
            self.radius = min(PLAYER_MAX_R, self.radius + PLAYER_RAD_SPD*dt)
        if inp.held(self.pid,"DOWN"):
            self.radius = max(PLAYER_MIN_R, self.radius - PLAYER_RAD_SPD*dt)

    def _in_hitbox(self, wx, wy, margin=0):
        px, py = self.pos()
        dx, dy = wx - px, wy - py
        cos_r, sin_r = math.cos(self.angle), math.sin(self.angle)
        lx =  dx * cos_r + dy * sin_r
        ly = -dx * sin_r + dy * cos_r
        return abs(lx) <= PLAYER_HW + margin and abs(ly) <= PLAYER_HH + margin

    def try_hit_ball(self, ball, inp, lasers):
        if not self.alive or self.transit or self._hit_cd > 0:
            return False
        px, py = self.pos()
        dx, dy   = ball.x - px, ball.y - py
        cos_r    = math.cos(self.angle)
        sin_r    = math.sin(self.angle)
        lx =  dx * cos_r + dy * sin_r   # radial  (+ = away from earth)
        ly = -dx * sin_r + dy * cos_r   # tangential
        if abs(lx) > PLAYER_HW + BALL_R or abs(ly) > PLAYER_HH + BALL_R:
            return False

        # Breakout-style: tangential hit position drives deflection angle.
        # Ball always goes inward (toward earth) after the hit.
        t   = max(-1.0, min(1.0, ly / PLAYER_HH))   # -1 .. +1 across paddle
        ang = t * math.radians(65)                   # max 65° from radial
        spd = math.hypot(ball.vx, ball.vy)

        # New velocity in local space: inward radial + tangential bias
        new_lx = -math.cos(ang) * spd   # inward  (negative = toward earth)
        new_ly =  math.sin(ang) * spd   # tangential

        # Back to world space
        ball.vx = cos_r * new_lx - sin_r * new_ly
        ball.vy = sin_r * new_lx + cos_r * new_ly

        if inp.either_button(self.pid):
            s = math.hypot(ball.vx, ball.vy)
            ball.vx = ball.vx / s * min(BALL_MAX_SPD, s * BALL_SMASH)
            ball.vy = ball.vy / s * min(BALL_MAX_SPD, s * BALL_SMASH)

        ball.color     = self.color
        ball.owner_pid = self.pid
        ball.owner_x   = px
        ball.owner_y   = py
        ball.bounces  += 1
        ball.clamp_speed()

        lasers.append(Laser(px, py,
            ball.x + ball.vx * 0.04,
            ball.y + ball.vy * 0.04, self.color))
        self._hit_cd = 0.18
        return True

    def die(self, particles):
        self.alive = False
        px, py = self.pos()
        for _ in range(30):
            particles.append(Particle(px, py, self.color))

    def respawn(self):
        self.deaths  += 1
        self.angle    = math.tau * self.pid / 4
        self.radius   = float(PLAYER_MIN_R)
        self.cur_r    = float(EARTH_R + 2)
        self.transit  = True
        self.alive    = True
        self._hit_cd  = 0.0

    def draw(self, surf):
        if not self.alive:
            return
        x, y = self.pos()
        cos_r, sin_r = math.cos(self.angle), math.sin(self.angle)
        col = self.color

        def pt(lx, ly):
            return (int(x + cos_r*lx - sin_r*ly),
                    int(y + sin_r*lx + cos_r*ly))

        # Flat 1:3 panel body (20px radial × 60px tangential)
        body = [pt(-PLAYER_HW, -PLAYER_HH), pt(PLAYER_HW, -PLAYER_HH),
                pt(PLAYER_HW,  PLAYER_HH),  pt(-PLAYER_HW, PLAYER_HH)]
        pygame.draw.polygon(surf, DGRAY, body)
        pygame.draw.polygon(surf, col, body, 2)

        # Panel cell dividers
        for gy in (-PLAYER_HH // 3, PLAYER_HH // 3):
            pygame.draw.line(surf, col, pt(-PLAYER_HW + 2, gy), pt(PLAYER_HW - 2, gy), 1)

        # Central hub
        hub = [pt(-4, -5), pt(4, -5), pt(4, 5), pt(-4, 5)]
        pygame.draw.polygon(surf, GRAY, hub)
        pygame.draw.polygon(surf, WHITE, hub, 1)

        # Player label (radially outward)
        label = FONTS[14].render(f"P{self.pid+1}", False, col)
        lw, lh = label.get_size()
        surf.blit(label, (int(x + cos_r*(PLAYER_HW+5)) - lw//2,
                          int(y + sin_r*(PLAYER_HW+5)) - lh//2))

# ── Economy ───────────────────────────────────────────────────────────────────
class Economy:
    def __init__(self):
        self.balance = START_MONEY
        self.earned  = 0

    def award(self, n):
        self.balance += n
        self.earned  += n

    def can_afford(self, cost):
        return self.balance >= cost

    def spend(self, cost):
        self.balance -= cost

# ── Leaderboard ───────────────────────────────────────────────────────────────
class Leaderboard:
    def __init__(self):
        self.solo = []
        self.team = []
        self._load()

    def _load(self):
        try:
            with open(SCORES_F) as f:
                d = json.load(f)
            self.solo = d.get("solo",[])
            self.team = d.get("team",[])
        except Exception:
            pass

    def _save(self):
        os.makedirs(CFG, exist_ok=True)
        with open(SCORES_F,"w") as f:
            json.dump({"solo":self.solo,"team":self.team}, f, indent=2)

    def add_solo(self, entry):
        self.solo.append(entry)
        self.solo.sort(key=lambda e: e["money"], reverse=True)
        self.solo = self.solo[:6]
        self._save()

    def add_team(self, entry):
        self.team.append(entry)
        self.team.sort(key=lambda e: e["money"], reverse=True)
        self.team = self.team[:6]
        self._save()

# ── Background ────────────────────────────────────────────────────────────────
def draw_bg(surf):
    surf.fill(BLACK)
    for sx, sy, sr, sb in STARS:
        pygame.draw.circle(surf, (sb,sb,sb+20), (sx,sy), sr)

def draw_earth(surf):
    pygame.draw.circle(surf, EARTH_C,  (CX,CY), EARTH_R)
    pygame.draw.circle(surf, GLOW_C,   (CX,CY), EARTH_R, 3)
    # highlight
    pygame.draw.circle(surf, add_col(EARTH_C,30), (CX-12,CY-12), 14)
    # zone boundary (faint dashed look via circle)
    pygame.draw.circle(surf, DGRAY, (CX,CY), int(ZONE_R), 1)

# ── Game ──────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        self.inp = Input()
        self.lb  = Leaderboard()
        self._to_attract()

    # ── State transitions ─────────────────────────────────────────────────────
    def _to_attract(self):
        self.state   = "ATTRACT"
        self._joined = {}    # pid -> None | "choosing" | "solo" | "team"
        self._reset()

    def _reset(self):
        self.rings     = []
        self.balls     = []
        self.particles = []
        self.lasers    = []
        self.players   = {}
        self.economies = {}
        self.team_eco  = None
        self._launch_queue = []
        self._lives        = 0
        self._next_pid_idx = 0
        self.game_time     = 0.0
        self.bricks_broken = 0
        self._spawn_rings()

    def _to_playing(self):
        self._reset()
        confirmed = {p:m for p,m in self._joined.items() if m in ("solo","team")}
        team_eco = None
        for pid, mode in confirmed.items():
            if mode == "team":
                if team_eco is None:
                    team_eco = Economy()
                eco = team_eco
            else:
                eco = Economy()
            self.economies[pid] = eco
            self.players[pid]   = Player(pid, mode=="team")
        self.team_eco = team_eco

        # Players start at orbit — no transit animation
        for player in self.players.values():
            player.transit = False
            player.cur_r   = float(PLAYER_MIN_R)

        # 3 shared lives; one ball per player launches at game start
        self._lives = BALL_LIVES
        pids = list(self.players.keys())
        for i, pid in enumerate(pids):
            self._launch_queue.append((1.5 + i * 0.5, pid))

        self.state = "PLAYING"

    def _to_game_over(self):
        self.state    = "GAME_OVER"
        self._go_cd   = 3.5
        self._ne_queue  = []
        self._team_entry = None
        self._build_name_queue()

    def _to_leaderboard(self):
        self.state  = "LEADERBOARD"
        self._lb_cd = 18.0

    # ── Ring / ball helpers ───────────────────────────────────────────────────
    def _spawn_rings(self):
        for r in RING_RADII:
            spd = random.uniform(0.15, 0.55)
            self.rings.append(Ring(r, spd, random.choice([-1, 1])))

    def _add_ball(self, target_pid=None):
        ball = Ball()
        if target_pid is not None and target_pid in self.players:
            player = self.players[target_pid]
            px, py = player.pos()
            dx, dy = CX - px, CY - py          # inward toward earth
            d = math.hypot(dx, dy)
            if d > 0.01:
                ux, uy = dx / d, dy / d
                # spawn just past the inner face so the ball is outside the hitbox
                offset = PLAYER_HW + BALL_R + 4
                ball.x, ball.y   = px + ux * offset, py + uy * offset
                ball.vx, ball.vy = ux * BALL_SPEED,  uy * BALL_SPEED
                ball.owner_pid   = target_pid
                ball.owner_x     = px
                ball.owner_y     = py
                ball.color       = player.color
        self.balls.append(ball)

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        while True:
            dt = min(clock.tick(60)/1000, 0.05)
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

            self.inp.update(events)

            if self.inp.timed_out():
                pygame.quit(); sys.exit()

            if   self.state == "ATTRACT":     self._attract(dt)
            elif self.state == "PLAYING":     self._playing(dt)
            elif self.state == "GAME_OVER":   self._game_over(dt)
            elif self.state == "NAME_ENTRY":  self._name_entry()
            elif self.state == "LEADERBOARD": self._leaderboard(dt)

            pygame.display.flip()

    # ── ATTRACT ───────────────────────────────────────────────────────────────
    def _attract(self, dt):
        # quit
        for pid in range(4):
            if self.inp.both_buttons(pid):
                pygame.quit(); sys.exit()

        # update joining
        for pid in range(4):
            st = self._joined.get(pid)
            if st is None:
                if self.inp.just(pid, "ATTACK"):
                    self._joined[pid] = "choosing"
            elif st == "choosing":
                if self.inp.held(pid,"UP"):
                    self._joined[pid] = "team"
                elif self.inp.held(pid,"DOWN"):
                    self._joined[pid] = "solo"
            elif st in ("solo","team"):
                pass  # confirmed

        confirmed = {p:m for p,m in self._joined.items() if m in ("solo","team")}
        if confirmed:
            for pid in confirmed:
                if self.inp.just_either(pid):
                    self._to_playing()
                    return

        draw_bg(screen)
        draw_earth(screen)

        blit(screen,"ORBITAL BREAKER",60,PCOLORS[0],(CX,H//4))
        blit(screen,"A SPACE LASER BRICK-BREAKER",18,GRAY,(CX,H//4+75))
        blit(screen,"PRESS ATTACK TO JOIN",18,WHITE,(CX,H//4+110))

        for pid in range(4):
            col = PCOLORS[pid]
            st  = self._joined.get(pid)
            y   = H//2 + pid*44
            if st is None:
                blit(screen,f"P{pid+1}  PRESS ATTACK",14,DGRAY,(CX,y))
            elif st == "choosing":
                blit(screen,f"P{pid+1}  HOLD UP=TEAM  DOWN=SOLO",14,col,(CX,y))
            elif st == "team":
                blit(screen,f"P{pid+1}  TEAM  (ATTACK/JUMP TO START)",14,TEAM_COL,(CX,y))
            else:
                blit(screen,f"P{pid+1}  SOLO  (ATTACK/JUMP TO START)",14,col,(CX,y))

        if confirmed:
            blit(screen,"PRESS ATTACK OR JUMP TO LAUNCH",24,WHITE,(CX,H-80))

    # ── PLAYING ───────────────────────────────────────────────────────────────
    def _playing(self, dt):
        self.game_time += dt

        # update rings
        for ring in self.rings:
            ring.update(dt)

        # update effects
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles: p.update(dt)
        self.lasers = [l for l in self.lasers if l.alive()]
        for l in self.lasers: l.update(dt)

        # update players
        for p in self.players.values():
            p.update(dt, self.inp)

        # update balls + collisions
        dead_balls = []
        for ball in self.balls:
            ball.move(dt)
            ball.bounce_earth()
            ball.clamp_speed()

            # player hits
            for player in self.players.values():
                if player.try_hit_ball(ball, self.inp, self.lasers):
                    break

            # brick collisions
            for ring in self.rings:
                for brick in ring.bricks:
                    if brick.transiting:
                        continue
                    bx, by = polar(brick.orbit_angle, ring.radius)
                    if dist2(ball.x, ball.y, bx, by) < (BALL_R + BRICK_COL_R)**2:
                        # laser beam
                        self.lasers.append(Laser(
                            ball.owner_x, ball.owner_y, bx, by,
                            ball.color))

                        destroyed = brick.hit()
                        ball.bounces += 1

                        # reflect
                        ball.vx, ball.vy = reflect(
                            ball.vx, ball.vy, ball.x-bx, ball.y-by)
                        ball.clamp_speed()

                        if destroyed:
                            ring.bricks.remove(brick)
                            self.bricks_broken += 1
                            # award money
                            pid = ball.owner_pid
                            if pid >= 0 and pid in self.players:
                                eco = self.economies[pid]
                                eco.award(brick.value)
                                self.players[pid].bricks_hit += 1
                            # confetti
                            cols = [PANEL_C, FRAME_C, WHITE, ball.color]
                            for _ in range(20):
                                self.particles.append(
                                    Particle(bx, by, random.choice(cols)))
                            # bonus ball from special brick
                            if brick.special:
                                b2 = Ball()
                                b2.x, b2.y = bx, by
                                b2.bonus = True
                                ang = random.uniform(0, math.tau)
                                b2.vx = math.cos(ang)*BALL_SPEED
                                b2.vy = math.sin(ang)*BALL_SPEED
                                self.balls.append(b2)
                        break   # one brick collision per ball per frame

            if not ball.alive():
                dead_balls.append(ball)

        pids = list(self.players.keys())
        for b in dead_balls:
            if b.bonus:
                self.balls.remove(b)
                continue
            self.balls.remove(b)
            self._lives -= 1
            if self._lives > 0:
                pid = pids[self._next_pid_idx % len(pids)]
                self._next_pid_idx += 1
                self._launch_queue.append((self.game_time + 1.5, pid))

        # fire any queued ball launches
        for i in range(len(self._launch_queue) - 1, -1, -1):
            t, pid = self._launch_queue[i]
            if self.game_time >= t:
                self._add_ball(pid)
                self._launch_queue.pop(i)

        # brick hits player → player dies
        for player in self.players.values():
            if not player.alive or player.transit:
                continue
            px, py = player.pos()
            for ring in self.rings:
                for brick in ring.bricks:
                    if brick.transiting:
                        continue
                    bx, by = polar(brick.orbit_angle, ring.radius)
                    if player._in_hitbox(bx, by, BRICK_COL_R):
                        player.die(self.particles)

        # handle dead players
        for pid, player in self.players.items():
            if not player.alive:
                eco  = self.economies[pid]
                cost = player.respawn_cost()
                if eco.can_afford(cost):
                    eco.spend(cost)
                    player.respawn()

        # game over: lives exhausted and no balls remain
        if self._lives <= 0 and not self.balls and not self._launch_queue:
            self._to_game_over()
            return
        if self.players and all(not p.alive for p in self.players.values()):
            can_any = any(self.economies[pid].can_afford(p.respawn_cost())
                          for pid, p in self.players.items())
            if not can_any:
                self._to_game_over()
                return

        # draw
        draw_bg(screen)
        draw_earth(screen)
        for ring in self.rings:
            ring.draw(screen)
        for l in self.lasers:
            l.draw(screen)
        for ball in self.balls:
            ball.draw(screen)
        for p in self.particles:
            p.draw(screen)
        for player in self.players.values():
            player.draw(screen)
        self._draw_hud()

    def _draw_hud(self):
        # player stats down left side
        for i, (pid, player) in enumerate(self.players.items()):
            eco = self.economies[pid]
            col = player.color
            status = "" if player.alive else " [DEAD]"
            blit(screen,
                f"P{pid+1}  ${eco.balance:>4}  +${eco.earned}{status}",
                14, col, (16, 12 + i*28), anchor="topleft")

        # lives + active balls (top right)
        lives_str = "o " * self._lives
        blit(screen, f"{lives_str.strip()}  [{len(self.balls)}]", 14, WHITE,
             (W-16, 12), anchor="topright")

        # timer (top center)
        m = int(self.game_time)//60
        s = int(self.game_time)%60
        blit(screen, f"{m:02d}:{s:02d}", 18, WHITE, (CX, 14))

    # ── GAME OVER ─────────────────────────────────────────────────────────────
    def _game_over(self, dt):
        self._go_cd -= dt

        # any player holds both buttons to quit
        for pid in range(4):
            if self.inp.both_buttons(pid):
                pygame.quit(); sys.exit()

        draw_bg(screen)
        draw_earth(screen)
        for ring in self.rings: ring.draw(screen)
        for p in self.particles: p.update(dt)
        for p in self.particles: p.draw(screen)

        blit(screen, "GAME OVER", 60, (220,50,50), (CX, H//3))

        m = int(self.game_time)//60
        s = int(self.game_time)%60
        blit(screen, f"TIME  {m:02d}:{s:02d}", 18, WHITE, (CX, H//2 - 50))

        for i,(pid,player) in enumerate(self.players.items()):
            eco = self.economies[pid]
            blit(screen, f"P{pid+1}  ${eco.earned} earned  {player.bricks_hit} bricks",
                 18, player.color, (CX, H//2 + i*36))

        blit(screen, "HOLD BOTH BUTTONS TO QUIT", 14, GRAY, (CX, H - 60))

        if self._go_cd <= 0:
            if self._ne_queue:
                self._next_ne()
                self.state = "NAME_ENTRY"
            else:
                self._to_leaderboard()

    def _build_name_queue(self):
        team_added = False
        for pid, player in self.players.items():
            eco = self.economies[pid]
            if eco.earned > 0:
                if player.team:
                    if not team_added:
                        team_pids = [p for p,pl in self.players.items() if pl.team]
                        for tp in team_pids:
                            self._ne_queue.append(("team", tp))
                        team_added = True
                else:
                    self._ne_queue.append(("solo", pid))

    def _next_ne(self):
        self._ne_mode, self._ne_pid = self._ne_queue.pop(0)
        self._ne_chars  = [0,0,0]   # 0..25 → A..Z
        self._ne_cursor = 0

    # ── NAME ENTRY ────────────────────────────────────────────────────────────
    def _name_entry(self):
        pid = self._ne_pid
        player = self.players[pid]
        col    = player.color

        if self.inp.just(pid,"UP"):
            self._ne_chars[self._ne_cursor] = (self._ne_chars[self._ne_cursor]-1)%26
        if self.inp.just(pid,"DOWN"):
            self._ne_chars[self._ne_cursor] = (self._ne_chars[self._ne_cursor]+1)%26
        if self.inp.just_either(pid) or self.inp.just(pid,"RIGHT"):
            self._ne_cursor += 1
            if self._ne_cursor >= 3:
                self._save_name()
                return

        draw_bg(screen)

        mode_str = "TEAM" if self._ne_mode == "team" else "SOLO"
        blit(screen, f"ENTER NAME  P{pid+1}  {mode_str}", 36, col, (CX, H//4))

        for i, ch in enumerate(self._ne_chars):
            bx = CX + (i-1)*90
            active = (i == self._ne_cursor)
            box_col = col if active else GRAY
            pygame.draw.rect(screen, box_col, (bx-32,H//2-40,64,80),
                             3 if active else 1)
            blit(screen, chr(65+ch), 60, WHITE if active else GRAY, (bx,H//2))

        blit(screen,"UP/DOWN CHANGE   ATTACK NEXT",14,DGRAY,(CX,H//2+80))

    def _save_name(self):
        name = "".join(chr(65+c) for c in self._ne_chars)
        pid  = self._ne_pid
        eco  = self.economies[pid]
        m,s  = int(self.game_time)//60, int(self.game_time)%60
        entry = {"name":name,"money":eco.earned,
                 "bricks":self.bricks_broken,"time":f"{m:02d}:{s:02d}"}

        if self._ne_mode == "team":
            if self._team_entry is None:
                self._team_entry = {**entry, "names":[name]}
            else:
                self._team_entry["names"].append(name)
            team_pids = [p for p,pl in self.players.items() if pl.team]
            if len(self._team_entry["names"]) >= len(team_pids):
                self.lb.add_team(self._team_entry)
                self._team_entry = None
        else:
            self.lb.add_solo(entry)

        if self._ne_queue:
            self._next_ne()
        else:
            self._to_leaderboard()

    # ── LEADERBOARD ───────────────────────────────────────────────────────────
    def _leaderboard(self, dt):
        for pid in range(4):
            if self.inp.both_buttons(pid):
                pygame.quit(); sys.exit()

        self._lb_cd -= dt
        if self._lb_cd <= 0:
            self._to_attract()
            return

        draw_bg(screen)
        blit(screen,"LEADERBOARD",36,WHITE,(CX,45))

        def col_header(x, label, col):
            blit(screen, label, 24, col, (x, 110))
            blit(screen,"NAME   MONEY  BRICKS  TIME",11,GRAY,(x,145))

        sx = W//4
        tx = W*3//4

        col_header(sx, "SOLO",  PCOLORS[0])
        col_header(tx, "TEAM",  TEAM_COL)

        for i, e in enumerate(self.lb.solo):
            blit(screen,
                f"{e['name']}  ${e['money']:>5}  {e['bricks']:>5}  {e['time']}",
                14, WHITE, (sx, 175 + i*38))

        for i, e in enumerate(self.lb.team):
            names = "/".join(e.get("names",["???"])[:4])
            blit(screen,
                f"{names}  ${e['money']:>5}  {e['bricks']:>5}  {e['time']}",
                14, TEAM_COL, (tx, 175 + i*38))

        blit(screen, f"RETURNING IN {max(0,int(self._lb_cd))}s",
             14, DGRAY, (CX, H-35))

if __name__ == "__main__":
    Game().run()
