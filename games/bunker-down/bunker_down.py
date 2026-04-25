#!/usr/bin/env python3
import pygame, sys, json, math, random, os, time as _t

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
W, H   = screen.get_size()
clock  = pygame.time.Clock()

_FP = os.path.expanduser("~/.local/share/fonts/DepartureMono-Regular.otf")
def _f(sz):
    return (pygame.font.Font(_FP, sz) if os.path.exists(_FP)
            else pygame.font.SysFont("monospace", sz, bold=True))
FONTS = {s: _f(s) for s in (72, 48, 36, 24, 18, 14, 11)}

def blit(surf, text, size, color, pos, anchor="center"):
    s = FONTS[size].render(str(text), False, color)
    surf.blit(s, s.get_rect(**{anchor: pos}))


# ── Input ─────────────────────────────────────────────────────────────────────
class Input:
    INACTIVITY_TIMEOUT = 45.0

    def __init__(self):
        self.maps = []
        self._prev = set()
        self._curr = set()
        self._last_activity = _t.monotonic()
        ctrl = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "config", "controllers.json")
        try:
            data = json.load(open(ctrl))
            for p in data["players"]:
                self.maps.append({a: v["key"] for a, v in p["inputs"].items()
                                  if v["type"] == "key"})
        except Exception:
            self.maps = [
                {"UP":1073741906,"DOWN":1073741905,"LEFT":1073741904,"RIGHT":1073741903,
                 "ATTACK":1073742050,"JUMP":1073742048},
                {"UP":114,"DOWN":102,"LEFT":100,"RIGHT":103,"ATTACK":115,"JUMP":97},
                {"UP":105,"DOWN":107,"LEFT":106,"RIGHT":108,
                 "ATTACK":1073742053,"JUMP":1073742052},
                {"UP":121,"DOWN":110,"LEFT":118,"RIGHT":117,"ATTACK":101,"JUMP":98},
            ]

    def pump(self, events):
        self._prev = set(self._curr)
        for e in events:
            if e.type == pygame.KEYDOWN:
                self._curr.add(e.key)
                self._last_activity = _t.monotonic()
            elif e.type == pygame.KEYUP:
                self._curr.discard(e.key)

    def reset_activity(self): self._last_activity = _t.monotonic()
    def timed_out(self): return _t.monotonic() - self._last_activity > self.INACTIVITY_TIMEOUT

    def held(self, pid, act):
        k = self.maps[pid].get(act) if pid < len(self.maps) else None
        return k is not None and k in self._curr

    def just(self, pid, act):
        k = self.maps[pid].get(act) if pid < len(self.maps) else None
        return k is not None and k in self._curr and k not in self._prev


# ── Constants ─────────────────────────────────────────────────────────────────
TILE       = 48
MTW, MTH   = 50, 36
MAPW, MAPH = MTW * TILE, MTH * TILE   # 2400 × 1728

BKX      = MAPW // 2    # 1200
BKY      = MAPH // 2    # 864
BK_HALF  = 72
BUNKER_RECT = pygame.Rect(BKX - BK_HALF, BKY - BK_HALF, BK_HALF * 2, BK_HALF * 2)

P1COL = (30, 130, 255)

TRAP_NAMES  = ["Spike Pit", "Flame Barrel", "Electric Fence", "Auto-Turret"]
TRAP_COSTS  = [15, 30, 25, 60]
TRAP_COLS   = [(150, 75, 30), (220, 90, 20), (60, 200, 240), (160, 160, 50)]

WAVE_TITLES = [
    "The Neighbourhood Watch",
    "A Light Drizzle of Undead",
    "They're Just Resting",
    "The Ones That Used To Be Your Neighbours",
    "DISTINGUISHED GUEST  ★",
    "Significant Personal Growth",
    "Technically Still Coming",
    "Persistent",
    "They've Brought Friends",
    "A VERY DISTINGUISHED GUEST  ★★",
    "Peak Foot Traffic",
    "The Rush Hour",
    "Everyone, Apparently",
    "The Encore",
    "AN EXCEPTIONALLY DISTINGUISHED GUEST  ★★★",
    "Okay This Is A Lot",
    "No Really A Lot",
    "You're Still Here?",
    "Impressive, Actually",
    "THE BIGGEST DISTINGUISHED GUEST  ★★★★",
]

