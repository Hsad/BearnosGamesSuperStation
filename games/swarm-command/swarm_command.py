#!/usr/bin/env python3
import pygame, sys, json, math, random, os, time

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
W, H   = screen.get_size()
CX, CY = W // 2, H // 2
clock  = pygame.time.Clock()

_FONT_PATH = os.path.expanduser("~/.local/share/fonts/DepartureMono-Regular.otf")
def _f(sz):
    return (pygame.font.Font(_FONT_PATH, sz) if os.path.exists(_FONT_PATH)
            else pygame.font.SysFont("monospace", sz, bold=True))
FONTS = {s: _f(s) for s in (72, 48, 36, 24, 18, 14, 11)}

def blit(surf, text, size, color, pos, anchor="center"):
    s = FONTS[size].render(str(text), False, color)
    surf.blit(s, s.get_rect(**{anchor: pos}))

PCOLORS = [
    ( 30, 130, 255),
    (255, 210,  40),
    (150,  60, 210),
    (220,  40,  40),
]
ROLES   = ["PILOT", "WEAPONS", "SHIELDS", "ENGINES"]
HINTS   = [
    "MOVE: stick  DASH: JUMP",
    "AIM: stick   FIRE: ATTACK",
    "ARC: stick   BLOCK: JUMP",
    "POWER: U/D   BOOST: ATTACK",
]

SX_MIN, SX_MAX = 160, 1760
SY_MIN, SY_MAX = 80,  1000

BULLET_SPEED   = 750
FIRE_CD_NORM   = 0.22
FIRE_CD_FAST   = 0.10
SHIP_SPEED_BASE = 280
DASH_SPEED     = 700
DASH_DUR       = 0.18
DASH_CD        = 1.2
SHIELD_ARC     = 110
SHIELD_CHARGES = 3
SHIELD_REGEN   = 5.0
OVERDRIVE_DUR  = 2.5
OVERDRIVE_CD   = 8.0

WAVES = [
    [("drone", 4)],
    [("drone", 5), ("beetle", 2)],
    [("drone", 6), ("beetle", 2), ("shooter", 2)],
    [("drone", 7), ("beetle", 3), ("shooter", 2), ("hornet", 2)],
    [("drone", 8), ("beetle", 3), ("shooter", 3), ("hornet", 3)],
    [("drone", 10), ("beetle", 4), ("shooter", 3), ("hornet", 4)],
    [("drone", 12), ("beetle", 5), ("shooter", 4), ("hornet", 5)],
    "BOSS",
]

ENEMY_DEFS = {
    "drone":   {"hp": 1, "speed": 95,  "radius": 18, "color": (180, 100, 220), "score": 10},
    "beetle":  {"hp": 3, "speed": 62,  "radius": 28, "color": ( 80, 210,  90), "score": 30},
    "shooter": {"hp": 2, "speed": 52,  "radius": 22, "color": (220, 160,  50), "score": 25},
    "hornet":  {"hp": 1, "speed": 150, "radius": 15, "color": (220,  90,  90), "score": 20},
}


# ── Input ────────────────────────────────────────────────────────────────────

