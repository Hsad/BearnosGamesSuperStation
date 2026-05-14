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


# ----------------------------------------------------------------- Input
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

    def any_just(self, pid):
        return any(self.just(pid, a)
                   for a in ("UP","DOWN","LEFT","RIGHT","JUMP","ATTACK"))


# ----------------------------------------------------------------- constants
PCOLORS = [
    ( 30, 130, 255),
    (255, 210,  40),
    (150,  60, 210),
    (220,  40,  40),
]

# Layout
HUD_TOP_H    = 70    # below the obscured 30px bezel; top HUD ends here
HUD_BOT_H    = 130   # bottom trap-selector strip height
PLAY_TOP     = HUD_TOP_H
PLAY_BOT     = H - HUD_BOT_H
PLAY_H       = PLAY_BOT - PLAY_TOP

# Bunker
BUNKER_W     = 180
BUNKER_H     = 160
BUNKER_HP    = 1000
BUNKER_CX    = CX
BUNKER_CY    = (PLAY_TOP + PLAY_BOT) // 2
BUNKER_RECT  = pygame.Rect(BUNKER_CX - BUNKER_W // 2,
                           BUNKER_CY - BUNKER_H // 2,
                           BUNKER_W, BUNKER_H)

# Player
PLAYER_R     = 12
PLAYER_SPEED = 280

# Wave timing
SCAVENGE_T   = 10.0
WAVE_INTRO_T = 2.4

# Palette
COL_BG       = ( 28,  22,  18)
COL_GROUND1  = ( 46,  36,  28)
COL_GROUND2  = ( 38,  30,  24)
COL_CRACK    = ( 22,  18,  14)
COL_BUNKER   = ( 80,  78,  68)
COL_BUNKER_2 = (110, 105,  88)
COL_BUNKER_HI= (140, 130, 100)
COL_HP_OK    = ( 70, 200,  80)
COL_HP_LOW   = (220,  60,  50)
COL_SCRAP    = (255, 170,  50)
COL_ZOMBIE   = ( 90, 140,  70)
COL_ZOMBIE_D = ( 60, 100,  50)
COL_BLOOD    = (110,  30,  30)
COL_HUD_BG   = ( 18,  14,  10)
COL_HUD_LINE = ( 70,  60,  45)
COL_TEXT     = (210, 200, 180)
COL_DIM      = (140, 130, 110)
COL_RED      = (220,  50,  50)
COL_FLAME_O  = (255, 140,  30)
COL_FLAME_Y  = (255, 220, 100)
COL_ELEC     = (180, 220, 255)
COL_TURRET   = (130, 130, 140)


# ----------------------------------------------------------------- traps
# Players always start with SPIKE + TURRET. The rest are unlocked by walking
# over pickups dropped by boss zombies. Each run picks a random subset of the
# unlockable traps (the "run pool") so playthroughs vary.
TRAPS = [
    {
        "key":   "SPIKE",
        "name":  "Spike Pit",
        "blurb": "8 spikes. they don't grow back.",
        "cost":  5,
        "color": (130, 110, 70),
        "default": True,
    },
    {
        "key":   "TURRET",
        "name":  "Auto-Turret",
        "blurb": "45° cone. zombies notice.",
        "cost":  40,
        "color": (180, 180, 195),
        "default": True,
    },
    {
        "key":   "FLAME",
        "name":  "Flame Brazier",
        "blurb": "lingering fire. ignites passersby.",
        "cost":  15,
        "color": (210, 110, 40),
        "default": False,
    },
    {
        "key":   "FENCE",
        "name":  "Stun Fence",
        "blurb": "1.5s stagger. weak damage.",
        "cost":  20,
        "color": (180, 220, 255),
        "default": False,
    },
    {
        "key":   "TAR",
        "name":  "Tar Pit",
        "blurb": "big slow field. no damage.",
        "cost":  10,
        "color": (40, 30, 50),
        "default": False,
    },
    {
        "key":   "MINE",
        "name":  "Claymore",
        "blurb": "one BIG bang. then gone.",
        "cost":  8,
        "color": (180, 60, 40),
        "default": False,
    },
    {
        "key":   "WIRE",
        "name":  "Barbed Wire",
        "blurb": "wide, durable, slow + chip.",
        "cost":  12,
        "color": (160, 150, 120),
        "default": False,
    },
]
TRAP_BY_KEY      = {t["key"]: t for t in TRAPS}
DEFAULT_TRAPS    = [t["key"] for t in TRAPS if t["default"]]
UNLOCKABLE_TRAPS = [t["key"] for t in TRAPS if not t["default"]]
MAX_TRAP_SLOTS   = 4               # 2 defaults + up to 2 unlocked
RUN_POOL_SIZE    = 3               # picked from UNLOCKABLE_TRAPS per run


SNARK_KILLS = [
    "rude.", "unprovoked.", "they had it coming.",
    "minor improvement.", "shrug.", "another one for the pile.",
    "neighborly.", "tasteful.", "deserved.", "natural causes.",
    "cosmically inevitable.", "they were bad at unliving.",
]
WAVE_TITLES = [
    "WAVE 1: The Ones Who Couldn't Wait",
    "WAVE 2: The Ones That Used To Be Joggers",
    "WAVE 3: The HOA Showed Up",
    "WAVE 4: The Ones That Used To Be Your Neighbors",
    "WAVE 5: BIG MISTAKE",
    "WAVE 6: The Brunch Crowd",
    "WAVE 7: The Ones That Forgot Their Keys",
    "WAVE 8: The Mall Walkers",
    "WAVE 9: The Group Chat",
    "WAVE 10: BIG MISTAKE PART TWO",
    "WAVE 11: The Subscribers",
    "WAVE 12: A Concerning Number",
    "WAVE 13: The Ones Who Read The Email",
    "WAVE 14: The Ones Who Still Believe",
    "WAVE 15: ABSOLUTE STATE",
]
EPITAPHS = [
    "You held out. Briefly. The zombies are unimpressed.",
    "The bunker fell. The traps are still on backorder.",
    "Survived longer than the warranty. Not by much.",
    "Held the line until the line stopped holding back.",
    "You did your best. Your best was not, on reflection, enough.",
    "Last words, paraphrased: 'I had ONE more spike pit.'",
    "Buried under a polite number of zombies.",
]


# ----------------------------------------------------------------- helpers
def clamp(v, a, b): return a if v < a else b if v > b else v
def length(x, y):   return math.hypot(x, y)
def lerp(a, b, t):  return a + (b - a) * t

def _ground_tile():
    """Pre-rendered ground texture surface, tiled across the playfield."""
    s = pygame.Surface((128, 128))
    s.fill(COL_GROUND1)
    rng = random.Random(7)
    for _ in range(80):
        x, y = rng.randrange(128), rng.randrange(128)
        c = COL_GROUND2 if rng.random() < 0.7 else COL_CRACK
        s.set_at((x, y), c)
    for _ in range(8):
        x1 = rng.randrange(128); y1 = rng.randrange(128)
        x2 = x1 + rng.randint(-25, 25); y2 = y1 + rng.randint(-25, 25)
        pygame.draw.line(s, COL_CRACK, (x1, y1), (x2, y2), 1)
    return s

GROUND = _ground_tile()


def in_bunker(x, y, pad=0):
    return BUNKER_RECT.inflate(pad * 2, pad * 2).collidepoint(x, y)


def clamp_play(x, y, r=0):
    x = clamp(x, r, W - r)
    y = clamp(y, PLAY_TOP + r, PLAY_BOT - r)
    return x, y


# ----------------------------------------------------------------- entities
MELEE_COOLDOWN  = 0.35
MELEE_RANGE     = 78      # px from player center
MELEE_DMG       = 50      # 1-shots wave-1 zombies (28 hp); 2-3 hits mid-game
MELEE_KNOCKBACK = 520     # initial knockback velocity (px/sec)
MELEE_ANIM_T    = 0.18    # arc visual duration
MELEE_HALF_COS  = 0.5     # cos(60°) — 120° total arc