QUIPS = [
    "Efficient.", "Mildly Gross.", "They Had It Coming.",
    "Points For Effort.", "Economical.", "It Was Them Or You.",
    "Technically Self-Defense.", "You Monster.", "Well, Someone Had To.",
    "And Another One.", "You're Getting Good At This.", "Sustainable.",
    "Could Be Worse.", "Honestly, Impressive.", "Not Your Finest Hour.",
]

EPITAPHS = [
    "You held out. Briefly. The zombies are unimpressed.",
    "Valiant effort. Statistically irrelevant.",
    "The bunker stood as long as your patience lasted.",
    "At least you kept them off the lawn. Mostly.",
    "The wasteland thanks you for your service. It won't remember your name.",
    "A spirited defense. Spirited, not successful.",
    "They got in eventually. They always do.",
    "You survived several waves. Several.",
]


# ── Map surface (pre-rendered) ────────────────────────────────────────────────
def _build_map():
    rng = random.Random(42)
    tc = [
        [(88,68,48),(83,64,45),(93,72,50)],
        [(108,92,76),(103,88,72),(113,96,80)],
        [(70,56,42),(66,52,38),(74,60,46)],
    ]
    surf = pygame.Surface((MAPW, MAPH))
    for ty in range(MTH):
        for tx in range(MTW):
            kind = rng.choices([0, 1, 2], weights=[60, 25, 15])[0]
            c    = rng.choice(tc[kind])
            pygame.draw.rect(surf, c, (tx*TILE, ty*TILE, TILE-1, TILE-1))

    # Road cross through bunker
    road = (62, 58, 52)
    for i in range(-3, 4):
        pygame.draw.rect(surf, road, (BKX + i*TILE - TILE//2, 0, TILE, MAPH))
        pygame.draw.rect(surf, road, (0, BKY + i*TILE - TILE//2, MAPW, TILE))

    # Bunker structure
    pygame.draw.rect(surf, (76, 72, 68), BUNKER_RECT)
    pygame.draw.rect(surf, (52, 48, 44), BUNKER_RECT, 5)
    for bx, by in [(-50,-50),(22,-50),(-50,22),(22,22)]:
        pygame.draw.rect(surf, (96, 90, 84), (BKX+bx, BKY+by, 28, 28))
        pygame.draw.rect(surf, (52, 48, 44), (BKX+bx, BKY+by, 28, 28), 2)
    # door
    pygame.draw.rect(surf, (46, 42, 38), (BKX-14, BKY+28, 28, 44))
    return surf

map_surf = _build_map()


# ── World-to-screen helper ────────────────────────────────────────────────────
def w2s(wx, wy, cx, cy):
    return int(wx - cx + W // 2), int(wy - cy + H // 2)


# ── Entities ──────────────────────────────────────────────────────────────────
class Scrap:
    def __init__(self, x, y, val=None):
        self.x = float(x)
        self.y = float(y)
        self.val = val or random.randint(3, 8)
        self.bob = random.uniform(0, math.tau)

    def update(self, dt):
        self.bob += dt * 3.0

    def draw(self, surf, cx, cy):
        sx, sy = w2s(self.x, self.y, cx, cy)
        if not (-20 < sx < W+20 and -20 < sy < H+20):
            return
        b = int(math.sin(self.bob) * 3)
        pygame.draw.circle(surf, (255, 140, 30), (sx, sy + b), 8)
        pygame.draw.circle(surf, (255, 200, 80), (sx, sy + b), 5)


class FloatText:
    def __init__(self, x, y, text, color=(255, 255, 200)):
        self.x    = float(x)
        self.y    = float(y)
        self.text = text
        self.col  = color
        self.life = 1.8
        self.vy   = -40.0

    def update(self, dt):
        self.y   += self.vy * dt
        self.vy  *= 0.97
        self.life -= dt

    def draw(self, surf, cx, cy):
        sx, sy = w2s(self.x, self.y, cx, cy)
        alpha  = max(0, min(255, int(self.life / 1.8 * 255)))
        s = FONTS[14].render(self.text, False, self.col)
        s.set_alpha(alpha)
        surf.blit(s, s.get_rect(center=(sx, int(sy))))


class Trap:
    def __init__(self, tx, ty, kind):
        self.tx, self.ty = tx, ty
        self.x  = tx * TILE + TILE // 2
        self.y  = ty * TILE + TILE // 2
        self.kind   = kind
        self.hp     = [1, 70, 90, 120][kind]
        self.max_hp = self.hp
        self.age    = 0.0
        self.active = True
        self.cooldown = 0.0

    def draw(self, surf, cx, cy):
        sx, sy = w2s(self.x, self.y, cx, cy)
        if not (-64 < sx < W+64 and -64 < sy < H+64):
            return
        c = TRAP_COLS[self.kind]

        if self.kind == 0:  # Spike Pit
            pygame.draw.rect(surf, (70, 45, 22), (sx-22, sy-22, 44, 44))
            for i in range(5):
                px = sx - 18 + i * 9
                pygame.draw.polygon(surf, c, [(px, sy+12), (px+4, sy-14), (px+8, sy+12)])

        elif self.kind == 1:  # Flame Barrel
            pygame.draw.rect(surf, (80, 58, 38), (sx-13, sy-22, 26, 38))
            pygame.draw.rect(surf, (100, 74, 50), (sx-13, sy-22, 26, 38), 2)
            if self.active:
                fh = random.randint(8, 20)
                pygame.draw.polygon(surf, (255, 80, 20),
                    [(sx-9, sy-22), (sx, sy-22-fh), (sx+9, sy-22)])
                pygame.draw.polygon(surf, (255, 210, 40),
                    [(sx-5, sy-22), (sx, sy-22-fh//2), (sx+5, sy-22)])

        elif self.kind == 2:  # Electric Fence
            deg = max(0, self.hp / 90.0)
            ec  = (int(60*deg), int(200*deg), int(240*deg))
            for dx in range(-40, 44, 7):
                jit = random.randint(-4, 4)
                pygame.draw.line(surf, ec, (sx+dx, sy), (sx+dx+7, sy+jit), 2)
            pygame.draw.rect(surf, (80, 80, 80), (sx-4, sy-18, 8, 36))

        elif self.kind == 3:  # Auto-Turret
            pygame.draw.circle(surf, (100, 100, 70), (sx, sy), 20)
            pygame.draw.circle(surf, (155, 155, 95), (sx, sy), 15)
            pygame.draw.circle(surf, (70, 70, 50), (sx, sy), 20, 3)
            hp_frac = max(0, self.hp / self.max_hp)
            pygame.draw.rect(surf, (50, 20, 20), (sx-18, sy-28, 36, 5))
            pygame.draw.rect(surf, (160, 220, 70), (sx-18, sy-28, int(36*hp_frac), 5))


class Bullet:
    def __init__(self, x, y, vx, vy, dmg=18):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = vx, vy
        self.dmg  = dmg
        self.alive = True
        self.life  = 3.0

    def update(self, dt):
        self.x   += self.vx * dt
        self.y   += self.vy * dt
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf, cx, cy):
        sx, sy = w2s(self.x, self.y, cx, cy)
        if 0 < sx < W and 0 < sy < H:
            pygame.draw.circle(surf, (255, 230, 80), (sx, sy), 4)


class Zombie:
    def __init__(self, x, y, wave):
        self.x, self.y = float(x), float(y)
        self.boss  = False
        speed_mult = 1.0 + (wave - 1) * 0.07
        hp_mult    = 1.0 + (wave - 1) * 0.10
        self.base_speed = 58.0 * speed_mult
        self.speed = self.base_speed
        self.hp = self.max_hp = int(38 * hp_mult)
        self.dmg   = 5.0
        self.scrap = random.randint(3, 7)
        self.wobble  = random.uniform(0, math.tau)
        self.wob_r   = random.uniform(5, 12)
        self.alive   = True
        self.at_bunker = False

    def make_boss(self, wave):
        self.boss = True
        self.base_speed = max(28, 40 + wave * 1.5)
        self.speed = self.base_speed
        self.hp = self.max_hp = int(320 + wave * 35)
        self.dmg   = 14.0
        self.scrap = random.randint(22, 38)

    def update(self, dt, traps, bullets, floats_list):
        if not self.alive:
            return
        self.wobble += dt * 4.2
        self.speed = self.base_speed  # reset slowing each frame

        dx, dy = BKX - self.x, BKY - self.y
        dist   = math.hypot(dx, dy)
        self.at_bunker = dist < BK_HALF + (26 if self.boss else 18)

        if not self.at_bunker:
            angle = math.atan2(dy, dx) + math.sin(self.wobble) * self.wob_r * 0.015
            self.x += math.cos(angle) * self.speed * dt
            self.y += math.sin(angle) * self.speed * dt

        # Bullet hits
        for b in bullets:
            if b.alive and math.hypot(b.x - self.x, b.y - self.y) < (28 if self.boss else 16):
                self.hp -= b.dmg
                b.alive = False

        # Trap interactions
        for trap in traps:
            if not trap.active:
                continue
            tdx = trap.x - self.x
            tdy = trap.y - self.y
            tdist = math.hypot(tdx, tdy)
            r = 30 if self.boss else 20

            if trap.kind == 0 and tdist < r + 10:
                self.hp = -999
                trap.active = False
                floats_list.append(FloatText(self.x, self.y - 20, "SPIKE!", (255,140,40)))

            elif trap.kind == 1 and tdist < 42:
                self.hp -= 40.0 * dt

            elif trap.kind == 2 and tdist < 46 and trap.hp > 0:
                self.speed = max(8, self.speed - 90.0 * dt)
                self.hp   -= 18.0 * dt
                trap.hp   -= 3.0 * dt

        self.alive = self.hp > 0

    def draw(self, surf, cx, cy):
        sx, sy = w2s(self.x, self.y, cx, cy)
        if not (-50 < sx < W+50 and -50 < sy < H+50):
            return
        wb  = int(math.sin(self.wobble) * 3)
        sz  = 24 if self.boss else 15
        col = (45, 170, 35) if not self.boss else (80, 190, 40)
        drk = (28, 108, 22) if not self.boss else (55, 128, 25)

        pygame.draw.circle(surf, drk, (sx, sy + wb + 2), sz + 2)
        pygame.draw.circle(surf, col, (sx, sy + wb), sz)
        pygame.draw.circle(surf, (65, 148, 55), (sx, sy - sz + wb - 4), sz - 4)
        pygame.draw.circle(surf, (200, 35, 35), (sx - 4, sy - sz + wb - 4), 3)
        pygame.draw.circle(surf, (200, 35, 35), (sx + 4, sy - sz + wb - 4), 3)

        if self.boss:
            pygame.draw.circle(surf, (200, 255, 100), (sx, sy + wb), sz, 3)
            blit(surf, "BOSS", 11, (220, 255, 80), (sx, sy - sz + wb - 24))

        if self.hp < self.max_hp:
            bw = 30 if self.boss else 20
            bx = sx - bw // 2
            by = sy - sz - 10 + wb
            pygame.draw.rect(surf, (80, 20, 20), (bx, by, bw, 4))
            frac = max(0, self.hp / self.max_hp)
            pygame.draw.rect(surf, (40, 220, 60), (bx, by, int(bw * frac), 4))


# ── Spawn helpers ─────────────────────────────────────────────────────────────
def make_wave_zombies(wave):
    count = 8 + wave * 4 + (wave // 3) * 2
    zs = []
    for _ in range(count):
        edge = random.randint(0, 3)
        if   edge == 0: x, y = random.uniform(0, MAPW), 0.0
        elif edge == 1: x, y = random.uniform(0, MAPW), float(MAPH)
        elif edge == 2: x, y = 0.0, random.uniform(0, MAPH)
        else:           x, y = float(MAPW), random.uniform(0, MAPH)
        zs.append(Zombie(x, y, wave))
    return zs


# ── Game ──────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        self.inp   = Input()
        self.state = "ATTRACT"
        self._reset()

    def _reset(self):
        self.px = float(BKX)
        self.py = float(BKY + 140)
        self.cx = float(BKX)
        self.cy = float(BKY)
        self.scrap     = 30
        self.trap_idx  = 0
        self.bk_hp     = 200.0
        self.wave      = 0
        self.kills     = 0
        self.waves_done = 0
        self.zombies   = []
        self.traps     = []
        self.bullets   = []
        self.scraps    = []
        self.floats    = []
        self.spawn_q   = []
        self.spawn_t   = 0.0
        self.intro_t   = 0.0
        self.scav_t    = 0.0
        self.quip_t    = 0.0
        self.quip_txt  = ""
        self.bk_flash  = 0.0
        self._quit_h   = 0.0
        self.go_timer  = 0.0

    def _tile_has_trap(self, tx, ty):
        return any(t.tx == tx and t.ty == ty for t in self.traps)

    def _add_float(self, x, y, text, color=(255, 255, 200)):
        self.floats.append(FloatText(x, y, text, color))

    def _start_wave(self):
        self.wave      += 1
        self.waves_done = self.wave
        self.spawn_q    = make_wave_zombies(self.wave)
        if self.wave % 5 == 0:
            boss = Zombie(0.0, float(MAPH // 2), self.wave)
            boss.make_boss(self.wave)
            self.spawn_q.insert(0, boss)
        self.spawn_t  = 0.0
        self.intro_t  = 2.5
        self.state    = "WAVE_INTRO"

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

            if   self.state == "ATTRACT":    self._attract(dt)
            elif self.state == "WAVE_INTRO": self._wave_intro(dt)
            elif self.state == "PLAYING":    self._playing(dt)
            elif self.state == "SCAVENGE":   self._scavenge(dt)
            elif self.state == "GAME_OVER":  self._game_over(dt)

            pygame.display.flip()

    # ── ATTRACT ───────────────────────────────────────────────────────────────
    def _attract(self, dt):
        screen.fill((18, 13, 10))
        blit(screen, "BUNKER DOWN", 72, (210, 75, 35), (W//2, H//2 - 130))
        blit(screen, "Defend the bunker. Place traps. Try not to die.", 24,
             (160, 138, 108), (W//2, H//2 - 35))
        blit(screen, "JUMP: cycle trap     ATTACK: place trap", 18,
             (120, 108, 88), (W//2, H//2 + 22))
        pulse = int(abs(math.sin(_t.monotonic() * 2)) * 20)
        blit(screen, "PRESS ATTACK TO START", 36,
             (220 + pulse, 140 + pulse//2, 55), (W//2, H//2 + 110))
        blit(screen, "HOLD ATTACK + JUMP TO QUIT", 14, (90, 72, 54),
             (W//2, H - 48))

        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
            if self.inp.just(pid, "ATTACK"):
                self._reset()
                self._start_wave()

    # ── WAVE INTRO ────────────────────────────────────────────────────────────
    def _wave_intro(self, dt):
        self._draw_world()
        self.intro_t -= dt

        idx   = (self.wave - 1) % len(WAVE_TITLES)
        title = f"WAVE {self.wave}: {WAVE_TITLES[idx]}"
        boss  = self.wave % 5 == 0

        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 150))
        screen.blit(ov, (0, 0))

        col = (255, 55, 25) if boss else (220, 200, 75)
        blit(screen, title, 48, col, (W//2, H//2))
        if boss:
            blit(screen, "A Large Boy Approaches", 24, (255, 150, 50), (W//2, H//2 + 65))

        if self.intro_t <= 0:
            self.state = "PLAYING"

        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()

    # ── PLAYING ───────────────────────────────────────────────────────────────
    def _playing(self, dt):
        # Quit: two players hold ATTACK+JUMP for 5s
        holders = [p for p in range(4)
                   if self.inp.held(p, "ATTACK") and self.inp.held(p, "JUMP")]
        self._quit_h = (self._quit_h + dt) if len(holders) >= 2 else 0.0
        if self._quit_h >= 5.0:
            pygame.quit(); sys.exit()

        # Player movement
        spd = 180.0
        if self.inp.held(0, "UP"):    self.py -= spd * dt
        if self.inp.held(0, "DOWN"):  self.py += spd * dt
        if self.inp.held(0, "LEFT"):  self.px -= spd * dt
        if self.inp.held(0, "RIGHT"): self.px += spd * dt
        self.px = max(16, min(MAPW - 16, self.px))
        self.py = max(16, min(MAPH - 16, self.py))

        if self.inp.just(0, "JUMP"):
            self.trap_idx = (self.trap_idx + 1) % len(TRAP_NAMES)

        if self.inp.just(0, "ATTACK"):
            self._place_trap()

        # Camera
        self.cx += (self.px - self.cx) * min(1.0, dt * 8)
        self.cy += (self.py - self.cy) * min(1.0, dt * 8)
        self.cx  = max(W//2, min(MAPW - W//2, self.cx))
        self.cy  = max(H//2, min(MAPH - H//2, self.cy))

        # Spawn queue
        if self.spawn_q:
            self.spawn_t -= dt
            if self.spawn_t <= 0:
                self.zombies.append(self.spawn_q.pop(0))
                self.spawn_t = max(0.1, 0.5 - self.wave * 0.01)

        # Update traps
        for trap in self.traps:
            if not trap.active:
                continue
            trap.age += dt
            if trap.kind == 1 and trap.age > 8.0:
                trap.active = False
            elif trap.kind == 3:
                trap.cooldown -= dt
                if trap.cooldown <= 0:
                    target = min(
                        (z for z in self.zombies if z.alive),
                        key=lambda z: math.hypot(z.x - trap.x, z.y - trap.y),
                        default=None,
                    )
                    if target and math.hypot(target.x - trap.x, target.y - trap.y) < 320:
                        ang = math.atan2(target.y - trap.y, target.x - trap.x)
                        spd2 = 360.0
                        self.bullets.append(
                            Bullet(trap.x, trap.y, math.cos(ang)*spd2, math.sin(ang)*spd2))
                        trap.cooldown = 0.85
                        # Turret takes hits from being in zombie mass
                        near = sum(1 for z in self.zombies if z.alive and
                                   math.hypot(z.x - trap.x, z.y - trap.y) < 30)
                        trap.hp -= near * 2.0 * dt

            if trap.hp <= 0:
                trap.active = False

        # Bullets
        for b in self.bullets:
            b.update(dt)
        self.bullets = [b for b in self.bullets if b.alive]

        # Zombies
        for z in self.zombies:
            z.update(dt, self.traps, self.bullets, self.floats)
            if z.at_bunker and z.alive:
                self.bk_hp    -= z.dmg * dt
                self.bk_flash  = 0.25

        # Collect dead
        for z in self.zombies:
            if not z.alive:
                self.scraps.append(Scrap(
                    z.x + random.uniform(-12, 12),
                    z.y + random.uniform(-12, 12), z.scrap))
                self.kills += 1
                if random.random() < 0.14:
                    self.quip_txt = random.choice(QUIPS)
                    self.quip_t   = 2.2
        self.zombies = [z for z in self.zombies if z.alive]
        self.traps   = [t for t in self.traps if t.active]

        # Scrap pickup
        for s in self.scraps:
            s.update(dt)
        pickup, keep = [], []
        for s in self.scraps:
            if math.hypot(s.x - self.px, s.y - self.py) < 34:
                self.scrap += s.val
                self._add_float(s.x, s.y, f"+{s.val}", (255, 155, 35))
                pickup.append(s)
            else:
                keep.append(s)
        self.scraps = keep

        # Float texts
        for f in self.floats:
            f.update(dt)
        self.floats = [f for f in self.floats if f.life > 0]

        self.bk_flash = max(0.0, self.bk_flash - dt)
        if self.quip_t > 0: self.quip_t -= dt

        # Wave complete?
        if not self.spawn_q and not self.zombies:
            bonus = 10 + self.wave * 2
            self.scrap += bonus
            self._add_float(self.px, self.py - 50,
                            f"WAVE CLEAR!  +{bonus} SCRAP", (80, 230, 120))
            self.scav_t = 10.0
            self.state  = "SCAVENGE"

        # Bunker dead?
        if self.bk_hp <= 0:
            self.bk_hp    = 0
            self.go_timer = 8.0
            self.state    = "GAME_OVER"

        self._draw_world()
        self._draw_hud()

        if self._quit_h > 0.0:
            t = min(self._quit_h / 5.0, 1.0)
            pygame.draw.rect(screen, (55, 18, 18), (0, H - 10, W, 10))
            pygame.draw.rect(screen, (220, 50, 50), (0, H - 10, int(W * t), 10))

    # ── SCAVENGE ──────────────────────────────────────────────────────────────
    def _scavenge(self, dt):
        spd = 180.0
        if self.inp.held(0, "UP"):    self.py -= spd * dt
        if self.inp.held(0, "DOWN"):  self.py += spd * dt
        if self.inp.held(0, "LEFT"):  self.px -= spd * dt
        if self.inp.held(0, "RIGHT"): self.px += spd * dt
        self.px = max(16, min(MAPW - 16, self.px))
        self.py = max(16, min(MAPH - 16, self.py))

        if self.inp.just(0, "JUMP"):
            self.trap_idx = (self.trap_idx + 1) % len(TRAP_NAMES)
        if self.inp.just(0, "ATTACK"):
            self._place_trap()

        self.cx += (self.px - self.cx) * min(1.0, dt * 8)
        self.cy += (self.py - self.cy) * min(1.0, dt * 8)
        self.cx  = max(W//2, min(MAPW - W//2, self.cx))
        self.cy  = max(H//2, min(MAPH - H//2, self.cy))

        for s in self.scraps:
            s.update(dt)
        keep = []
        for s in self.scraps:
            if math.hypot(s.x - self.px, s.y - self.py) < 34:
                self.scrap += s.val
                self._add_float(s.x, s.y, f"+{s.val}", (255, 155, 35))
            else:
                keep.append(s)
        self.scraps = keep

        for f in self.floats:
            f.update(dt)
        self.floats = [f for f in self.floats if f.life > 0]

        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()

        self.scav_t -= dt
        self._draw_world()
        self._draw_hud()

        t_left = max(0, self.scav_t)
        blit(screen, f"SCAVENGE PHASE  —  {int(t_left) + 1}s", 36,
             (80, 225, 120), (W//2, 55))

        if self.scav_t <= 0:
            self._start_wave()

    # ── GAME OVER ─────────────────────────────────────────────────────────────
    def _game_over(self, dt):
        self.go_timer -= dt
        screen.fill((8, 5, 4))

        blit(screen, "BUNKER COMPROMISED", 72, (185, 40, 28), (W//2, H//2 - 210))
        ep = EPITAPHS[self.waves_done % len(EPITAPHS)]
        blit(screen, ep, 24, (155, 128, 96), (W//2, H//2 - 120))

        blit(screen, f"Waves Survived:  {self.waves_done}", 36,
             (220, 178, 75), (W//2, H//2 - 20))
        blit(screen, f"Zombies Killed:  {self.kills}", 36,
             (220, 178, 75), (W//2, H//2 + 45))

        if self.go_timer < 5.5:
            p = int(abs(math.sin(_t.monotonic() * 2)) * 28)
            blit(screen, "HOLD ATTACK + JUMP TO EXIT", 24,
                 (100 + p, 75, 55), (W//2, H//2 + 145))
            blit(screen, "PRESS ATTACK TO PLAY AGAIN", 24,
                 (70, 100 + p, 55), (W//2, H//2 + 190))

        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
            if self.go_timer < 5.5 and self.inp.just(pid, "ATTACK"):
                self._reset()
                self._start_wave()

    # ── Place trap ────────────────────────────────────────────────────────────
    def _place_trap(self):
        tx   = int(self.px // TILE)
        ty   = int(self.py // TILE)
        cost = TRAP_COSTS[self.trap_idx]

        if self._tile_has_trap(tx, ty):
            self._add_float(self.px, self.py - 32, "OCCUPIED", (200, 80, 80))
            return

        tpx = tx * TILE + TILE // 2
        tpy = ty * TILE + TILE // 2
        if BUNKER_RECT.inflate(16, 16).collidepoint(tpx, tpy):
            self._add_float(self.px, self.py - 32, "BUNKER TILE", (200, 80, 80))
            return

        if self.scrap < cost:
            self._add_float(self.px, self.py - 32,
                            f"NEED {cost} SCRAP", (220, 55, 55))
            return

        self.scrap -= cost
        self.traps.append(Trap(tx, ty, self.trap_idx))
        self._add_float(self.px, self.py - 32,
                        f"{TRAP_NAMES[self.trap_idx]} PLACED", (100, 220, 100))

    # ── Draw world ────────────────────────────────────────────────────────────
    def _draw_world(self):
        icx, icy = int(self.cx), int(self.cy)
        vx, vy   = icx - W//2, icy - H//2
        screen.blit(map_surf, (0, 0), (vx, vy, W, H))

        # Bunker flash
        if self.bk_flash > 0:
            bsx, bsy = w2s(BKX, BKY, icx, icy)
            fl = pygame.Surface((BK_HALF*2+10, BK_HALF*2+10), pygame.SRCALPHA)
            fl.fill((220, 28, 28, int(self.bk_flash / 0.25 * 160)))
            screen.blit(fl, (bsx - BK_HALF - 5, bsy - BK_HALF - 5))

        for trap in self.traps:
            trap.draw(screen, icx, icy)
        for s in self.scraps:
            s.draw(screen, icx, icy)
        for b in self.bullets:
            b.draw(screen, icx, icy)
        for z in self.zombies:
            z.draw(screen, icx, icy)

        self._draw_player(icx, icy)
        self._draw_preview(icx, icy)

        for f in self.floats:
            f.draw(screen, icx, icy)

        if self.quip_t > 0:
            blit(screen, self.quip_txt, 18, (220, 198, 138), (W//2, H - 96))

    def _draw_player(self, cx, cy):
        sx, sy = w2s(self.px, self.py, cx, cy)
        pygame.draw.circle(screen, (18, 85, 190), (sx, sy + 2), 17)
        pygame.draw.circle(screen, P1COL, (sx, sy), 15)
        pygame.draw.circle(screen, (200, 168, 128), (sx, sy - 11), 8)

        # Direction dot
        dx = dy = 0
        if self.inp.held(0, "RIGHT"): dx = 1
        elif self.inp.held(0, "LEFT"): dx = -1
        if self.inp.held(0, "DOWN"):  dy = 1
        elif self.inp.held(0, "UP"):  dy = -1
        if dx or dy:
            m = math.hypot(dx, dy)
            pygame.draw.circle(screen, (180, 220, 255),
                               (sx + int(dx/m*19), sy + int(dy/m*19)), 4)

    def _draw_preview(self, cx, cy):
        tx = int(self.px // TILE)
        ty = int(self.py // TILE)
        sx, sy = w2s(tx * TILE + TILE//2, ty * TILE + TILE//2, cx, cy)
        cost = TRAP_COSTS[self.trap_idx]
        ok   = self.scrap >= cost and not self._tile_has_trap(tx, ty)
        ov = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        ov.fill((90, 220, 90, 70) if ok else (220, 60, 60, 70))
        screen.blit(ov, (sx - TILE//2, sy - TILE//2))

    # ── HUD ───────────────────────────────────────────────────────────────────
    def _draw_hud(self):
        pygame.draw.rect(screen, (14, 11, 9), (0, H - 78, W, 78))
        pygame.draw.line(screen, (58, 48, 38), (0, H - 78), (W, H - 78), 2)

        # Bunker HP bar
        bhp = max(0.0, self.bk_hp)
        bw  = 290
        pygame.draw.rect(screen, (48, 18, 18), (22, H - 56, bw, 22))
        hcol = (215, 55, 28) if bhp < 60 else (215, 175, 55) if bhp < 120 else (55, 195, 75)
        pygame.draw.rect(screen, hcol, (22, H - 56, int(bw * bhp / 200), 22))
        pygame.draw.rect(screen, (75, 58, 45), (22, H - 56, bw, 22), 2)
        blit(screen, f"BUNKER  {int(bhp)} / 200", 14, (195, 175, 148), (22 + bw//2, H - 45))

        # Scrap
        blit(screen, f"SCRAP  {self.scrap}", 24, (255, 138, 28), (370, H - 48))

        # Trap selector
        for i in range(len(TRAP_NAMES)):
            bx = 510 + i * 240
            by = H - 72
            sel = i == self.trap_idx
            bg  = (42, 36, 28) if not sel else (68, 58, 38)
            pygame.draw.rect(screen, bg, (bx, by, 225, 60), border_radius=4)
            if sel:
                pygame.draw.rect(screen, (195, 158, 58), (bx, by, 225, 60), 2,
                                 border_radius=4)
            can = self.scrap >= TRAP_COSTS[i]
            nc  = (198, 175, 128) if can else (115, 78, 55)
            cc  = (250, 155, 38) if can else (195, 55, 55)
            pygame.draw.rect(screen, TRAP_COLS[i], (bx + 8, by + 20, 12, 12))
            blit(screen, TRAP_NAMES[i],       14, nc, (bx + 118, by + 20))
            blit(screen, f"Cost: {TRAP_COSTS[i]}", 11, cc, (bx + 118, by + 40))

        # Wave / kills
        blit(screen, f"WAVE  {self.wave}", 24, (218, 195, 95), (W - 215, H - 58))
        blit(screen, f"KILLS  {self.kills}", 18, (158, 148, 118), (W - 215, H - 32))

        # Controls
        blit(screen, "JUMP: cycle trap     ATTACK: place trap", 11,
             (75, 65, 52), (W//2, H - 10))


Game().run()