class Input:
    INACTIVITY_TIMEOUT = 60.0

    def __init__(self):
        self.maps  = []
        self._prev = set()
        self._curr = set()
        self._last_activity = time.monotonic()
        ctrl = os.path.join(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__)))), "config", "controllers.json")
        try:
            data = json.load(open(ctrl))
            for p in data["players"]:
                self.maps.append({a: v["key"] for a, v in p["inputs"].items()
                                  if v["type"] == "key"})
        except Exception:
            self.maps = [
                {"UP":1073741906,"DOWN":1073741905,"LEFT":1073741904,
                 "RIGHT":1073741903,"ATTACK":1073742050,"JUMP":1073742048},
                {"UP":114,"DOWN":102,"LEFT":100,
                 "RIGHT":103,"ATTACK":115,"JUMP":97},
                {"UP":105,"DOWN":107,"LEFT":106,
                 "RIGHT":108,"ATTACK":1073742053,"JUMP":1073742052},
                {"UP":121,"DOWN":110,"LEFT":118,
                 "RIGHT":117,"ATTACK":101,"JUMP":98},
            ]

    def pump(self, events):
        self._prev = set(self._curr)
        for e in events:
            if e.type == pygame.KEYDOWN:
                self._curr.add(e.key)
                self._last_activity = time.monotonic()
            elif e.type == pygame.KEYUP:
                self._curr.discard(e.key)

    def reset_activity(self): self._last_activity = time.monotonic()
    def timed_out(self): return time.monotonic() - self._last_activity > self.INACTIVITY_TIMEOUT

    def held(self, pid, act):
        k = self.maps[pid].get(act) if pid < len(self.maps) else None
        return k is not None and k in self._curr

    def just(self, pid, act):
        k = self.maps[pid].get(act) if pid < len(self.maps) else None
        return k is not None and k in self._curr and k not in self._prev

    def any_just(self, pid):
        return any(self.just(pid, a)
                   for a in ("UP","DOWN","LEFT","RIGHT","JUMP","ATTACK"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def rand_edge(margin=80):
    side = random.randint(0, 3)
    if side == 0: return random.randint(0, W), -margin
    if side == 1: return random.randint(0, W), H + margin
    if side == 2: return -margin, random.randint(0, H)
    return W + margin, random.randint(0, H)

def draw_googly_eyes(surf, cx, cy, radius, angle_to_target):
    er = max(4, int(radius * 0.28))
    perp = angle_to_target + math.pi / 2
    offset = radius * 0.38
    back  = radius * 0.15
    for sign in (1, -1):
        ex = cx + math.cos(perp) * offset * sign - math.cos(angle_to_target) * back
        ey = cy + math.sin(perp) * offset * sign - math.sin(angle_to_target) * back
        pygame.draw.circle(surf, (255, 255, 255), (int(ex), int(ey)), er)
        px = int(ex + math.cos(angle_to_target) * er * 0.45)
        py = int(ey + math.sin(angle_to_target) * er * 0.45)
        pygame.draw.circle(surf, (15, 15, 15), (px, py), max(2, er // 2))


# ── Stars / nebula ────────────────────────────────────────────────────────────

class Star:
    def __init__(self):
        self.x = random.randint(0, W)
        self.y = random.randint(0, H)
        self.r = random.randint(1, 3)
        self.bright = random.randint(80, 210)
        self.phase  = random.uniform(0, math.pi * 2)
        self.speed  = random.uniform(1, 4)

    def draw(self, surf, dt):
        self.phase += self.speed * dt
        b = int(self.bright + math.sin(self.phase) * 40)
        b = max(60, min(255, b))
        pygame.draw.circle(surf, (b, b, b), (self.x, self.y), self.r)

def build_nebula():
    surf = pygame.Surface((W, H))
    surf.fill((8, 5, 20))
    for _ in range(14):
        cx = random.randint(0, W)
        cy = random.randint(0, H)
        r  = random.randint(120, 380)
        col = random.choice([(40, 0, 80), (0, 20, 60), (60, 10, 40), (10, 40, 70)])
        ns = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        for dr in range(r, 0, -30):
            a = max(0, int(40 * (1 - dr / r)))
            pygame.draw.circle(ns, (*col, a), (r, r), dr)
        surf.blit(ns, (cx - r, cy - r))
    return surf


# ── Projectiles ───────────────────────────────────────────────────────────────

class Bullet:
    def __init__(self, x, y, dx, dy):
        self.x, self.y = x, y
        self.dx, self.dy = dx, dy
        self.dead = False

    def update(self, dt):
        self.x += self.dx * BULLET_SPEED * dt
        self.y += self.dy * BULLET_SPEED * dt
        if not (-80 < self.x < W+80 and -80 < self.y < H+80):
            self.dead = True

    def draw(self, surf):
        gx, gy = int(self.x), int(self.y)
        tx = int(self.x - self.dx * 18)
        ty = int(self.y - self.dy * 18)
        pygame.draw.line(surf, (150, 255, 150), (tx, ty), (gx, gy), 3)
        pygame.draw.circle(surf, (220, 255, 220), (gx, gy), 5)


class EBullet:
    def __init__(self, x, y, dx, dy, speed=220):
        self.x, self.y = x, y
        self.dx, self.dy = dx, dy
        self.speed = speed
        self.dead  = False
        self.t     = 0.0

    def update(self, dt):
        self.t += dt
        self.x += self.dx * self.speed * dt
        self.y += self.dy * self.speed * dt
        if not (-80 < self.x < W+80 and -80 < self.y < H+80):
            self.dead = True

    def draw(self, surf):
        gx, gy = int(self.x), int(self.y)
        pulse = 5 + int(math.sin(self.t * 12) * 2)
        pygame.draw.circle(surf, (255,  80,  80), (gx, gy), pulse + 2)
        pygame.draw.circle(surf, (255, 200,  50), (gx, gy), pulse - 1)


# ── Power-ups ─────────────────────────────────────────────────────────────────

class PowerUp:
    KINDS   = ["shield", "weapon", "engine", "repair"]
    COLORS  = {"shield": (150, 60, 210), "weapon": (255, 210, 40),
               "engine": (220, 40, 40),  "repair": (50, 220, 100)}
    WEIGHTS = [3, 3, 2, 4]

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.kind     = random.choices(self.KINDS, weights=self.WEIGHTS)[0]
        self.color    = self.COLORS[self.kind]
        self.dead     = False
        self.lifetime = 9.0
        self.t        = 0.0

    def update(self, dt):
        self.t += dt
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.dead = True

    def draw(self, surf):
        pulse = 0.75 + 0.25 * math.sin(self.t * 5)
        r  = int(15 * pulse)
        x, y = int(self.x), int(self.y)
        pygame.draw.circle(surf, self.color, (x, y), r)
        pygame.draw.circle(surf, (255, 255, 255), (x, y), r, 2)
        k = self.kind
        if k == "shield":
            pygame.draw.arc(surf, (255,255,255),
                            (x-7, y-7, 14, 14), 0.2, math.pi - 0.2, 2)
        elif k == "weapon":
            pygame.draw.line(surf, (255,255,255), (x-7,y),(x+7,y), 2)
            pygame.draw.line(surf, (255,255,255), (x,y-7),(x,y+7), 2)
        elif k == "engine":
            pygame.draw.polygon(surf, (255,255,255),
                                [(x,y-7),(x+6,y+5),(x-6,y+5)])
        elif k == "repair":
            pygame.draw.line(surf, (255,255,255), (x-6,y),(x+6,y), 3)
            pygame.draw.line(surf, (255,255,255), (x,y-6),(x,y+6), 3)
        # Fading timer ring
        ratio = self.lifetime / 9.0
        if ratio < 0.4:
            pygame.draw.arc(surf, (*self.color, 180),
                            (x-18, y-18, 36, 36),
                            0, ratio / 0.4 * math.pi * 2, 3)


# ── Enemies ───────────────────────────────────────────────────────────────────

class Enemy:
    def __init__(self, x, y, kind, speed_mult=1.0):
        self.x, self.y = float(x), float(y)
        self.kind = kind
        d = ENEMY_DEFS[kind]
        self.hp        = d["hp"]
        self.max_hp    = d["hp"]
        self.speed     = d["speed"] * speed_mult
        self.radius    = d["radius"]
        self.color     = d["color"]
        self.score_val = d["score"]
        self.dead      = False
        self.hit_flash = 0.0
        self.t         = random.uniform(0, math.pi * 2)
        self.wobble    = random.uniform(0.6, 2.2)
        self.shoot_cd  = random.uniform(2.5, 4.0)
        self.shoot_t   = random.uniform(1.5, 3.0)

    def update(self, dt, sx, sy, ebullets):
        self.t += dt
        self.hit_flash = max(0.0, self.hit_flash - dt)
        dx = sx - self.x
        dy = sy - self.y
        dist = math.hypot(dx, dy) or 1
        nx, ny = dx / dist, dy / dist
        perp_x = -ny * math.sin(self.t * self.wobble * 3) * 0.25
        perp_y =  nx * math.sin(self.t * self.wobble * 3) * 0.25
        self.x += (nx + perp_x) * self.speed * dt
        self.y += (ny + perp_y) * self.speed * dt
        if self.kind == "shooter":
            self.shoot_t -= dt
            if self.shoot_t <= 0:
                self.shoot_t  = self.shoot_cd + random.uniform(-0.5, 0.5)
                ebullets.append(EBullet(self.x, self.y, nx, ny))

    def take_hit(self, dmg=1):
        self.hp -= dmg
        self.hit_flash = 0.15
        if self.hp <= 0:
            self.dead = True

    def draw(self, surf, sx, sy):
        x, y = int(self.x), int(self.y)
        r = self.radius
        col = (255, 255, 255) if self.hit_flash > 0 else self.color
        wx = int(math.sin(self.t * 7) * 2)
        wy = int(math.cos(self.t * 5) * 2)
        a2s = math.atan2(sy - self.y, sx - self.x)

        if self.kind == "drone":
            pts = [(x+wx, y-r+wy), (x+r-wx, y+wy), (x-wx, y+r-wy), (x-r+wx, y+wy)]
            pygame.draw.polygon(surf, col, pts)
            # Wings
            pygame.draw.ellipse(surf, col,
                (x - r*2 + wx, y - r//2 + wy, r, r // 2))
            pygame.draw.ellipse(surf, col,
                (x + r + wx,   y - r//2 + wy, r, r // 2))
        elif self.kind == "beetle":
            pygame.draw.ellipse(surf, col,
                (x - r + wx, y - int(r * 0.7) + wy, r*2, int(r * 1.4)))
            dark = tuple(max(0, c - 50) for c in col)
            for i in (1, 2):
                yy = y - int(r * 0.7) + wy + int(r * 1.4 * i // 3)
                pygame.draw.line(surf, dark, (x - r + wx, yy), (x + r + wx, yy), 2)
        elif self.kind == "shooter":
            pts = [(x+wx, y-r+wy), (x+int(r*.85)+wx, y+r+wy), (x-int(r*.85)+wx, y+r+wy)]
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.line(surf, col,
                (x - r//3 + wx, y - r + wy), (x - r//2 + wx, y - r - 12 + wy), 2)
            pygame.draw.line(surf, col,
                (x + r//3 + wx, y - r + wy), (x + r//2 + wx, y - r - 12 + wy), 2)
            charge = 1.0 - max(0, self.shoot_t) / self.shoot_cd
            if charge > 0:
                pygame.draw.circle(surf, (255, 120, 50), (x, y), max(2, int(r * 0.35 * charge)))
        elif self.kind == "hornet":
            pts = [(x+wx, y-r+wy), (x+r//2+wx, y+wy), (x+wx, y+r+wy), (x-r//2+wx, y+wy)]
            pygame.draw.polygon(surf, col, pts)
            for i in range(1, 4):
                xi = x - r + i * r // 2 + wx
                pygame.draw.line(surf, (255, 255, 255),
                    (xi, y - r//2 + wy), (xi, y + r//2 + wy), 1)

        draw_googly_eyes(surf, self.x, self.y, r * 0.8, a2s)

        if self.max_hp > 1 and self.hp < self.max_hp:
            bx = x - r
            pygame.draw.rect(surf, (80, 0, 0), (bx, y - r - 10, r*2, 5))
            pygame.draw.rect(surf, (200, 50, 50),
                (bx, y - r - 10, int(r*2 * self.hp / self.max_hp), 5))


# ── Boss ──────────────────────────────────────────────────────────────────────

class BossArm:
    def __init__(self, base_angle, dist):
        self.base_angle = base_angle
        self.angle = float(base_angle)
        self.dist  = dist
        self.hp    = 8
        self.max_hp = 8
        self.dead  = False
        self.t     = random.uniform(0, math.pi*2)
        self.x = self.y = 0.0

    def update(self, dt, bx, by):
        self.t += dt * 0.8
        self.angle = self.base_angle + math.sin(self.t) * 0.4
        self.x = bx + math.cos(self.angle) * self.dist
        self.y = by + math.sin(self.angle) * self.dist

    def draw(self, surf, bx, by):
        sx, sy = int(self.x), int(self.y)
        ibx, iby = int(bx), int(by)
        # Tentacle spine
        segs = 8
        prev = (ibx, iby)
        for i in range(1, segs + 1):
            t = i / segs
            cx_ = int(bx + (self.x - bx) * t)
            cy_ = int(by + (self.y - by) * t)
            sag = int(math.sin(self.t + i) * 6)
            pygame.draw.line(surf, (80, 30, 120), prev, (cx_ + sag, cy_), 5)
            prev = (cx_ + sag, cy_)
        # End bulb
        ratio = self.hp / self.max_hp
        col = (int(220 * ratio), int(40 * ratio), int(200 * ratio))
        pygame.draw.circle(surf, col, (sx, sy), 34)
        pygame.draw.circle(surf, (200, 100, 255), (sx, sy), 34, 3)
        draw_googly_eyes(surf, self.x, self.y, 22, self.base_angle + math.pi)


class Boss:
    def __init__(self):
        self.x = float(W + 200)
        self.y = float(CY)
        self.hp     = 40
        self.max_hp = 40
        self.t      = 0.0
        self.dead   = False
        self.arms   = [BossArm(i * math.pi / 2, 170) for i in range(4)]
        self.shoot_t = 2.0
        self.tx, self.ty = float(CX), float(CY)
        self.retarget_t  = 0.0
        self.entry_done  = False
        self.entry_t     = 3.5

    @property
    def core_exposed(self):
        return all(a.dead for a in self.arms)

    def update(self, dt, sx, sy, ebullets):
        self.t += dt
        if not self.entry_done:
            self.entry_t -= dt
            self.x = max(CX + 120, self.x - 200 * dt)
            if self.entry_t <= 0:
                self.entry_done = True
        else:
            self.retarget_t -= dt
            if self.retarget_t <= 0:
                self.retarget_t = random.uniform(3, 7)
                self.tx = random.uniform(400, 1520)
                self.ty = random.uniform(200, 880)
            tdx = self.tx - self.x
            tdy = self.ty - self.y
            td  = math.hypot(tdx, tdy) or 1
            spd = 50 if not self.core_exposed else 90
            self.x += tdx / td * spd * dt
            self.y += tdy / td * spd * dt
            self.shoot_t -= dt
            if self.shoot_t <= 0:
                count = 10 if self.core_exposed else 6
                self.shoot_t = 1.2 if self.core_exposed else 2.2
                for i in range(count):
                    a = self.t * 0.5 + i * math.pi * 2 / count
                    ebullets.append(EBullet(self.x, self.y, math.cos(a), math.sin(a),
                                            speed=280 if self.core_exposed else 200))
        for arm in self.arms:
            arm.update(dt, self.x, self.y)

    def hit_test(self, bx, by, dmg=1):
        for arm in self.arms:
            if not arm.dead and math.hypot(bx - arm.x, by - arm.y) < 40:
                arm.hp -= dmg
                if arm.hp <= 0:
                    arm.dead = True
                return True
        if self.core_exposed and math.hypot(bx - self.x, by - self.y) < 72:
            self.hp -= dmg
            if self.hp <= 0:
                self.dead = True
            return True
        return False

    def draw(self, surf):
        bx, by = int(self.x), int(self.y)
        for arm in self.arms:
            if not arm.dead:
                arm.draw(surf, self.x, self.y)
        br = 72
        if not self.core_exposed:
            pygame.draw.circle(surf, (80, 20, 130), (bx, by), br)
            pygame.draw.circle(surf, (160, 60, 255), (bx, by), br, 5)
        else:
            p = 0.85 + 0.15 * math.sin(self.t * 10)
            pygame.draw.circle(surf, (200, 20, 20), (bx, by), int(br * p))
            pygame.draw.circle(surf, (255, 80, 80), (bx, by), int(br * p), 4)
        draw_googly_eyes(surf, self.x, self.y, 52,
                         math.atan2(self.y - CY, self.x - CX))
        if self.core_exposed:
            bw = 220
            bby = by - br - 30
            pygame.draw.rect(surf, (60, 10, 10), (bx - bw//2, bby, bw, 14))
            ratio = max(0, self.hp / self.max_hp)
            pygame.draw.rect(surf, (220, 40, 40),
                (bx - bw//2, bby, int(bw * ratio), 14))
            pygame.draw.rect(surf, (255, 100, 100), (bx - bw//2, bby, bw, 14), 2)
            blit(surf, "CORE", 11, (255, 100, 100), (bx, bby - 8))


# ── Ship ──────────────────────────────────────────────────────────────────────

class Ship:
    def __init__(self):
        self.x = float(CX)
        self.y = float(CY)
        self.hp     = 100
        self.max_hp = 100
        self.aim    = 0.0
        self.fire_cd = 0.0
        self.wboost  = 0.0
        self.sh_angle  = 200.0
        self.sh_charges = SHIELD_CHARGES
        self.sh_regen_t = 0.0
        self.sh_on      = False
        self.eng_level  = 3
        self.od_t  = 0.0
        self.od_cd = 0.0
        self.dash_t  = 0.0
        self.dash_cd = 0.0
        self.dash_dx = 0.0
        self.dash_dy = 0.0
        self.hit_flash  = 0.0
        self.invincible = 0.0
        self.t = 0.0

    def speed(self):
        base = SHIP_SPEED_BASE * (0.4 + 0.6 * self.eng_level / 5.0)
        return base * 2.0 if self.od_t > 0 else base

    def update(self, dt, inp, bullets):
        self.t += dt
        self.hit_flash  = max(0, self.hit_flash  - dt)
        self.invincible = max(0, self.invincible - dt)
        self.fire_cd    = max(0, self.fire_cd    - dt)
        self.wboost     = max(0, self.wboost     - dt)
        self.od_t       = max(0, self.od_t       - dt)
        self.od_cd      = max(0, self.od_cd      - dt)
        self.dash_t     = max(0, self.dash_t     - dt)
        self.dash_cd    = max(0, self.dash_cd    - dt)
        self.sh_regen_t -= dt
        if self.sh_regen_t <= 0 and self.sh_charges < SHIELD_CHARGES:
            self.sh_charges += 1
            self.sh_regen_t = SHIELD_REGEN

        # P1 pilot
        dx, dy = 0.0, 0.0
        if inp.held(0, "LEFT"):  dx -= 1
        if inp.held(0, "RIGHT"): dx += 1
        if inp.held(0, "UP"):    dy -= 1
        if inp.held(0, "DOWN"):  dy += 1
        if dx and dy:
            dx *= 0.7071; dy *= 0.7071
        if inp.just(0, "JUMP") and self.dash_cd <= 0:
            ndx = dx or math.cos(math.radians(self.aim) + math.pi)
            ndy = dy or math.sin(math.radians(self.aim) + math.pi)
            l = math.hypot(ndx, ndy) or 1
            self.dash_dx, self.dash_dy = ndx / l, ndy / l
            self.dash_t  = DASH_DUR
            self.dash_cd = DASH_CD
            self.invincible = DASH_DUR + 0.15
        if self.dash_t > 0:
            vx, vy = self.dash_dx * DASH_SPEED, self.dash_dy * DASH_SPEED
        else:
            vx, vy = dx * self.speed(), dy * self.speed()
        self.x = max(SX_MIN+40, min(SX_MAX-40, self.x + vx * dt))
        self.y = max(SY_MIN+40, min(SY_MAX-40, self.y + vy * dt))

        # P2 weapons — joystick direction = aim
        adx, ady = 0.0, 0.0
        if inp.held(1, "LEFT"):  adx -= 1
        if inp.held(1, "RIGHT"): adx += 1
        if inp.held(1, "UP"):    ady -= 1
        if inp.held(1, "DOWN"):  ady += 1
        if adx or ady:
            self.aim = math.degrees(math.atan2(ady, adx))
        fcd = FIRE_CD_FAST if self.wboost > 0 else FIRE_CD_NORM
        if inp.held(1, "ATTACK") and self.fire_cd <= 0:
            r = math.radians(self.aim)
            bullets.append(Bullet(self.x + math.cos(r)*36, self.y + math.sin(r)*36,
                                  math.cos(r), math.sin(r)))
            self.fire_cd = fcd

        # P3 shields — joystick direction = shield facing
        sdx, sdy = 0.0, 0.0
        if inp.held(2, "LEFT"):  sdx -= 1
        if inp.held(2, "RIGHT"): sdx += 1
        if inp.held(2, "UP"):    sdy -= 1
        if inp.held(2, "DOWN"):  sdy += 1
        if sdx or sdy:
            self.sh_angle = math.degrees(math.atan2(sdy, sdx))
        self.sh_on = inp.held(2, "JUMP")

        # P4 engines
        if inp.just(3, "UP"):
            self.eng_level = min(5, self.eng_level + 1)
        if inp.just(3, "DOWN"):
            self.eng_level = max(1, self.eng_level - 1)
        if inp.just(3, "ATTACK") and self.od_cd <= 0:
            self.od_t  = OVERDRIVE_DUR
            self.od_cd = OVERDRIVE_CD

    def check_hit(self, damage, impact_deg):
        if self.invincible > 0:
            return True
        if self.sh_on and self.sh_charges > 0:
            diff = (impact_deg - self.sh_angle + 180) % 360 - 180
            if abs(diff) <= SHIELD_ARC / 2:
                self.sh_charges -= 1
                self.sh_regen_t  = SHIELD_REGEN
                return True
        self.hp -= damage
        self.hit_flash  = 0.15
        self.invincible = 0.6
        return False

    def apply_powerup(self, kind):
        if kind == "shield":
            self.sh_charges = min(SHIELD_CHARGES + 2, self.sh_charges + 2)
        elif kind == "weapon":
            self.wboost = 10.0
        elif kind == "engine":
            self.od_t  = 3.0
            self.od_cd = max(self.od_cd, 3.0)
        elif kind == "repair":
            self.hp = min(self.max_hp, self.hp + 20)

    def draw(self, surf):
        x, y = int(self.x), int(self.y)
        t = self.t

        # Shield arc
        sh_rad = math.radians(self.sh_angle)
        arc_half = math.radians(SHIELD_ARC / 2)
        if self.sh_charges > 0:
            sr = 54
            alpha_s = pygame.Surface((sr*2+6, sr*2+6), pygame.SRCALPHA)
            col = (150, 60, 210) if self.sh_on else (70, 20, 110)
            lw  = 14 if self.sh_on else 4
            start_a = -(sh_rad + arc_half)
            end_a   = -(sh_rad - arc_half)
            pygame.draw.arc(alpha_s, (*col, 220 if self.sh_on else 80),
                (3, 3, sr*2, sr*2), start_a, end_a, lw)
            surf.blit(alpha_s, (x - sr, y - sr))

        # Aim reticle
        ar = math.radians(self.aim)
        aim_x = int(self.x + math.cos(ar) * 64)
        aim_y = int(self.y + math.sin(ar) * 64)
        pygame.draw.line(surf, (255, 210, 40), (x, y), (aim_x, aim_y), 2)
        pygame.draw.circle(surf, (255, 210, 40), (aim_x, aim_y), 9, 2)
        pygame.draw.line(surf, (255, 210, 40),
            (aim_x - 13, aim_y), (aim_x + 13, aim_y), 1)
        pygame.draw.line(surf, (255, 210, 40),
            (aim_x, aim_y - 13), (aim_x, aim_y + 13), 1)

        # Overdrive glow
        if self.od_t > 0:
            gs = pygame.Surface((130, 130), pygame.SRCALPHA)
            pygame.draw.circle(gs, (220, 60, 20, 55), (65, 65), 60)
            surf.blit(gs, (x - 65, y - 65))

        # Dash flash
        if self.dash_t > 0:
            ds = pygame.Surface((90, 90), pygame.SRCALPHA)
            pygame.draw.circle(ds, (30, 130, 255, 90), (45, 45), 42)
            surf.blit(ds, (x - 45, y - 45))

        # Engine trails
        el = self.eng_level / 5.0
        if self.od_t > 0: el = 1.0
        tlen = int(18 + 45 * el)
        tcol = (220, 100, 40) if self.od_t > 0 else (80, 140, 255)
        for sign, yo in [(-1, -18), (1, 18)]:
            fx = int(math.sin(t * (19 + sign)) * 4)
            pygame.draw.polygon(surf, tcol, [
                (x - 25, y + yo),
                (x - 25 - tlen + fx, y + yo - 4 * sign),
                (x - 25 - tlen + fx, y + yo + 4 * sign),
            ])

        # Hull
        col = (255, 255, 255) if self.hit_flash > 0 else (185, 225, 255)
        pts = [(x+38, y), (x-26, y-22), (x-15, y), (x-26, y+22)]
        pygame.draw.polygon(surf, col, pts)
        pygame.draw.polygon(surf, (30, 130, 255), pts, 2)
        # Cockpit
        pygame.draw.ellipse(surf, (100, 210, 255), (x-4, y-9, 26, 18))


# ── HUD ───────────────────────────────────────────────────────────────────────

def draw_hud(surf, ship, wave_num, score, boss=None):
    # Top bar background
    pygame.draw.rect(surf, (10, 8, 25), (0, 30, W, 46))
    pygame.draw.line(surf, (60, 40, 120), (0, 76), (W, 76), 1)

    # Ship HP bar (center top)
    bw = 440
    bx = CX - bw//2
    by = 42
    pygame.draw.rect(surf, (40, 10, 10), (bx, by, bw, 20))
    hp_ratio = max(0, ship.hp / ship.max_hp)
    hcol = (60, 200, 60) if hp_ratio > 0.5 else (220, 180, 20) if hp_ratio > 0.25 else (220, 40, 40)
    pygame.draw.rect(surf, hcol, (bx, by, int(bw * hp_ratio), 20))
    pygame.draw.rect(surf, (100, 60, 180), (bx, by, bw, 20), 2)
    blit(surf, f"HULL  {ship.hp}/{ship.max_hp}", 14, (220, 200, 255), (CX, by + 10))

    # Wave / score
    blit(surf, f"WAVE {wave_num}", 18, (180, 140, 255), (CX - 280, 54))
    blit(surf, f"SCORE  {score}", 18, (180, 140, 255), (CX + 280, 54))

    # Player panels
    panel_w = 150
    for pid in range(4):
        col = PCOLORS[pid]
        px = 2 + pid * (panel_w + 4) if pid < 2 else W - (4 - pid) * (panel_w + 4) - panel_w + 2
        # Rearrange: P1 P2 on left, P3 P4 on right isn't great visually
        # Better: all four at sides — P1,P2 left; P3,P4 right
        if pid == 0:   px = 2
        elif pid == 1: px = panel_w + 6
        elif pid == 2: px = W - panel_w*2 - 6
        elif pid == 3: px = W - panel_w - 2

        pygame.draw.rect(surf, (15, 10, 35), (px, 82, panel_w, 200))
        pygame.draw.rect(surf, col, (px, 82, panel_w, 200), 2)
        blit(surf, f"P{pid+1}", 18, col, (px + panel_w//2, 98))
        blit(surf, ROLES[pid], 11, (200, 180, 255), (px + panel_w//2, 116))

        if pid == 0:
            # Dash cooldown
            dc = 1.0 - min(1.0, ship.dash_cd / DASH_CD)
            blit(surf, "DASH", 11, (150, 180, 255), (px + panel_w//2, 138))
            pygame.draw.rect(surf, (30, 20, 60),  (px+10, 148, panel_w-20, 8))
            pygame.draw.rect(surf, (30, 130, 255), (px+10, 148, int((panel_w-20)*dc), 8))
        elif pid == 1:
            blit(surf, "AIM DIR", 11, (220, 190, 100), (px + panel_w//2, 138))
            ar = math.radians(ship.aim)
            mx = int((px + panel_w//2) + math.cos(ar) * 22)
            my = int(164 + math.sin(ar) * 22)
            pygame.draw.circle(surf, (60, 50, 100), (px + panel_w//2, 164), 24)
            pygame.draw.line(surf, (255, 210, 40), (px + panel_w//2, 164), (mx, my), 3)
            if ship.wboost > 0:
                blit(surf, "BOOSTED", 11, (255, 210, 40), (px + panel_w//2, 195))
        elif pid == 2:
            blit(surf, f"CHARGES: {ship.sh_charges}", 11, (180, 100, 255), (px + panel_w//2, 138))
            sr = math.radians(ship.sh_angle)
            sx_ = int((px + panel_w//2) + math.cos(sr) * 22)
            sy_ = int(164 + math.sin(sr) * 22)
            arc_half = math.radians(SHIELD_ARC / 2)
            ac = (150, 60, 210) if ship.sh_on else (70, 25, 100)
            pygame.draw.circle(surf, (40, 25, 70), (px + panel_w//2, 164), 24)
            pygame.draw.arc(surf, ac,
                (px + panel_w//2 - 24, 140, 48, 48),
                -(sr + arc_half), -(sr - arc_half), 8 if ship.sh_on else 3)
        elif pid == 3:
            blit(surf, "THROTTLE", 11, (220, 100, 100), (px + panel_w//2, 138))
            for lv in range(1, 6):
                lx = px + 12 + (lv-1) * ((panel_w-24)//5)
                lc = (220, 60, 40) if lv <= ship.eng_level else (40, 20, 30)
                if ship.od_t > 0:
                    lc = (255, 150, 50)
                pygame.draw.rect(surf, lc, (lx, 155, (panel_w-24)//5 - 3, 18))
            if ship.od_t > 0:
                blit(surf, "OVERDRIVE", 11, (255, 150, 50), (px + panel_w//2, 182))
            else:
                oc = 1.0 - min(1.0, ship.od_cd / OVERDRIVE_CD)
                blit(surf, "BOOST CD", 11, (150, 80, 80), (px + panel_w//2, 182))
                pygame.draw.rect(surf, (40, 15, 15),  (px+10, 193, panel_w-20, 6))
                pygame.draw.rect(surf, (220, 60, 40),  (px+10, 193, int((panel_w-20)*oc), 6))

    # Shield charges as small dots near ship (drawn in gameplay area)
    for i in range(SHIELD_CHARGES):
        c = (150, 60, 210) if i < ship.sh_charges else (40, 20, 60)
        pygame.draw.circle(surf, c, (int(ship.x) - 30 + i * 14, int(ship.y) - 60), 5)


# ── Attract drones ────────────────────────────────────────────────────────────

class AttractDrone:
    def __init__(self):
        self.x, self.y = float(random.randint(0, W)), float(random.randint(0, H))
        speed = random.uniform(40, 100)
        angle = random.uniform(0, math.pi * 2)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.t  = random.uniform(0, math.pi*2)
        self.r  = random.randint(12, 22)
        self.col = random.choice([(180,100,220),(80,210,90),(220,160,50),(220,90,90)])

    def update(self, dt):
        self.t += dt
        self.x = (self.x + self.vx * dt) % W
        self.y = (self.y + self.vy * dt) % H

    def draw(self, surf):
        x, y = int(self.x), int(self.y)
        r = self.r
        wx = int(math.sin(self.t * 7) * 2)
        wy = int(math.cos(self.t * 5) * 2)
        pts = [(x+wx,y-r+wy),(x+r,y+wy),(x+wx,y+r-wy),(x-r,y+wy)]
        pygame.draw.polygon(surf, self.col, pts)
        draw_googly_eyes(surf, self.x, self.y, r * 0.8,
                         math.atan2(CY - self.y, CX - self.x))


# ── Main game ─────────────────────────────────────────────────────────────────

class Game:
    def __init__(self):
        self.inp    = Input()
        self.state  = "ATTRACT"
        self.nebula = build_nebula()
        self.stars  = [Star() for _ in range(220)]
        self.attract_drones = [AttractDrone() for _ in range(18)]
        self._reset()

    def _reset(self):
        self.ship      = Ship()
        self.bullets   = []
        self.ebullets  = []
        self.enemies   = []
        self.powerups  = []
        self.boss      = None
        self.wave_idx  = 0
        self.wave_num  = 1
        self.score     = 0
        self.spawn_queue = []
        self.spawn_t   = 0.0
        self.wave_clear_t = 0.0
        self.wave_msg_t   = 0.0
        self.result    = "DEFEAT"
        self._quit_hold = 0.0
        self._start_wave(0)

    def _start_wave(self, idx):
        spec = WAVES[idx]
        if spec == "BOSS":
            self.boss = Boss()
            self.wave_msg_t = 3.0
        else:
            speed_mult = 1.0 + idx * 0.08
            self.spawn_queue = []
            for kind, count in spec:
                for _ in range(count):
                    self.spawn_queue.append((kind, speed_mult))
            random.shuffle(self.spawn_queue)
            self.spawn_t   = 0.3
            self.wave_msg_t = 2.0

    def run(self):
        while True:
            dt = min(clock.tick(60) / 1000.0, 0.05)
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
            self.inp.pump(events)

            if self.inp.timed_out():
                pygame.quit(); sys.exit()

            if   self.state == "ATTRACT":   self._attract(dt)
            elif self.state == "PLAYING":   self._playing(dt)
            elif self.state == "GAME_OVER": self._game_over(dt)
            elif self.state == "VICTORY":   self._game_over(dt)

            pygame.display.flip()

    # ── ATTRACT ──────────────────────────────────────────────────────────────

    def _attract(self, dt):
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        for pid in range(4):
            if self.inp.just(pid, "ATTACK"):
                self._reset()
                self.state = "PLAYING"
                self.inp.reset_activity()
                return

        screen.blit(self.nebula, (0, 0))
        for s in self.stars: s.draw(screen, dt)
        for d in self.attract_drones:
            d.update(dt)
            d.draw(screen)

        # Title
        blit(screen, "SWARM COMMAND", 72, (220, 160, 255), (CX, 200))
        blit(screen, "CO-OP STARSHIP SURVIVAL", 24, (160, 120, 220), (CX, 268))

        # Role cards
        card_w, card_h = 320, 160
        starts = [CX - card_w*2 - 20, CX - card_w - 10, CX + 10, CX + card_w + 20]
        for pid in range(4):
            cx_ = starts[pid] + card_w // 2
            cy_ = 440
            col = PCOLORS[pid]
            pygame.draw.rect(screen, (15, 10, 30),
                (starts[pid], cy_ - card_h//2, card_w, card_h), border_radius=8)
            pygame.draw.rect(screen, col,
                (starts[pid], cy_ - card_h//2, card_w, card_h), 3, border_radius=8)
            blit(screen, f"P{pid+1} — {ROLES[pid]}", 24, col, (cx_, cy_ - 44))
            blit(screen, HINTS[pid], 11, (200, 180, 240), (cx_, cy_ - 14))

        blit(screen, "SURVIVE ALIEN WAVES · DESTROY THE MOTHERSHIP", 18,
             (180, 140, 255), (CX, 580))
        pulse = 0.7 + 0.3 * math.sin(time.monotonic() * 3)
        pcol  = tuple(int(c * pulse) for c in (220, 200, 255))
        blit(screen, "PRESS ATTACK TO BEGIN", 36, pcol, (CX, 660))
        blit(screen, "ATTACK + JUMP  TO QUIT", 14, (120, 80, 160), (CX, 730))

    # ── PLAYING ───────────────────────────────────────────────────────────────

    def _playing(self, dt):
        # Quit hold (2 players)
        holders = [p for p in range(4)
                   if self.inp.held(p, "ATTACK") and self.inp.held(p, "JUMP")]
        if len(holders) >= 2:
            self._quit_hold = getattr(self, "_quit_hold", 0.0) + dt
        else:
            self._quit_hold = 0.0
        if self._quit_hold >= 5.0:
            pygame.quit(); sys.exit()

        self.ship.update(dt, self.inp, self.bullets)

        # Spawn enemies
        self.spawn_t -= dt
        if self.spawn_t <= 0 and self.spawn_queue:
            kind, smult = self.spawn_queue.pop(0)
            ex, ey = rand_edge()
            self.enemies.append(Enemy(ex, ey, kind, smult))
            self.spawn_t = random.uniform(0.3, 0.7)

        # Update enemies
        for e in self.enemies:
            e.update(dt, self.ship.x, self.ship.y, self.ebullets)
            dist = math.hypot(e.x - self.ship.x, e.y - self.ship.y)
            if dist < e.radius + 32 and not e.dead:
                impact = math.degrees(math.atan2(e.y - self.ship.y, e.x - self.ship.x)) + 180
                blocked = self.ship.check_hit(12, impact)
                if not blocked:
                    pass  # damage applied
                e.dead = True

        # Drop power-ups
        for e in self.enemies:
            if e.dead and random.random() < 0.22:
                self.powerups.append(PowerUp(e.x, e.y))
        self.score += sum(e.score_val for e in self.enemies if e.dead)
        self.enemies = [e for e in self.enemies if not e.dead]

        # Update bullets
        for b in self.bullets:
            b.update(dt)
            for e in self.enemies:
                if not e.dead and math.hypot(b.x - e.x, b.y - e.y) < e.radius:
                    e.take_hit()
                    b.dead = True
            if self.boss and not self.boss.dead:
                if self.boss.hit_test(b.x, b.y):
                    b.dead = True
        self.bullets = [b for b in self.bullets if not b.dead]

        # Update enemy bullets
        for eb in self.ebullets:
            eb.update(dt)
            if not eb.dead:
                d = math.hypot(eb.x - self.ship.x, eb.y - self.ship.y)
                if d < 30:
                    impact = math.degrees(math.atan2(eb.y - self.ship.y,
                                                     eb.x - self.ship.x)) + 180
                    self.ship.check_hit(8, impact)
                    eb.dead = True
        self.ebullets = [eb for eb in self.ebullets if not eb.dead]

        # Power-ups
        for pu in self.powerups:
            pu.update(dt)
            if not pu.dead and math.hypot(pu.x - self.ship.x, pu.y - self.ship.y) < 36:
                self.ship.apply_powerup(pu.kind)
                pu.dead = True
        self.powerups = [p for p in self.powerups if not p.dead]

        # Boss
        if self.boss:
            self.boss.update(dt, self.ship.x, self.ship.y, self.ebullets)
            if self.boss.dead:
                self.result = "VICTORY"
                self.state  = "VICTORY"
                return

        # Wave clear check
        no_enemies = not self.enemies and not self.spawn_queue
        no_boss    = self.boss is None
        if no_enemies and no_boss:
            self.wave_clear_t += dt
            if self.wave_clear_t >= 2.0:
                self.wave_clear_t = 0.0
                self.wave_idx += 1
                if self.wave_idx >= len(WAVES):
                    self.result = "VICTORY"
                    self.state  = "VICTORY"
                    return
                self.wave_num += 1
                self._start_wave(self.wave_idx)

        # Death check
        if self.ship.hp <= 0:
            self.result = "DEFEAT"
            self.state  = "GAME_OVER"
            return

        # ── Draw ─────────────────────────────────────────────────────────────
        screen.blit(self.nebula, (0, 0))
        for s in self.stars: s.draw(screen, dt)
        for pu in self.powerups: pu.draw(screen)
        for e  in self.enemies:  e.draw(screen, self.ship.x, self.ship.y)
        if self.boss: self.boss.draw(screen)
        for eb in self.ebullets: eb.draw(screen)
        for b  in self.bullets:  b.draw(screen)
        self.ship.draw(screen)
        draw_hud(screen, self.ship, self.wave_num, self.score, self.boss)

        # Wave announcement
        self.wave_msg_t -= dt
        if self.wave_msg_t > 0:
            alpha = min(1.0, self.wave_msg_t) * 255
            col   = (int(200 * alpha/255), int(160 * alpha/255), int(255 * alpha/255))
            if WAVES[self.wave_idx] == "BOSS" or (self.boss and self.wave_msg_t > 0):
                blit(screen, "BOSS WAVE!", 72, col, (CX, CY))
                blit(screen, "DESTROY THE MOTHERSHIP", 24, col, (CX, CY + 70))
            else:
                blit(screen, f"WAVE {self.wave_num}", 72, col, (CX, CY))

        # Quit progress bar
        if self._quit_hold > 0:
            t = min(self._quit_hold / 5.0, 1.0)
            pygame.draw.rect(screen, (60, 20, 20), (0, H - 10, W, 10))
            pygame.draw.rect(screen, (220, 50, 50), (0, H - 10, int(W * t), 10))
            blit(screen, "HOLD TO QUIT...", 14, (220, 80, 80), (CX, H - 22))

    # ── GAME OVER / VICTORY ───────────────────────────────────────────────────

    def _game_over(self, dt):
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        for pid in range(4):
            if self.inp.just(pid, "ATTACK"):
                self._reset()
                self.state = "PLAYING"
                self.inp.reset_activity()
                return

        screen.blit(self.nebula, (0, 0))
        for s in self.stars: s.draw(screen, dt)

        if self.state == "VICTORY":
            blit(screen, "MISSION COMPLETE", 72, (180, 255, 140), (CX, 320))
            blit(screen, "THE MOTHERSHIP IS DESTROYED", 36, (140, 220, 120), (CX, 410))
        else:
            blit(screen, "SHIP DESTROYED", 72, (255, 80, 80), (CX, 320))
            blit(screen, "THE SWARM OVERWHELMED YOU", 36, (220, 100, 80), (CX, 410))

        blit(screen, f"FINAL SCORE:  {self.score}", 48, (220, 200, 255), (CX, 510))
        blit(screen, f"REACHED WAVE {self.wave_num}", 24, (180, 150, 220), (CX, 570))

        pulse = 0.7 + 0.3 * math.sin(time.monotonic() * 3)
        pcol  = tuple(int(c * pulse) for c in (220, 200, 255))
        blit(screen, "PRESS ATTACK TO PLAY AGAIN", 36, pcol, (CX, 660))
        blit(screen, "ATTACK + JUMP  TO QUIT", 14, (120, 80, 160), (CX, 720))


Game().run()