class Player:
    def __init__(self):
        self.x = float(BUNKER_CX)
        self.y = float(BUNKER_CY + BUNKER_H // 2 + 40)
        self.dirx, self.diry = 0.0, 1.0
        self.scrap = 25
        self.sel = 0  # selected trap index
        self.wob = 0.0
        self.kill_select_cd = 0.0  # debounce cycling
        self.swing_t  = 0.0  # >0 means arc visual is showing
        self.swing_cd = 0.0  # cooldown until next swing

    def update(self, dt, inp):
        ax, ay = 0.0, 0.0
        if inp.held(0, "LEFT"):  ax -= 1
        if inp.held(0, "RIGHT"): ax += 1
        if inp.held(0, "UP"):    ay -= 1
        if inp.held(0, "DOWN"):  ay += 1
        if ax or ay:
            m = math.hypot(ax, ay)
            ax, ay = ax / m, ay / m
            self.x += ax * PLAYER_SPEED * dt
            self.y += ay * PLAYER_SPEED * dt
            self.dirx, self.diry = ax, ay
            self.wob += dt * 14
        self.x, self.y = clamp_play(self.x, self.y, PLAYER_R)
        # players can't walk through the bunker either
        if BUNKER_RECT.inflate(PLAYER_R * 2, PLAYER_R * 2).collidepoint(self.x, self.y):
            bx1 = BUNKER_RECT.left  - PLAYER_R
            bx2 = BUNKER_RECT.right + PLAYER_R
            by1 = BUNKER_RECT.top   - PLAYER_R
            by2 = BUNKER_RECT.bottom + PLAYER_R
            dl, dr = self.x - bx1, bx2 - self.x
            dt_, db = self.y - by1, by2 - self.y
            m = min(dl, dr, dt_, db)
            if   m == dl: self.x = bx1
            elif m == dr: self.x = bx2
            elif m == dt_: self.y = by1
            else:          self.y = by2
        self.swing_t  = max(0.0, self.swing_t  - dt)
        self.swing_cd = max(0.0, self.swing_cd - dt)

    def try_swing(self, zombies, particles, floats):
        if self.swing_cd > 0:
            return False
        self.swing_cd = MELEE_COOLDOWN
        self.swing_t  = MELEE_ANIM_T
        hit_any = False
        for z in zombies:
            if not z.alive:
                continue
            dx, dy = z.x - self.x, z.y - self.y
            d = math.hypot(dx, dy)
            if d > MELEE_RANGE + z.r or d < 1:
                continue
            nx, ny = dx / d, dy / d
            if nx * self.dirx + ny * self.diry < MELEE_HALF_COS:
                continue
            z.hurt(MELEE_DMG)
            z.kvx += nx * MELEE_KNOCKBACK
            z.kvy += ny * MELEE_KNOCKBACK
            # impact sparks
            for _ in range(5):
                particles.append(Particle(
                    z.x, z.y,
                    nx * random.uniform(60, 180) + random.uniform(-40, 40),
                    ny * random.uniform(60, 180) + random.uniform(-40, 40),
                    (240, 220, 160),
                    random.uniform(0.25, 0.45),
                    random.randint(2, 3)))
            hit_any = True
        return hit_any

    def draw(self, surf):
        bob = math.sin(self.wob) * 2
        # melee arc (under feet/body so player draws on top)
        if self.swing_t > 0:
            t = self.swing_t / MELEE_ANIM_T  # 1 -> 0
            facing = math.atan2(self.diry, self.dirx)
            half = math.radians(60)
            arc_r = int(MELEE_RANGE * (1.05 - 0.15 * (1 - t)))
            arc_surf = pygame.Surface((arc_r * 2 + 4, arc_r * 2 + 4),
                                      pygame.SRCALPHA)
            cx_, cy_ = arc_r + 2, arc_r + 2
            steps = 14
            pts = [(cx_, cy_)]
            for i in range(steps + 1):
                a = facing - half + (2 * half) * (i / steps)
                pts.append((cx_ + math.cos(a) * arc_r,
                            cy_ + math.sin(a) * arc_r))
            alpha = int(160 * t)
            pygame.draw.polygon(arc_surf, (255, 240, 180, alpha), pts)
            pygame.draw.polygon(arc_surf, (255, 200, 80, min(220, alpha + 40)),
                                pts, 2)
            surf.blit(arc_surf,
                      (int(self.x) - cx_, int(self.y) - cy_ - int(bob)))
        # shadow
        pygame.draw.ellipse(surf, (15, 12, 8),
                            (int(self.x) - PLAYER_R, int(self.y) + 6,
                             PLAYER_R * 2, 6))
        # body
        pygame.draw.circle(surf, PCOLORS[0],
                           (int(self.x), int(self.y) - int(bob)), PLAYER_R)
        pygame.draw.circle(surf, (255, 255, 255),
                           (int(self.x), int(self.y) - int(bob)), PLAYER_R, 2)
        # facing line / "weapon"
        fx = self.x + self.dirx * (PLAYER_R + 14)
        fy = self.y + self.diry * (PLAYER_R + 14) - bob
        pygame.draw.line(surf, (220, 210, 190),
                         (int(self.x), int(self.y) - int(bob)),
                         (int(fx), int(fy)), 4)
        pygame.draw.line(surf, (255, 255, 255),
                         (int(self.x), int(self.y) - int(bob)),
                         (int(fx), int(fy)), 2)


class Zombie:
    def __init__(self, x, y, hp, speed, boss=False):
        self.x, self.y = float(x), float(y)
        self.hp_max = hp
        self.hp = hp
        self.speed = speed
        self.base_speed = speed
        self.boss = boss
        self.r = 22 if boss else 11
        self.alive = True
        self.wob = random.uniform(0, math.tau)
        self.flash = 0.0  # damage flash timer
        self.slow_t = 0.0  # electric stun
        self.burn_t = 0.0  # flame burn timer
        self.kvx, self.kvy = 0.0, 0.0  # knockback velocity
        self.stab_cd = 0.0  # cooldown between spike hits so one zombie doesn't drain a trap in a frame
        self.aggro_target = None  # (x, y) — overrides bunker steering when set
        self.aggro_t      = 0.0   # remaining seconds of aggro

    def update(self, dt, traps, bunker):
        self.wob += dt * 8
        if self.stab_cd > 0:
            self.stab_cd -= dt
        speed = self.speed
        if self.slow_t > 0:
            self.slow_t -= dt
            speed *= 0.35
        # burn DoT
        if self.burn_t > 0:
            self.burn_t -= dt
            self.hp -= 18 * dt
            if self.hp <= 0:
                self.alive = False
                return
        # apply knockback (decays exponentially)
        if abs(self.kvx) > 1 or abs(self.kvy) > 1:
            self.x += self.kvx * dt
            self.y += self.kvy * dt
            decay = max(0.0, 1.0 - 7.0 * dt)
            self.kvx *= decay
            self.kvy *= decay
        else:
            self.kvx = self.kvy = 0.0
        # aggro decay
        if self.aggro_t > 0:
            self.aggro_t -= dt
            if self.aggro_t <= 0:
                self.aggro_target = None
        # steer toward aggro target if any, else bunker center
        if self.aggro_target is not None:
            tx, ty = self.aggro_target
        else:
            tx, ty = BUNKER_CX, BUNKER_CY
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy) or 1.0
        dx, dy = dx / d, dy / d
        # wobble perpendicular
        wob = math.sin(self.wob) * 0.25
        px, py = -dy, dx
        mvx = dx + px * wob
        mvy = dy + py * wob
        m = math.hypot(mvx, mvy) or 1.0
        mvx, mvy = mvx / m, mvy / m
        # walk forward, but slide along the bunker wall if the AI is steering into it
        blocked = BUNKER_RECT.inflate(self.r * 2, self.r * 2)
        next_x = self.x + mvx * speed * dt
        next_y = self.y + mvy * speed * dt
        touching = False
        if blocked.collidepoint(next_x, next_y):
            touching = True
            if not blocked.collidepoint(next_x, self.y):
                self.x = next_x
            elif not blocked.collidepoint(self.x, next_y):
                self.y = next_y
        else:
            self.x, self.y = next_x, next_y
        # hard clamp: zombie center must never be inside the inflated bunker rect
        rect = BUNKER_RECT
        bx1, by1 = rect.left - self.r, rect.top - self.r
        bx2, by2 = rect.right + self.r, rect.bottom + self.r
        if bx1 < self.x < bx2 and by1 < self.y < by2:
            dl, dr = self.x - bx1, bx2 - self.x
            dtp, dbm = self.y - by1, by2 - self.y
            mn = min(dl, dr, dtp, dbm)
            if   mn == dl:  self.x = bx1
            elif mn == dr:  self.x = bx2
            elif mn == dtp: self.y = by1
            else:           self.y = by2
            touching = True
            # knockback into a wall: kill that component
            if mn == dl or mn == dr: self.kvx = 0.0
            else:                    self.kvy = 0.0
        if touching:
            bunker.take_damage(8 * dt * (3 if self.boss else 1))
        if self.flash > 0:
            self.flash -= dt

    def hurt(self, dmg):
        self.hp -= dmg
        self.flash = 0.12
        if self.hp <= 0:
            self.alive = False

    def draw(self, surf):
        bob = math.sin(self.wob) * (3 if self.boss else 2)
        sway = math.cos(self.wob * 0.7) * (4 if self.boss else 2)
        col = COL_ZOMBIE_D if self.boss else COL_ZOMBIE
        if self.flash > 0:
            col = (255, 240, 240)
        # shadow
        pygame.draw.ellipse(surf, (15, 12, 8),
                            (int(self.x) - self.r, int(self.y) + self.r // 2,
                             self.r * 2, max(4, self.r // 2)))
        # body
        cx, cy = int(self.x + sway), int(self.y - bob)
        pygame.draw.circle(surf, col, (cx, cy), self.r)
        pygame.draw.circle(surf, (20, 30, 15), (cx, cy), self.r, 2)
        # eyes
        ex = self.r // 3
        ey = self.r // 4
        er = max(2, self.r // 5)
        pygame.draw.circle(surf, (200, 30, 30), (cx - ex, cy - ey), er)
        pygame.draw.circle(surf, (200, 30, 30), (cx + ex, cy - ey), er)
        # boss accent
        if self.boss:
            pygame.draw.circle(surf, (40, 60, 30), (cx, cy + self.r // 2), self.r // 2, 2)
            # hp bar
            bw = self.r * 3
            f  = max(0, self.hp / self.hp_max)
            pygame.draw.rect(surf, (40, 20, 20),
                             (cx - bw // 2, cy - self.r - 14, bw, 5))
            pygame.draw.rect(surf, COL_RED,
                             (cx - bw // 2, cy - self.r - 14, int(bw * f), 5))
        # burn fx
        if self.burn_t > 0:
            for i in range(3):
                fx = cx + random.randint(-self.r, self.r)
                fy = cy - self.r - random.randint(0, 12)
                pygame.draw.circle(surf, COL_FLAME_O, (fx, fy), 2)


class Trap:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.x, self.y = float(x), float(y)
        self.alive = True
        self.t = 0.0
        if kind == "SPIKE":
            self.spikes_max = 8
            self.spikes     = 8
            self.spike_dmg  = 35
            self.r = 26
        elif kind == "FLAME":
            # Persistent fire field. Zombies in radius get a sustained
            # burn DoT so they keep burning after leaving.
            self.life = 30.0
            self.r    = 80
        elif kind == "FENCE":
            # Stun fence: hits hard with status, soft on damage.
            self.hp = 350
            self.r  = 70
        elif kind == "TAR":
            # Slow field, no damage, expires by time.
            self.life = 40.0
            self.r    = 95
        elif kind == "MINE":
            # One-shot AOE. Armed after a short setup so it doesn't insta-pop.
            self.arm_t   = 0.6
            self.r       = 26       # trigger radius
            self.boom_r  = 170      # AOE radius
            self.dmg     = 220
            self.boom    = False    # set True on the frame it explodes
            self.boom_age= 0.0
        elif kind == "WIRE":
            # Big durable obstacle: slows + chip damage.
            self.hp = 500
            self.r  = 70
        elif kind == "TURRET":
            self.hp      = 130           # was 160 — slightly squishier
            self.r       = 18
            self.range   = 320
            self.fire_cd = 0.0
            self.angle   = 0.0           # current barrel direction
            self.target  = None          # cached current target
            self.cone    = math.radians(22.5)  # half-angle = 22.5° (45° total)
            self.rot_spd = 2.5           # rad/sec rotation cap
            self.aggro_radius = 360      # zombies inside hear it shoot

    def update(self, dt, zombies, bullets):
        self.t += dt
        if self.kind == "SPIKE":
            for z in zombies:
                if not z.alive or z.stab_cd > 0: continue
                if math.hypot(z.x - self.x, z.y - self.y) < self.r * 0.65 + z.r:
                    z.hurt(self.spike_dmg)
                    z.stab_cd = 0.4   # this zombie can't eat another spike for a moment
                    self.spikes -= 1
                    if self.spikes <= 0:
                        self.alive = False
                        return
        elif self.kind == "FLAME":
            # Persistent fire field — light radius, big burn DoT carry.
            for z in zombies:
                if not z.alive: continue
                if math.hypot(z.x - self.x, z.y - self.y) < self.r:
                    z.hurt(10 * dt)              # gentle direct damage
                    z.burn_t = max(z.burn_t, 2.5)
            if self.t > self.life:
                self.alive = False
        elif self.kind == "FENCE":
            for z in zombies:
                if not z.alive: continue
                if math.hypot(z.x - self.x, z.y - self.y) < self.r:
                    z.hurt(25 * dt)
                    z.slow_t = max(z.slow_t, 1.5)   # strong stagger
                    self.hp -= 8 * dt
            if self.hp <= 0:
                self.alive = False
        elif self.kind == "TAR":
            for z in zombies:
                if not z.alive: continue
                if math.hypot(z.x - self.x, z.y - self.y) < self.r:
                    z.slow_t = max(z.slow_t, 0.3)
            if self.t > self.life:
                self.alive = False
        elif self.kind == "WIRE":
            for z in zombies:
                if not z.alive: continue
                if math.hypot(z.x - self.x, z.y - self.y) < self.r:
                    z.hurt(12 * dt)
                    z.slow_t = max(z.slow_t, 0.4)
                    self.hp -= 3 * dt
            if self.hp <= 0:
                self.alive = False
        elif self.kind == "MINE":
            if self.boom:
                # detonation frame already handled; trap goes away next frame
                self.boom_age += dt
                if self.boom_age > 0.5:
                    self.alive = False
                return
            self.arm_t = max(0, self.arm_t - dt)
            if self.arm_t > 0:
                return
            for z in zombies:
                if not z.alive: continue
                if math.hypot(z.x - self.x, z.y - self.y) < self.r + z.r:
                    # KABOOM
                    self.boom = True
                    self.boom_age = 0.0
                    for zz in zombies:
                        if not zz.alive: continue
                        dd = math.hypot(zz.x - self.x, zz.y - self.y)
                        if dd < self.boom_r + zz.r:
                            zz.hurt(self.dmg * (1.0 - dd / (self.boom_r + zz.r)))
                            # knockback outward
                            nx = (zz.x - self.x) / (dd or 1)
                            ny = (zz.y - self.y) / (dd or 1)
                            zz.kvx += nx * 700
                            zz.kvy += ny * 700
                    break
        elif self.kind == "TURRET":
            self.fire_cd -= dt
            # take contact damage from any zombie touching the cabinet
            for z in zombies:
                if not z.alive: continue
                if math.hypot(z.x - self.x, z.y - self.y) < z.r + self.r:
                    self.hp -= 18 * dt
            if self.hp <= 0:
                self.alive = False
                return
            # find best target in range
            best, bd = None, self.range
            for z in zombies:
                if not z.alive: continue
                d = math.hypot(z.x - self.x, z.y - self.y)
                if d < bd:
                    bd = d; best = z
            self.target = best
            if best is not None:
                want = math.atan2(best.y - self.y, best.x - self.x)
                diff = (want - self.angle + math.pi) % math.tau - math.pi
                step = self.rot_spd * dt
                if abs(diff) <= step:
                    self.angle = want
                else:
                    self.angle += step if diff > 0 else -step
                # fire only if target is within the firing cone
                if self.fire_cd <= 0 and abs(diff) < self.cone:
                    self.fire_cd = 0.45
                    bx = self.x + math.cos(self.angle) * 22
                    by = self.y + math.sin(self.angle) * 22
                    bullets.append(Bullet(bx, by, best))
                    # the muzzle report draws zombies' attention to this turret
                    for z in zombies:
                        if not z.alive: continue
                        if math.hypot(z.x - self.x,
                                      z.y - self.y) < self.aggro_radius:
                            z.aggro_target = (self.x, self.y)
                            z.aggro_t      = 6.0

    def draw(self, surf):
        if self.kind == "SPIKE":
            pygame.draw.circle(surf, (50, 38, 26), (int(self.x), int(self.y)), self.r)
            pygame.draw.circle(surf, (30, 22, 16), (int(self.x), int(self.y)), self.r, 2)
            for i in range(self.spikes_max):
                a = i * (math.tau / self.spikes_max)
                x1 = self.x + math.cos(a) * 6
                y1 = self.y + math.sin(a) * 6
                x2 = self.x + math.cos(a) * (self.r - 4)
                y2 = self.y + math.sin(a) * (self.r - 4)
                if i < self.spikes:
                    pygame.draw.line(surf, (180, 170, 150),
                                     (x1, y1), (x2, y2), 2)
                    pygame.draw.circle(surf, (220, 210, 190),
                                       (int(x2), int(y2)), 2)
                else:
                    # broken stub
                    sx = self.x + math.cos(a) * 9
                    sy = self.y + math.sin(a) * 9
                    pygame.draw.line(surf, (70, 55, 40),
                                     (x1, y1), (sx, sy), 2)
        elif self.kind == "FLAME":
            # brazier
            pygame.draw.circle(surf, (60, 40, 30), (int(self.x), int(self.y)), 14)
            pygame.draw.circle(surf, (90, 60, 40), (int(self.x), int(self.y)), 14, 2)
            life_t = self.life - self.t
            scale = 1.0 if life_t > 3 else max(0.35, life_t / 3)
            for i in range(12):
                a = self.t * 3 + i * (math.tau / 12)
                rr = self.r * scale * (0.55 + 0.4 * math.sin(self.t * 5 + i))
                fx = self.x + math.cos(a) * rr * 0.55
                fy = self.y + math.sin(a) * rr * 0.55
                pygame.draw.circle(surf, COL_FLAME_O, (int(fx), int(fy)),
                                   max(3, int(9 * scale)))
                pygame.draw.circle(surf, COL_FLAME_Y, (int(fx), int(fy)),
                                   max(2, int(4 * scale)))
        elif self.kind == "FENCE":
            f = max(0, self.hp / 350)
            for off in (-self.r, self.r):
                pygame.draw.rect(surf, (90, 90, 100),
                                 (int(self.x + off) - 3, int(self.y) - 18, 6, 36))
            n = 16
            for i in range(n):
                a1 = self.t * 6 + i * (math.tau / n)
                a2 = a1 + 0.4
                r1 = self.r * (0.7 + 0.3 * random.random())
                r2 = self.r * (0.7 + 0.3 * random.random())
                x1 = self.x + math.cos(a1) * r1
                y1 = self.y + math.sin(a1) * r1
                x2 = self.x + math.cos(a2) * r2
                y2 = self.y + math.sin(a2) * r2
                col = (int(120 + 100 * f), int(180 + 40 * f), 255)
                pygame.draw.line(surf, col, (x1, y1), (x2, y2), 2)
        elif self.kind == "TAR":
            # oily blob with a slow inner ripple
            blob = pygame.Surface((self.r * 2 + 4, self.r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(blob, (30, 22, 32, 200),
                               (self.r + 2, self.r + 2), self.r)
            pygame.draw.circle(blob, (60, 45, 60, 230),
                               (self.r + 2, self.r + 2), self.r, 3)
            surf.blit(blob, (int(self.x) - self.r - 2, int(self.y) - self.r - 2))
            for i in range(5):
                a = self.t * 1.5 + i * (math.tau / 5)
                rr = self.r * 0.55 * (0.7 + 0.3 * math.sin(self.t * 2 + i))
                fx = int(self.x + math.cos(a) * rr)
                fy = int(self.y + math.sin(a) * rr)
                pygame.draw.circle(surf, (70, 55, 75), (fx, fy), 3)
        elif self.kind == "WIRE":
            f = max(0, self.hp / 500)
            # criss-cross strands
            pygame.draw.circle(surf, (50, 45, 38),
                               (int(self.x), int(self.y)), self.r, 1)
            for i in range(20):
                a1 = i * (math.tau / 20)
                a2 = a1 + 1.4
                x1 = self.x + math.cos(a1) * self.r * 0.95
                y1 = self.y + math.sin(a1) * self.r * 0.95
                x2 = self.x + math.cos(a2) * self.r * 0.55
                y2 = self.y + math.sin(a2) * self.r * 0.55
                pygame.draw.line(surf, (170, 160, 130), (x1, y1), (x2, y2), 1)
            # barb dots
            for i in range(12):
                a = i * (math.tau / 12)
                bx = int(self.x + math.cos(a) * self.r * 0.7)
                by = int(self.y + math.sin(a) * self.r * 0.7)
                pygame.draw.circle(surf, (220, 210, 180), (bx, by), 2)
            # subtle damage tint
            if f < 0.5:
                pygame.draw.circle(surf, (90, 50, 50),
                                   (int(self.x), int(self.y)), int(self.r * 0.6), 1)
        elif self.kind == "MINE":
            if self.boom:
                # expanding ring + bright core
                k = clamp(self.boom_age / 0.5, 0, 1)
                rr = int(self.boom_r * k)
                ring = pygame.Surface((rr * 2 + 4, rr * 2 + 4), pygame.SRCALPHA)
                alpha = int(220 * (1 - k))
                pygame.draw.circle(ring, (255, 200, 80, alpha),
                                   (rr + 2, rr + 2), rr, 6)
                pygame.draw.circle(ring, (255, 120, 40, alpha // 2),
                                   (rr + 2, rr + 2), max(2, rr - 6), 4)
                surf.blit(ring, (int(self.x) - rr - 2, int(self.y) - rr - 2))
            else:
                # disk with blink
                pygame.draw.circle(surf, (60, 50, 40),
                                   (int(self.x), int(self.y)), self.r)
                pygame.draw.circle(surf, (120, 60, 40),
                                   (int(self.x), int(self.y)), self.r, 2)
                blink = (math.sin(self.t * 8) > 0) if self.arm_t <= 0 \
                        else (math.sin(self.t * 20) > 0)
                if blink:
                    pygame.draw.circle(surf, (255, 80, 40),
                                       (int(self.x), int(self.y)), 4)
        elif self.kind == "TURRET":
            pygame.draw.circle(surf, (60, 60, 70), (int(self.x), int(self.y)), self.r + 3)
            pygame.draw.circle(surf, COL_TURRET, (int(self.x), int(self.y)), self.r)
            pygame.draw.circle(surf, (40, 40, 50), (int(self.x), int(self.y)), self.r, 2)
            # 45° firing cone (faint) — shows the player exactly what it can hit
            cone_pts = [(int(self.x), int(self.y))]
            steps = 10
            cone_len = min(self.range, 200)
            for i in range(steps + 1):
                a = self.angle - self.cone + (2 * self.cone) * (i / steps)
                cone_pts.append((int(self.x + math.cos(a) * cone_len),
                                 int(self.y + math.sin(a) * cone_len)))
            cs = pygame.Surface((int(cone_len) * 2 + 4, int(cone_len) * 2 + 4),
                                pygame.SRCALPHA)
            ox, oy = int(self.x) - int(cone_len) - 2, int(self.y) - int(cone_len) - 2
            shifted = [(p[0] - ox, p[1] - oy) for p in cone_pts]
            pygame.draw.polygon(cs, (200, 200, 220, 28), shifted)
            pygame.draw.polygon(cs, (200, 200, 220, 70), shifted, 1)
            surf.blit(cs, (ox, oy))
            # barrel
            bx = self.x + math.cos(self.angle) * 22
            by = self.y + math.sin(self.angle) * 22
            pygame.draw.line(surf, (40, 40, 50),
                             (int(self.x), int(self.y)), (int(bx), int(by)), 6)
            pygame.draw.circle(surf, (200, 200, 200), (int(bx), int(by)), 3)
            # hp ring
            f = max(0, self.hp / 130)
            pygame.draw.arc(surf, COL_HP_OK if f > 0.4 else COL_RED,
                            (int(self.x) - self.r - 6, int(self.y) - self.r - 6,
                             (self.r + 6) * 2, (self.r + 6) * 2),
                            -math.pi / 2, -math.pi / 2 + math.tau * f, 2)


class Bullet:
    def __init__(self, x, y, target):
        self.x, self.y = float(x), float(y)
        dx, dy = target.x - x, target.y - y
        d = math.hypot(dx, dy) or 1.0
        self.vx, self.vy = dx / d * 900, dy / d * 900
        self.life = 0.6
        self.alive = True
        self.dmg = 28

    def update(self, dt, zombies):
        self.life -= dt
        if self.life <= 0:
            self.alive = False; return
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x < 0 or self.x > W or self.y < PLAY_TOP or self.y > PLAY_BOT:
            self.alive = False; return
        for z in zombies:
            if not z.alive: continue
            if math.hypot(z.x - self.x, z.y - self.y) < z.r + 4:
                z.hurt(self.dmg)
                self.alive = False
                return

    def draw(self, surf):
        pygame.draw.circle(surf, (255, 230, 120), (int(self.x), int(self.y)), 3)
        pygame.draw.line(surf, (255, 200, 90),
                         (int(self.x), int(self.y)),
                         (int(self.x - self.vx * 0.012),
                          int(self.y - self.vy * 0.012)), 2)


class TrapPickup:
    """A trap-blueprint dropped by a boss or by a swap. Persistent."""
    PICKUP_R = 22

    def __init__(self, kind, x, y):
        self.kind  = kind
        self.x, self.y = float(x), float(y)
        self.alive = True
        self.t     = random.uniform(0, math.tau)

    def update(self, dt):
        self.t += dt  # purely cosmetic

    def draw(self, surf):
        col  = TRAP_BY_KEY[self.kind]["color"]
        name = TRAP_BY_KEY[self.kind]["name"]
        bob  = math.sin(self.t * 2) * 3
        cx, cy = int(self.x), int(self.y - bob)
        # halo
        glow = pygame.Surface((self.PICKUP_R * 4, self.PICKUP_R * 4),
                              pygame.SRCALPHA)
        for i in range(3):
            pygame.draw.circle(glow,
                               (col[0], col[1], col[2], 50 - i * 12),
                               (self.PICKUP_R * 2, self.PICKUP_R * 2),
                               int(self.PICKUP_R * 1.6 - i * 4))
        surf.blit(glow, (cx - self.PICKUP_R * 2, cy - self.PICKUP_R * 2))
        # diamond crystal
        s = self.PICKUP_R
        pts = [(cx, cy - s), (cx + s * 2 // 3, cy),
               (cx, cy + s), (cx - s * 2 // 3, cy)]
        pygame.draw.polygon(surf, col, pts)
        pygame.draw.polygon(surf, (255, 255, 255), pts, 2)
        # name tag below
        blit(surf, name.upper(), 14, (240, 230, 200),
             (cx, cy + s + 14))


class Scrap:
    def __init__(self, x, y, amount=1):
        self.x, self.y = float(x), float(y)
        self.amount = amount
        self.life = 22.0
        self.alive = True
        self.bob = random.uniform(0, math.tau)

    def update(self, dt):
        self.life -= dt
        self.bob += dt * 4
        if self.life <= 0:
            self.alive = False

    def draw(self, surf):
        b = math.sin(self.bob) * 2
        r = 5 if self.amount < 5 else 8
        # blink when about to despawn
        if self.life < 3 and int(self.life * 6) % 2 == 0:
            return
        glow = pygame.Surface((r * 6, r * 6), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 170, 50, 60), (r * 3, r * 3), r * 3)
        surf.blit(glow, (int(self.x) - r * 3, int(self.y) - r * 3 - int(b)))
        pygame.draw.circle(surf, COL_SCRAP, (int(self.x), int(self.y) - int(b)), r)
        pygame.draw.circle(surf, (255, 240, 180),
                           (int(self.x) - 1, int(self.y) - int(b) - 1), max(1, r // 3))


class FloatingText:
    def __init__(self, text, x, y, color=(220, 210, 180), size=18, life=1.4):
        self.text = text
        self.x, self.y = x, y
        self.color = color
        self.size = size
        self.life = life
        self.maxlife = life
        self.alive = True
        self.vx = random.uniform(-12, 12)
        self.vy = -28

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 18 * dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf):
        a = clamp(self.life / self.maxlife, 0, 1)
        col = tuple(int(c * a + 0 * (1 - a)) for c in self.color)
        blit(surf, self.text, self.size, col, (int(self.x), int(self.y)))


class Particle:
    def __init__(self, x, y, vx, vy, color, life=0.6, r=2):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.color = color
        self.life = life
        self.maxlife = life
        self.r = r
        self.alive = True

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.92
        self.vy *= 0.92
        if self.life <= 0:
            self.alive = False

    def draw(self, surf):
        if self.life <= 0: return
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), self.r)


class Bunker:
    def __init__(self):
        self.hp = BUNKER_HP
        self.shake = 0.0
        self.hit_flash = 0.0

    def take_damage(self, d):
        self.hp -= d
        self.shake = min(self.shake + d * 0.4, 8)
        self.hit_flash = 0.15

    def update(self, dt):
        self.shake = max(0, self.shake - dt * 18)
        self.hit_flash = max(0, self.hit_flash - dt)

    def draw(self, surf):
        sx = random.uniform(-self.shake, self.shake)
        sy = random.uniform(-self.shake, self.shake)
        r  = BUNKER_RECT.move(int(sx), int(sy))
        # outer wall
        pygame.draw.rect(surf, COL_BUNKER, r)
        pygame.draw.rect(surf, COL_BUNKER_2, r, 5)
        # inner detail
        ir = r.inflate(-30, -30)
        pygame.draw.rect(surf, (60, 58, 50), ir)
        pygame.draw.rect(surf, COL_BUNKER_HI, ir, 2)
        # rivets
        for cx in (r.left + 12, r.right - 12):
            for cy in (r.top + 12, r.bottom - 12):
                pygame.draw.circle(surf, (40, 38, 30), (cx, cy), 4)
                pygame.draw.circle(surf, (160, 150, 120), (cx, cy), 2)
        # door
        d = pygame.Rect(0, 0, 30, 22); d.midbottom = (r.centerx, r.bottom - 10)
        pygame.draw.rect(surf, (30, 25, 20), d)
        pygame.draw.rect(surf, (90, 80, 60), d, 2)
        # cracks based on damage
        damage = 1 - self.hp / BUNKER_HP
        rng = random.Random(1)
        for _ in range(int(damage * 14)):
            x1 = rng.randint(r.left + 5, r.right - 5)
            y1 = rng.randint(r.top + 5, r.bottom - 5)
            x2 = x1 + rng.randint(-18, 18)
            y2 = y1 + rng.randint(-18, 18)
            pygame.draw.line(surf, (30, 22, 18), (x1, y1), (x2, y2), 1)
        # hit flash
        if self.hit_flash > 0:
            ov = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            a = int(120 * self.hit_flash / 0.15)
            ov.fill((255, 80, 60, a))
            surf.blit(ov, r.topleft)


# ----------------------------------------------------------------- game
class Game:
    def __init__(self):
        self.inp   = Input()
        self.state = "ATTRACT"
        self._reset()
        # attract demo zombies
        self._demo_zoms = [self._spawn_demo_zom() for _ in range(8)]
        self._title_t = 0.0
        self._quit_hold = 0.0
        self._game_over_t = 0.0
        self._epitaph = ""
        self._jump_held_t   = 0.0
        self._jump_consumed = False

    def _reset(self):
        self.player  = Player()
        self.bunker  = Bunker()
        self.zombies = []
        self.traps   = []
        self.bullets = []
        self.scraps  = []
        self.floats  = []
        self.particles = []
        self.pickups = []
        # roll the run's unlockable-trap pool fresh on each new game
        self.run_pool = random.sample(UNLOCKABLE_TRAPS,
                                      min(RUN_POOL_SIZE, len(UNLOCKABLE_TRAPS)))
        self.unlocked = list(DEFAULT_TRAPS)  # ["SPIKE", "TURRET"]
        self.wave    = 0
        self.kills   = 0
        self.phase   = "INTRO"   # INTRO | ACTIVE | SCAVENGE
        self.phase_t = WAVE_INTRO_T
        self.spawn_q = []
        self.wave_total = 0
        self.wave_killed = 0
        self._jump_held_t = 0.0
        self._jump_consumed = False
        self._next_wave()

    # ------------------ wave management ------------------
    def _next_wave(self):
        self.wave += 1
        self.phase = "INTRO"
        self.phase_t = WAVE_INTRO_T
        # build spawn queue
        n = 8 + (self.wave - 1) * 4
        speed = 50 + (self.wave - 1) * 4
        hp    = 28 + (self.wave - 1) * 9
        is_boss_wave = (self.wave % 5 == 0)
        self.spawn_q = []
        # spread spawns over (8 + 0.6*n) seconds-ish, capped
        active_t = clamp(8 + 0.5 * n, 14, 40)
        for i in range(n):
            t = (i / n) * active_t + random.uniform(0, 0.3)
            self.spawn_q.append((t, hp, speed, False))
        if is_boss_wave:
            self.spawn_q.append((active_t * 0.45,
                                 hp * 6, max(28, speed - 18), True))
        # sort by time
        self.spawn_q.sort(key=lambda s: s[0])
        self.wave_total = len(self.spawn_q)
        self.wave_killed = 0
        self._active_t = active_t

    def _spawn_zombie(self, hp, speed, boss):
        edge = random.randint(0, 3)
        if edge == 0:   # left
            x, y = -20, random.uniform(PLAY_TOP + 30, PLAY_BOT - 30)
        elif edge == 1: # right
            x, y = W + 20, random.uniform(PLAY_TOP + 30, PLAY_BOT - 30)
        elif edge == 2: # top
            x, y = random.uniform(40, W - 40), PLAY_TOP - 20
        else:           # bottom
            x, y = random.uniform(40, W - 40), PLAY_BOT + 20
        self.zombies.append(Zombie(x, y, hp, speed, boss))

    def _spawn_demo_zom(self):
        return Zombie(random.uniform(0, W),
                      random.uniform(PLAY_TOP + 50, PLAY_BOT - 50),
                      30, 40, False)

    # ------------------ main loop ------------------
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

            pygame.display.flip()

    # ------------------ attract ------------------
    def _attract(self, dt):
        self._title_t += dt
        # quit on any player holding ATTACK+JUMP simultaneously
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        # start on ATTACK from any player (also accept JUMP after a short delay
        # so we don't immediately consume a held button from the launcher)
        for pid in range(4):
            if self.inp.just(pid, "ATTACK") or (
                    self._title_t > 0.5 and self.inp.just(pid, "JUMP")):
                self._reset()
                self.state = "PLAYING"
                return

        # update demo zombies
        for z in self._demo_zoms:
            z.x += math.cos(z.wob) * 14 * dt
            z.y += math.sin(z.wob * 0.7) * 12 * dt
            z.wob += dt * 0.4
            if z.x < -30: z.x = W + 30
            if z.x > W + 30: z.x = -30
            if z.y < PLAY_TOP - 30: z.y = PLAY_BOT + 30
            if z.y > PLAY_BOT + 30: z.y = PLAY_TOP - 30

        # draw
        screen.fill(COL_BG)
        self._draw_ground()
        for z in self._demo_zoms:
            z.draw(screen)
        # title
        pulse = 1 + 0.02 * math.sin(self._title_t * 2)
        title = "BUNKER  DOWN"
        blit(screen, title, 72,
             (220, 80, 60), (CX, 220))
        blit(screen, title, 72,
             (240, 220, 200), (CX - 3, 217))
        blit(screen, "they are coming. you have a hammer and ill-advised optimism.",
             24, COL_DIM, (CX, 290))

        # rules
        rules = [
            ("MOVE",            "ARROW KEYS"),
            ("MELEE SWING",     "ATTACK  (120° arc)"),
            ("CYCLE  TRAP",     "tap JUMP"),
            ("PLACE  TRAP",     "hold JUMP"),
            ("AUTO-PICK SCRAP", "walk over it"),
            ("QUIT",            "hold ATTACK + JUMP"),
        ]
        y = 430
        for k, v in rules:
            blit(screen, k, 24, COL_TEXT, (CX - 60, y), anchor="midright")
            blit(screen, v, 24, (200, 170, 80), (CX - 30, y), anchor="midleft")
            y += 36

        # trap list — start kit + this-run drop pool
        y = 660
        blit(screen, "you start with:", 18, COL_DIM, (CX - 480, y - 28),
             anchor="midleft")
        blit(screen, "boss zombies drop one of these (rolled per run):",
             18, COL_DIM, (CX + 120, y - 28), anchor="midleft")
        cards = [(k, True)  for k in DEFAULT_TRAPS]            # start kit
        cards += [(k, False) for k in self.run_pool]            # this run's pool
        for i, (key, owned) in enumerate(cards):
            t = TRAP_BY_KEY[key]
            x = CX - 540 + i * 220
            box = pygame.Rect(x, y, 200, 130)
            pygame.draw.rect(screen, (40, 32, 26) if owned else (28, 24, 22),
                             box)
            pygame.draw.rect(screen, t["color"], box, 2)
            tag = "START" if owned else "DROP"
            blit(screen, tag, 11,
                 (180, 220, 180) if owned else (220, 180, 80),
                 (box.x + 8, box.y + 8), anchor="topleft")
            blit(screen, t["name"], 18, t["color"],
                 (box.centerx, box.y + 36))
            blit(screen, f"{t['cost']} scrap", 14, COL_SCRAP,
                 (box.centerx, box.y + 62))
            blit(screen, t["blurb"], 11, COL_DIM,
                 (box.centerx, box.y + 96))

        # blink prompt
        if int(self._title_t * 2) % 2 == 0:
            blit(screen, "press ATTACK to begin", 36, (240, 230, 180),
                 (CX, H - 80))

    # ------------------ playing ------------------
    def _playing(self, dt):
        # quit hold (two players)
        holders = [p for p in range(4)
                   if self.inp.held(p, "ATTACK") and self.inp.held(p, "JUMP")]
        if len(holders) >= 2:
            self._quit_hold += dt
        else:
            self._quit_hold = 0.0
        if self._quit_hold >= 5.0:
            pygame.quit(); sys.exit()

        # ---------- update ----------
        self.player.update(dt, self.inp)
        self.bunker.update(dt)

        # ATTACK = melee swing.
        # JUMP: tap (<0.35s) cycles the selected trap; hold ≥0.35s places it.
        if self.inp.just(0, "ATTACK"):
            self.player.try_swing(self.zombies, self.particles, self.floats)
        if self.inp.held(0, "JUMP"):
            self._jump_held_t += dt
            if (not self._jump_consumed) and self._jump_held_t >= 0.35:
                self._try_place_trap()
                self._jump_consumed = True
        else:
            if self._jump_held_t > 0 and not self._jump_consumed \
                    and self._jump_held_t < 0.35:
                self.player.sel = (self.player.sel + 1) % len(self.unlocked)
            self._jump_held_t   = 0.0
            self._jump_consumed = False

        # phases
        self.phase_t -= dt
        if self.phase == "INTRO":
            if self.phase_t <= 0:
                self.phase = "ACTIVE"
                self.phase_t = self._active_t + 4.0
        elif self.phase == "ACTIVE":
            # spawn from queue
            t_into = self._active_t + 4.0 - self.phase_t  # how far in
            while self.spawn_q and self.spawn_q[0][0] <= t_into:
                _, hp, speed, boss = self.spawn_q.pop(0)
                self._spawn_zombie(hp, speed, boss)
            # transition: active phase ends when all zombies dead and queue empty
            if not self.spawn_q and not any(z.alive for z in self.zombies):
                self.phase = "SCAVENGE"
                self.phase_t = SCAVENGE_T
                self.floats.append(FloatingText(
                    "WAVE CLEARED — scavenge phase", CX, CY - 60,
                    (220, 220, 140), 36, 2.5))
        elif self.phase == "SCAVENGE":
            if self.phase_t <= 0:
                self._next_wave()

        # update zombies / traps / bullets — any of these can kill zombies,
        # plus melee (handled above) may have already flipped some to dead.
        for z in self.zombies:
            if z.alive:
                z.update(dt, self.traps, self.bunker)

        for t in self.traps:
            if t.alive:
                t.update(dt, self.zombies, self.bullets)
        self.traps = [t for t in self.traps if t.alive]

        for b in self.bullets:
            if b.alive:
                b.update(dt, self.zombies)
        self.bullets = [b for b in self.bullets if b.alive]

        # single kill-sweep — pays scrap for every death this frame
        # regardless of the damage source (melee, burn DoT, traps, bullets).
        for z in self.zombies:
            if not z.alive:
                self._on_kill(z)
        self.zombies = [z for z in self.zombies if z.alive]

        # scrap
        for s in self.scraps:
            s.update(dt)
            if s.alive and math.hypot(s.x - self.player.x, s.y - self.player.y) < 26:
                self.player.scrap += s.amount
                s.alive = False
                self.floats.append(FloatingText(
                    f"+{s.amount}", s.x, s.y - 6, COL_SCRAP, 14, 0.9))
        self.scraps = [s for s in self.scraps if s.alive]

        # trap pickups (persistent — never expire on their own)
        for pu in self.pickups:
            pu.update(dt)
        for pu in self.pickups:
            if not pu.alive: continue
            if math.hypot(pu.x - self.player.x, pu.y - self.player.y) \
                    < TrapPickup.PICKUP_R + PLAYER_R + 4:
                self._acquire_pickup(pu)
        self.pickups = [p for p in self.pickups if p.alive]

        # floats / particles
        for f in self.floats: f.update(dt)
        self.floats = [f for f in self.floats if f.alive]
        for p in self.particles: p.update(dt)
        self.particles = [p for p in self.particles if p.alive]

        # game over?
        if self.bunker.hp <= 0:
            self.state = "GAME_OVER"
            self._game_over_t = 0.0
            self._epitaph = random.choice(EPITAPHS)
            return

        # ---------- draw ----------
        self._draw_world()
        self._draw_hud()

        # place-trap charge ring above player
        if self._jump_held_t > 0 and not self._jump_consumed:
            t = min(self._jump_held_t / 0.35, 1.0)
            cx, cy = int(self.player.x), int(self.player.y) - PLAYER_R - 14
            pygame.draw.arc(screen, (200, 200, 200),
                            (cx - 12, cy - 12, 24, 24),
                            -math.pi / 2,
                            -math.pi / 2 + math.tau * t, 3)

        # quit progress bar
        if self._quit_hold > 0:
            t = min(self._quit_hold / 5.0, 1.0)
            pygame.draw.rect(screen, (60, 20, 20), (0, H - 10, W, 10))
            pygame.draw.rect(screen, (220, 50, 50), (0, H - 10, int(W * t), 10))

    def _try_place_trap(self):
        if self.phase == "INTRO":
            return
        if not self.unlocked:
            return
        self.player.sel = self.player.sel % len(self.unlocked)
        trap = TRAP_BY_KEY[self.unlocked[self.player.sel]]
        # cannot place inside bunker
        if in_bunker(self.player.x, self.player.y, pad=4):
            self.floats.append(FloatingText(
                "not in the bunker, genius",
                self.player.x, self.player.y - 22, (240, 180, 100), 14, 1.2))
            return
        # cannot place too close to existing trap of any kind
        for existing in self.traps:
            if math.hypot(existing.x - self.player.x,
                          existing.y - self.player.y) < 38:
                self.floats.append(FloatingText(
                    "too crowded", self.player.x, self.player.y - 22,
                    (240, 180, 100), 14, 1.0))
                return
        if self.player.scrap < trap["cost"]:
            self.floats.append(FloatingText(
                f"need {trap['cost']} scrap",
                self.player.x, self.player.y - 22, COL_RED, 14, 1.2))
            return
        self.player.scrap -= trap["cost"]
        self.traps.append(Trap(trap["key"], self.player.x, self.player.y))
        self.floats.append(FloatingText(
            f"-{trap['cost']}", self.player.x, self.player.y - 22,
            COL_DIM, 14, 0.9))

    def _acquire_pickup(self, pu):
        name = TRAP_BY_KEY[pu.kind]["name"]
        # duplicate of something the player already owns → some scrap instead
        if pu.kind in self.unlocked:
            self.player.scrap += 20
            self.floats.append(FloatingText(
                f"already have {name} — +20 scrap",
                pu.x, pu.y - 6, COL_SCRAP, 14, 1.4))
            pu.alive = False
            return
        # free slot — just slot it in and auto-select it
        if len(self.unlocked) < MAX_TRAP_SLOTS:
            self.unlocked.append(pu.kind)
            self.player.sel = len(self.unlocked) - 1
            self.floats.append(FloatingText(
                f"unlocked  {name.upper()}",
                pu.x, pu.y - 6, (220, 220, 140), 24, 1.8))
            pu.alive = False
            return
        # slots full — only swap with the currently selected slot, and only
        # if that slot is a non-default (so SPIKE/TURRET stick around).
        sel_key = self.unlocked[self.player.sel]
        if TRAP_BY_KEY[sel_key]["default"]:
            self.floats.append(FloatingText(
                "select a non-default trap to swap",
                self.player.x, self.player.y - 22,
                (240, 180, 100), 14, 1.2))
            return
        # do the swap: the old kind drops here as a fresh pickup
        old_name = TRAP_BY_KEY[sel_key]["name"]
        self.unlocked[self.player.sel] = pu.kind
        # spawn dropped pickup slightly offset so it doesn't re-trigger immediately
        ox = self.player.x - self.player.dirx * 32
        oy = self.player.y - self.player.diry * 32
        self.pickups.append(TrapPickup(sel_key, ox, oy))
        self.floats.append(FloatingText(
            f"swapped: {old_name} -> {name}",
            pu.x, pu.y - 6, (220, 220, 140), 18, 1.8))
        pu.alive = False

    def _on_kill(self, z):
        # avoid double-counting if already counted
        if getattr(z, "_counted", False):
            return
        z._counted = True
        self.kills += 1
        self.wave_killed += 1
        # scrap drop
        amount = 25 if z.boss else random.randint(1, 3)
        self.scraps.append(Scrap(z.x, z.y, amount))
        # bosses drop a trap pickup from the run pool (prefer something the
        # player doesn't already own, otherwise just any pool entry)
        if z.boss and self.run_pool:
            unowned = [k for k in self.run_pool if k not in self.unlocked]
            kind = random.choice(unowned) if unowned else random.choice(self.run_pool)
            self.pickups.append(TrapPickup(kind, z.x, z.y))
        # blood particles
        for _ in range(8 if not z.boss else 16):
            self.particles.append(Particle(
                z.x, z.y,
                random.uniform(-90, 90), random.uniform(-90, 90),
                (random.randint(110, 170), 30, 30),
                random.uniform(0.4, 0.8),
                random.randint(2, 3)))
        # snark every ~6 kills
        if self.kills % 6 == 0:
            self.floats.append(FloatingText(
                random.choice(SNARK_KILLS),
                z.x, z.y - 30, (220, 200, 150), 14, 1.4))

    # ------------------ rendering ------------------
    def _draw_ground(self):
        for x in range(0, W, 128):
            for y in range(PLAY_TOP, PLAY_BOT, 128):
                screen.blit(GROUND, (x, y))
        # vignette edges
        edge = pygame.Surface((W, 40), pygame.SRCALPHA)
        for i in range(40):
            a = int(140 * (1 - i / 40))
            pygame.draw.line(edge, (0, 0, 0, a), (0, 39 - i), (W, 39 - i))
        screen.blit(edge, (0, PLAY_TOP))
        edge2 = pygame.transform.flip(edge, False, True)
        screen.blit(edge2, (0, PLAY_BOT - 40))

    def _draw_world(self):
        screen.fill(COL_BG)
        self._draw_ground()
        # blood splats persist (just particles)
        # draw traps before zombies (zombies on top)
        for t in self.traps: t.draw(screen)
        # bunker
        self.bunker.draw(screen)
        # trap pickups (above ground, below zombies)
        for pu in self.pickups: pu.draw(screen)
        # zombies
        for z in self.zombies: z.draw(screen)
        # scrap
        for s in self.scraps: s.draw(screen)
        # bullets
        for b in self.bullets: b.draw(screen)
        # player
        self.player.draw(screen)
        # particles & floats on top
        for p in self.particles: p.draw(screen)
        for f in self.floats: f.draw(screen)

        # wave intro overlay
        if self.phase == "INTRO":
            overlay = pygame.Surface((W, PLAY_BOT - PLAY_TOP), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            screen.blit(overlay, (0, PLAY_TOP))
            idx = (self.wave - 1) % len(WAVE_TITLES)
            title = WAVE_TITLES[idx] if self.wave <= len(WAVE_TITLES) \
                    else f"WAVE {self.wave}: STILL HERE?"
            blit(screen, title, 48, (240, 200, 100), (CX, CY - 20))
            blit(screen, "deep breath. they're at the door.", 24, COL_DIM,
                 (CX, CY + 30))

    def _draw_hud(self):
        # ---- top HUD ----
        pygame.draw.rect(screen, COL_HUD_BG, (0, 0, W, HUD_TOP_H))
        pygame.draw.line(screen, COL_HUD_LINE, (0, HUD_TOP_H), (W, HUD_TOP_H), 2)

        # leave 30px from top untouched logically (still fill bg, but text >= y=36)
        # wave + phase
        blit(screen, f"WAVE {self.wave}", 24, (240, 200, 100), (24, 50),
             anchor="midleft")
        if self.phase == "ACTIVE":
            left = max(0, self.wave_total - self.wave_killed)
            blit(screen, f"left: {left}", 18, COL_DIM, (24 + 150, 50),
                 anchor="midleft")
        elif self.phase == "SCAVENGE":
            blit(screen, f"scavenge {int(math.ceil(self.phase_t))}s",
                 18, (140, 220, 150), (24 + 150, 50), anchor="midleft")
        elif self.phase == "INTRO":
            blit(screen, "incoming...", 18, (220, 100, 100),
                 (24 + 150, 50), anchor="midleft")

        # bunker HP bar (center)
        bx, by, bw, bh = CX - 280, 42, 560, 18
        pygame.draw.rect(screen, (40, 30, 24), (bx, by, bw, bh))
        f  = clamp(self.bunker.hp / BUNKER_HP, 0, 1)
        col = COL_HP_OK if f > 0.4 else (COL_HP_LOW if f < 0.2 else (220, 180, 60))
        pygame.draw.rect(screen, col, (bx, by, int(bw * f), bh))
        pygame.draw.rect(screen, COL_HUD_LINE, (bx, by, bw, bh), 2)
        blit(screen, "BUNKER", 14, COL_DIM, (bx - 8, by + bh // 2),
             anchor="midright")
        blit(screen, f"{int(max(0, self.bunker.hp))}/{BUNKER_HP}",
             14, (240, 230, 200), (bx + bw + 8, by + bh // 2),
             anchor="midleft")

        # scrap
        blit(screen, "SCRAP", 18, COL_DIM, (W - 200, 50), anchor="midright")
        blit(screen, f"{self.player.scrap}", 36, COL_SCRAP,
             (W - 30, 50), anchor="midright")

        # ---- bottom HUD: trap selector (only unlocked traps) ----
        pygame.draw.rect(screen, COL_HUD_BG, (0, H - HUD_BOT_H, W, HUD_BOT_H))
        pygame.draw.line(screen, COL_HUD_LINE,
                         (0, H - HUD_BOT_H), (W, H - HUD_BOT_H), 2)
        n_slots = MAX_TRAP_SLOTS
        slot_w  = 360
        gap     = 24
        total   = n_slots * slot_w + (n_slots - 1) * gap
        x0      = (W - total) // 2
        sel_idx = self.player.sel % max(1, len(self.unlocked))
        for i in range(n_slots):
            x = x0 + i * (slot_w + gap)
            y = H - HUD_BOT_H + 14
            box = pygame.Rect(x, y, slot_w, HUD_BOT_H - 28)
            if i >= len(self.unlocked):
                # empty slot — show locked
                pygame.draw.rect(screen, (24, 20, 16), box)
                pygame.draw.rect(screen, (50, 44, 36), box, 2)
                blit(screen, "LOCKED", 18, (90, 80, 60),
                     (box.centerx, box.centery - 6))
                blit(screen, "boss drop", 14, (70, 60, 45),
                     (box.centerx, box.centery + 16))
                continue
            t = TRAP_BY_KEY[self.unlocked[i]]
            sel = (i == sel_idx)
            bg = (50, 40, 32) if sel else (30, 24, 20)
            pygame.draw.rect(screen, bg, box)
            border_col = t["color"] if sel else (60, 54, 44)
            pygame.draw.rect(screen, border_col, box, 3 if sel else 2)
            blit(screen, t["name"], 24,
                 (240, 230, 200) if sel else COL_DIM,
                 (box.centerx - 70, box.y + 26))
            cost_col = COL_SCRAP if self.player.scrap >= t["cost"] else COL_RED
            blit(screen, f"{t['cost']}", 36, cost_col,
                 (box.right - 30, box.centery), anchor="midright")
            blit(screen, "scrap", 14, COL_DIM,
                 (box.right - 30, box.bottom - 20), anchor="midright")
            if sel:
                pygame.draw.polygon(screen, t["color"],
                                    [(box.centerx - 10, box.y - 8),
                                     (box.centerx + 10, box.y - 8),
                                     (box.centerx, box.y - 0)])
            blit(screen, t["blurb"], 14, COL_DIM,
                 (box.x + 14, box.bottom - 18), anchor="midleft")

        # kills counter (bottom right area, above HUD strip)
        blit(screen, f"kills: {self.kills}", 18, COL_DIM,
             (W - 30, H - HUD_BOT_H - 18), anchor="midright")
        # controls hint (bottom left)
        blit(screen, "ATTACK swing  |  tap JUMP cycle  |  hold JUMP place",
             14, COL_DIM, (30, H - HUD_BOT_H - 18), anchor="midleft")

    # ------------------ game over ------------------
    def _game_over(self, dt):
        self._game_over_t += dt
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        # any ATTACK after 1s -> back to attract
        if self._game_over_t > 1.0:
            for pid in range(4):
                if self.inp.just(pid, "ATTACK"):
                    self.state = "ATTRACT"
                    self._title_t = 0.0
                    self._demo_zoms = [self._spawn_demo_zom() for _ in range(8)]
                    return

        # render last frame faded
        screen.fill(COL_BG)
        self._draw_ground()
        # show wreckage: bunker as rubble
        r = BUNKER_RECT
        pygame.draw.rect(screen, (50, 40, 32), r)
        pygame.draw.rect(screen, (30, 22, 18), r, 4)
        for i in range(40):
            x = random.randint(r.left, r.right)
            y = random.randint(r.top, r.bottom)
            pygame.draw.circle(screen, (35, 28, 22), (x, y), 4)
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        screen.blit(ov, (0, 0))
        blit(screen, "THE  BUNKER  HAS  FALLEN", 72, (220, 70, 60), (CX, 280))
        blit(screen, self._epitaph, 24, (220, 200, 170), (CX, 360))
        # stats
        y = 480
        for label, val in [
            ("Waves Survived", self.wave - 1
                              if self.phase == "INTRO" else self.wave),
            ("Zombies Killed", self.kills),
            ("Final Scrap",    self.player.scrap),
        ]:
            blit(screen, label, 24, COL_DIM, (CX - 30, y), anchor="midright")
            blit(screen, str(val), 36, (240, 230, 200),
                 (CX + 30, y), anchor="midleft")
            y += 60
        if int(self._game_over_t * 2) % 2 == 0:
            blit(screen, "press ATTACK to return to attract", 18, COL_DIM,
                 (CX, H - 100))
        blit(screen, "(or hold ATTACK + JUMP to quit)", 14, COL_DIM,
             (CX, H - 70))


Game().run()
