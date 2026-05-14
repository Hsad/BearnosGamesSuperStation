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

CYAN    = (0, 255, 230)
MAGENTA = (255, 60, 200)
YELLOW  = (255, 230, 60)
LIME    = (140, 255, 80)
RED     = (255, 70, 80)
DARK    = (8, 4, 22)
GRID    = (28, 18, 60)
WHITE   = (240, 240, 255)


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


# --------- Level entities ---------
# Each level dict has:
#   start: (x,y)
#   exit:  pygame.Rect
#   walls: list of Rect
#   hazards: list of Rect
#   bounces: list of Rect (top-facing)
#   gravity_zones: list of (Rect, direction_y)  direction_y = -1 means flips up
#   conveyors: list of (Rect, speed)
#   moving: list of dicts {rect, axis, range, speed, phase}
#   hint: text shown briefly

def L1():
    return {
        "name": "ONBOARD",
        "hint": "MOVE: JOY  /  JUMP: JUMP  /  BOOST: ATTACK",
        "start": (200, 800),
        "exit": pygame.Rect(1750, 760, 100, 120),
        "walls": [
            pygame.Rect(0, 1000, W, 80),     # floor
            pygame.Rect(0, 0, 20, H),
            pygame.Rect(W-20, 0, 20, H),
            pygame.Rect(500, 880, 220, 30),
            pygame.Rect(820, 760, 220, 30),
            pygame.Rect(1140, 880, 220, 30),
            pygame.Rect(1500, 760, 280, 30),
        ],
        "hazards": [],
        "bounces": [],
        "gravity_zones": [],
        "conveyors": [],
        "moving": [],
    }

def L2():
    return {
        "name": "BOUNCE",
        "hint": "YELLOW PADS LAUNCH YOU",
        "start": (160, 920),
        "exit": pygame.Rect(1780, 220, 100, 120),
        "walls": [
            pygame.Rect(0, 1000, W, 80),
            pygame.Rect(0, 0, 20, H),
            pygame.Rect(W-20, 0, 20, H),
            pygame.Rect(400, 850, 200, 30),
            pygame.Rect(900, 700, 180, 30),
            pygame.Rect(1300, 540, 180, 30),
            pygame.Rect(1700, 340, 200, 30),
        ],
        "hazards": [
            pygame.Rect(620, 980, 240, 20),
            pygame.Rect(1100, 980, 180, 20),
        ],
        "bounces": [
            pygame.Rect(260, 980, 100, 20),
            pygame.Rect(700, 830, 100, 20),
            pygame.Rect(1130, 680, 100, 20),
            pygame.Rect(1520, 520, 100, 20),
        ],
        "gravity_zones": [],
        "conveyors": [],
        "moving": [],
    }

def L3():
    return {
        "name": "INVERSION",
        "hint": "MAGENTA ZONES FLIP GRAVITY",
        "start": (160, 920),
        "exit": pygame.Rect(1780, 920, 100, 120),
        "walls": [
            pygame.Rect(0, 1000, W, 80),
            pygame.Rect(0, 60, W, 30),       # ceiling walkable
            pygame.Rect(0, 0, 20, H),
            pygame.Rect(W-20, 0, 20, H),
            pygame.Rect(420, 1000-30-200, 220, 30),
        ],
        "hazards": [
            pygame.Rect(720, 980, 320, 20),
            pygame.Rect(1240, 980, 280, 20),
            pygame.Rect(720, 90, 320, 20),
        ],
        "bounces": [],
        "gravity_zones": [
            (pygame.Rect(640, 200, 240, 800), -1),
            (pygame.Rect(1100, 200, 240, 800), -1),
        ],
        "conveyors": [],
        "moving": [],
    }

def L4():
    return {
        "name": "FLOWLINE",
        "hint": "CYAN STRIPS PULL YOU ALONG",
        "start": (160, 920),
        "exit": pygame.Rect(1780, 220, 100, 120),
        "walls": [
            pygame.Rect(0, 1000, W, 80),
            pygame.Rect(0, 0, 20, H),
            pygame.Rect(W-20, 0, 20, H),
            pygame.Rect(280, 850, 360, 30),
            pygame.Rect(820, 700, 360, 30),
            pygame.Rect(1360, 550, 360, 30),
            pygame.Rect(1500, 340, 380, 30),
        ],
        "hazards": [
            pygame.Rect(640, 980, 200, 20),
            pygame.Rect(1180, 980, 200, 20),
            pygame.Rect(1720, 980, 180, 20),
        ],
        "bounces": [
            pygame.Rect(1300, 530, 60, 20),
        ],
        "gravity_zones": [],
        "conveyors": [
            (pygame.Rect(280, 840, 360, 10), 350),
            (pygame.Rect(820, 690, 360, 10), -350),
            (pygame.Rect(1360, 540, 360, 10), 350),
        ],
        "moving": [],
    }

def L5():
    return {
        "name": "FLUX",
        "hint": "EVERYTHING AT ONCE",
        "start": (160, 920),
        "exit": pygame.Rect(1780, 140, 100, 120),
        "walls": [
            pygame.Rect(0, 1000, W, 80),
            pygame.Rect(0, 0, 20, H),
            pygame.Rect(W-20, 0, 20, H),
            pygame.Rect(280, 880, 220, 30),
            pygame.Rect(1500, 260, 380, 30),
        ],
        "hazards": [
            pygame.Rect(520, 980, 280, 20),
            pygame.Rect(880, 980, 280, 20),
            pygame.Rect(1240, 980, 280, 20),
        ],
        "bounces": [
            pygame.Rect(340, 860, 100, 20),
        ],
        "gravity_zones": [
            (pygame.Rect(900, 200, 220, 700), -1),
        ],
        "conveyors": [
            (pygame.Rect(1500, 250, 380, 10), -300),
        ],
        "moving": [
            {"rect": pygame.Rect(640, 700, 180, 24), "axis":"y", "lo":500, "hi":820, "speed":120, "phase":0},
            {"rect": pygame.Rect(1200, 600, 180, 24), "axis":"x", "lo":1140, "hi":1440, "speed":160, "phase":1.5},
            {"rect": pygame.Rect(1440, 400, 180, 24), "axis":"y", "lo":340, "hi":520, "speed":140, "phase":0.7},
        ],
    }

LEVELS = [L1, L2, L3, L4, L5]


class Particle:
    __slots__ = ("x","y","vx","vy","life","max_life","color","size")
    def __init__(self, x, y, vx, vy, life, color, size=3):
        self.x=x; self.y=y; self.vx=vx; self.vy=vy
        self.life=life; self.max_life=life; self.color=color; self.size=size

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 200 * dt
        self.vx *= 0.98
        self.life -= dt
        return self.life > 0

    def draw(self, surf):
        a = max(0.0, self.life / self.max_life)
        c = (int(self.color[0]*a), int(self.color[1]*a), int(self.color[2]*a))
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), max(1, int(self.size*a)))


class Player:
    R = 16
    def __init__(self, x, y):
        self.x = x; self.y = y
        self.vx = 0.0; self.vy = 0.0
        self.gdir = 1            # +1 down, -1 up
        self.coyote = 0.0
        self.jump_buf = 0.0
        self.boost_cd = 0.0
        self.boost_t = 0.0       # while >0, boost is active (extra force)
        self.on_ground = False
        self.facing = 1
        self.trail = []          # (x,y,age)

    def rect(self):
        return pygame.Rect(int(self.x - self.R), int(self.y - self.R), self.R*2, self.R*2)


class Game:
    def __init__(self):
        self.inp   = Input()
        self.state = "ATTRACT"
        self.level_idx = 0
        self.level = None
        self.player = None
        self.particles = []
        self.t = 0.0
        self.shake = 0.0
        self.shake_amt = 0
        self.flash = 0.0
        self.glitch = 0.0
        self.deaths = 0
        self.timer = 0.0
        self.best_times = [None]*len(LEVELS)
        self.win_t = 0.0
        self.transition = 0.0
        self.hint_t = 0.0
        self._quit_hold = 0.0
        self._level_done = False
        self.attract_t = 0.0

    # ---------- Level lifecycle ----------
    def load_level(self, idx):
        self.level_idx = idx
        self.level = LEVELS[idx]()
        sx, sy = self.level["start"]
        self.player = Player(sx, sy)
        self.particles = []
        self.timer = 0.0
        self.hint_t = 4.0
        self._level_done = False
        self.transition = 0.5

    def respawn(self):
        sx, sy = self.level["start"]
        self.player = Player(sx, sy)
        self.deaths += 1
        self.flash = 0.4
        self.shake = 0.4; self.shake_amt = 14
        for _ in range(40):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(120, 480)
            self.particles.append(Particle(self.player.x, self.player.y,
                                           math.cos(ang)*sp, math.sin(ang)*sp,
                                           random.uniform(0.4, 0.9), RED, 4))

    # ---------- Physics ----------
    def update_player(self, dt):
        p = self.player
        L = self.level
        # input
        lx = (-1 if self.inp.held(0, "LEFT") else 0) + (1 if self.inp.held(0, "RIGHT") else 0)
        jump_pressed = self.inp.just(0, "JUMP")
        boost_pressed = self.inp.just(0, "ATTACK")

        # buffers
        if jump_pressed: p.jump_buf = 0.15
        else: p.jump_buf = max(0.0, p.jump_buf - dt)

        # horizontal: floaty momentum
        accel = 1500 if p.on_ground else 900
        target = lx * 520
        dv = target - p.vx
        p.vx += max(-accel*dt, min(accel*dt, dv))
        if lx == 0:
            fric = 6.0 if p.on_ground else 0.6
            p.vx -= p.vx * min(1.0, fric * dt)
        if lx != 0: p.facing = lx

        # vertical: gravity (modulated by zones)
        in_zone = False
        for r, gd in L["gravity_zones"]:
            if r.collidepoint(p.x, p.y):
                in_zone = True
                if p.gdir != gd:
                    p.gdir = gd
                break
        if not in_zone and p.gdir == -1:
            p.gdir = 1

        g = 1900 * p.gdir
        p.vy += g * dt
        p.vy = max(-1600, min(1600, p.vy))

        # jump
        if p.jump_buf > 0 and (p.on_ground or p.coyote > 0):
            p.vy = -780 * p.gdir
            p.jump_buf = 0
            p.coyote = 0
            p.on_ground = False
            for _ in range(10):
                self.particles.append(Particle(p.x, p.y + p.R*p.gdir,
                                               random.uniform(-200,200),
                                               random.uniform(0,260)*p.gdir,
                                               0.4, CYAN, 3))

        # boost (dash) - instant velocity injection in input direction
        if boost_pressed and p.boost_cd <= 0:
            dx = lx
            dy = (-1 if self.inp.held(0,"UP") else 0) + (1 if self.inp.held(0,"DOWN") else 0)
            if dx == 0 and dy == 0: dx = p.facing
            mag = math.hypot(dx, dy) or 1
            p.vx = dx/mag * 900 + p.vx*0.2
            p.vy = dy/mag * 900 + p.vy*0.2
            p.boost_cd = 0.6
            p.boost_t = 0.18
            self.glitch = 0.18
            for _ in range(18):
                ang = random.uniform(0, math.tau)
                sp = random.uniform(160, 380)
                self.particles.append(Particle(p.x, p.y,
                                               math.cos(ang)*sp, math.sin(ang)*sp,
                                               0.45, MAGENTA, 4))
        p.boost_cd = max(0.0, p.boost_cd - dt)
        p.boost_t  = max(0.0, p.boost_t  - dt)

        # conveyor influence (if standing on one)
        # apply later in collision step

        # integrate X
        p.x += p.vx * dt
        self._collide_axis(p, "x")
        # integrate Y
        p.y += p.vy * dt
        prev_on = p.on_ground
        p.on_ground = False
        self._collide_axis(p, "y")
        if not p.on_ground and prev_on:
            p.coyote = 0.1
        else:
            p.coyote = max(0.0, p.coyote - dt)

        # conveyors: if standing on top of conveyor strip, drag horizontally
        for cr, sp in L["conveyors"]:
            foot = pygame.Rect(int(p.x - p.R + 2), int(p.y + p.R - 2), p.R*2-4, 6)
            if p.gdir == -1:
                foot = pygame.Rect(int(p.x - p.R + 2), int(p.y - p.R - 4), p.R*2-4, 6)
            if foot.colliderect(cr):
                p.vx += (sp - p.vx) * min(1.0, 4.0*dt)
                if random.random() < 0.4:
                    self.particles.append(Particle(p.x + random.uniform(-12,12),
                                                   cr.centery,
                                                   sp*0.5, 0, 0.3, CYAN, 2))

        # bounce pads
        for br in L["bounces"]:
            pr = p.rect()
            if pr.colliderect(br):
                p.vy = -1200
                p.y = br.top - p.R - 1
                p.on_ground = False
                self.shake = 0.25; self.shake_amt = 8
                for _ in range(20):
                    self.particles.append(Particle(p.x + random.uniform(-20,20),
                                                   br.top,
                                                   random.uniform(-260,260),
                                                   random.uniform(-700,-200),
                                                   0.5, YELLOW, 4))

        # moving platforms (treat like walls; player rides on top)
        # already integrated into walls list at draw/collide time? handle here:
        for m in L["moving"]:
            # platform velocity for ride-along
            if m["axis"] == "x":
                pv = m["_vx"]
                pvy = 0
            else:
                pv = 0
                pvy = m["_vy"]
            r = m["rect"]
            pr = p.rect()
            if pr.colliderect(r):
                # determine side of impact based on previous position; simple top-resolve when falling
                if p.vy > 0 and pr.bottom - r.top < 24:
                    p.y = r.top - p.R
                    p.vy = 0
                    p.on_ground = True
                    p.gdir = 1
                    p.x += pv * dt
                elif p.vy < 0 and r.bottom - pr.top < 24:
                    p.y = r.bottom + p.R
                    p.vy = 0
                else:
                    if pr.centerx < r.centerx:
                        p.x = r.left - p.R
                        p.vx = min(p.vx, 0)
                    else:
                        p.x = r.right + p.R
                        p.vx = max(p.vx, 0)

        # hazards & boundaries
        pr = p.rect()
        for hz in L["hazards"]:
            if pr.colliderect(hz):
                self.respawn()
                return
        if p.y > H + 200 or p.y < -200 or p.x < -200 or p.x > W + 200:
            self.respawn()
            return

        # exit
        if pr.colliderect(L["exit"]):
            self._level_done = True

        # trail
        p.trail.append((p.x, p.y, 0.0))
        if len(p.trail) > 18:
            p.trail.pop(0)
        for i in range(len(p.trail)):
            x, y, a = p.trail[i]
            p.trail[i] = (x, y, a + dt)

    def _collide_axis(self, p, axis):
        L = self.level
        pr = p.rect()
        for w in L["walls"]:
            if not pr.colliderect(w): continue
            if axis == "x":
                if p.vx > 0:
                    p.x = w.left - p.R
                elif p.vx < 0:
                    p.x = w.right + p.R
                p.vx = 0
                pr = p.rect()
            else:
                if p.vy > 0:
                    p.y = w.top - p.R
                    p.vy = 0
                    if p.gdir == 1:
                        p.on_ground = True
                elif p.vy < 0:
                    p.y = w.bottom + p.R
                    p.vy = 0
                    if p.gdir == -1:
                        p.on_ground = True
                pr = p.rect()

    # ---------- Loop ----------
    def run(self):
        while True:
            dt = min(clock.tick(60) / 1000.0, 0.05)
            self.t += dt
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
            elif self.state == "WIN":       self._win(dt)
            elif self.state == "GAME_OVER": self._game_over(dt)

            pygame.display.flip()

    # ---------- States ----------
    def _attract(self, dt):
        self.attract_t += dt
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        if self.inp.just(0, "ATTACK"):
            self.deaths = 0
            self.load_level(0)
            self.state = "PLAYING"
            return

        screen.fill(DARK)
        self._draw_grid(0)

        # title with glitch
        title = "MOMENTUM FLUX"
        for ox, oy, col in [(-4, 0, CYAN), (4, 0, MAGENTA), (0, 0, WHITE)]:
            blit(screen, title, 72, col, (CX + ox, 280 + oy))

        sub = "FLOATY MOMENTUM PLATFORMER"
        blit(screen, sub, 24, YELLOW, (CX, 360))

        instr = [
            "JOYSTICK . . . . MOVE",
            "JUMP BUTTON  . . JUMP",
            "ATTACK BUTTON  . BOOST DASH",
            "",
            "AVOID RED HAZARDS",
            "BOUNCE ON YELLOW PADS",
            "FLIP GRAVITY IN MAGENTA ZONES",
            "RIDE CYAN FLOW STRIPS",
        ]
        for i, line in enumerate(instr):
            blit(screen, line, 24, WHITE, (CX, 480 + i*40))

        prompt = "PRESS ATTACK TO START"
        if int(self.attract_t * 2) % 2 == 0:
            blit(screen, prompt, 36, LIME, (CX, 880))

        blit(screen, "P1 ONLY", 18, (160,160,200), (CX, 940))
        blit(screen, "HOLD ATTACK + JUMP TO QUIT", 14, (130,130,160), (CX, 1040))

    def _playing(self, dt):
        # quit hold — any player holds both buttons for 3 seconds
        if any(self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP") for pid in range(4)):
            self._quit_hold += dt
        else:
            self._quit_hold = 0.0
        if self._quit_hold >= 3.0:
            pygame.quit(); sys.exit()

        # update moving platforms
        for m in self.level["moving"]:
            m["phase"] += dt
            t = m["phase"] * (m["speed"] / max(1, (m["hi"]-m["lo"])))
            # simple oscillation
            base_lo = m["lo"]; base_hi = m["hi"]
            mid = (base_lo + base_hi) / 2
            amp = (base_hi - base_lo) / 2
            new = mid + math.sin(m["phase"] * (m["speed"] / max(1, amp))) * amp
            if m["axis"] == "x":
                old = m["rect"].x
                m["rect"].x = int(new)
                m["_vx"] = (m["rect"].x - old) / dt if dt > 0 else 0
                m["_vy"] = 0
            else:
                old = m["rect"].y
                m["rect"].y = int(new)
                m["_vy"] = (m["rect"].y - old) / dt if dt > 0 else 0
                m["_vx"] = 0

        self.timer += dt
        self.hint_t = max(0.0, self.hint_t - dt)
        self.transition = max(0.0, self.transition - dt)
        self.flash = max(0.0, self.flash - dt)
        self.glitch = max(0.0, self.glitch - dt)
        self.shake = max(0.0, self.shake - dt)

        self.update_player(dt)
        self.particles = [p for p in self.particles if p.update(dt)]

        if self._level_done:
            bt = self.best_times[self.level_idx]
            if bt is None or self.timer < bt:
                self.best_times[self.level_idx] = self.timer
            if self.level_idx + 1 < len(LEVELS):
                self.load_level(self.level_idx + 1)
            else:
                self.state = "WIN"
                self.win_t = 0.0
            return

        self._draw_world()

        # quit-hold bar
        if self._quit_hold > 0:
            t = min(self._quit_hold/3.0, 1.0)
            pygame.draw.rect(screen, (60, 20, 20), (0, H-10, W, 10))
            pygame.draw.rect(screen, (220, 50, 50), (0, H-10, int(W*t), 10))

    def _win(self, dt):
        self.win_t += dt
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        if self.win_t > 1.5 and self.inp.just(0, "ATTACK"):
            self.state = "ATTRACT"
            return

        screen.fill(DARK)
        self._draw_grid(0)
        for ox, oy, col in [(-4,0,CYAN),(4,0,MAGENTA),(0,0,WHITE)]:
            blit(screen, "FLUX STABILIZED", 72, col, (CX+ox, 240+oy))
        blit(screen, "ALL LEVELS CLEARED", 36, YELLOW, (CX, 340))
        blit(screen, f"DEATHS: {self.deaths}", 36, WHITE, (CX, 420))
        total = sum(t for t in self.best_times if t is not None)
        blit(screen, f"BEST TIMES", 24, LIME, (CX, 500))
        for i, t in enumerate(self.best_times):
            name = LEVELS[i]().get("name", f"LV{i+1}")
            txt = f"{name:<10}  {t:5.2f}s" if t is not None else f"{name:<10}   --"
            blit(screen, txt, 24, WHITE, (CX, 540 + i*30))
        blit(screen, f"TOTAL  {total:5.2f}s", 36, MAGENTA, (CX, 760))
        if self.win_t > 1.5 and int(self.win_t*2) % 2 == 0:
            blit(screen, "PRESS ATTACK", 24, LIME, (CX, 900))

    def _game_over(self, dt):
        # not used; respawn keeps you in PLAYING
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()

    # ---------- Drawing ----------
    def _draw_grid(self, parallax):
        for y in range(0, H, 60):
            pygame.draw.line(screen, GRID, (0, y), (W, y), 1)
        for x in range(0, W, 60):
            pygame.draw.line(screen, GRID, (x, 0), (x, H), 1)

    def _draw_world(self):
        L = self.level
        sx = sy = 0
        if self.shake > 0:
            sx = random.randint(-self.shake_amt, self.shake_amt)
            sy = random.randint(-self.shake_amt, self.shake_amt)

        screen.fill(DARK)
        self._draw_grid(0)

        # gravity zones (background tinted)
        for r, gd in L["gravity_zones"]:
            pulse = 0.5 + 0.5*math.sin(self.t*4)
            tint = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            tint.fill((255, 60, 200, int(40 + 30*pulse)))
            screen.blit(tint, (r.x + sx, r.y + sy))
            # arrows
            for ax in range(r.x+30, r.right-20, 60):
                ay = r.y + 30 + (int(self.t*120) + ax) % (r.h - 60)
                d = -1 if gd == -1 else 1
                pygame.draw.polygon(screen, MAGENTA,
                    [(ax+sx, ay+sy + 14*d),
                     (ax-8+sx, ay+sy - 6*d),
                     (ax+8+sx, ay+sy - 6*d)])
            pygame.draw.rect(screen, MAGENTA, r.move(sx, sy), 2)

        # walls
        for w in L["walls"]:
            pygame.draw.rect(screen, (50, 30, 90), w.move(sx, sy))
            pygame.draw.rect(screen, CYAN, w.move(sx, sy), 2)

        # moving platforms
        for m in L["moving"]:
            r = m["rect"].move(sx, sy)
            pygame.draw.rect(screen, (60, 20, 80), r)
            pygame.draw.rect(screen, MAGENTA, r, 2)
            pygame.draw.line(screen, WHITE, (r.x+8, r.centery), (r.right-8, r.centery), 1)

        # conveyors
        for cr, sp in L["conveyors"]:
            r = cr.move(sx, sy)
            pygame.draw.rect(screen, (10, 60, 70), r)
            pygame.draw.rect(screen, CYAN, r, 1)
            offs = (self.t * sp) % 30
            for x in range(int(r.x - 30), r.right, 30):
                xx = x + (offs if sp > 0 else -offs)
                pygame.draw.line(screen, CYAN, (xx, r.centery), (xx+12*(1 if sp>0 else -1), r.centery), 2)

        # bounce pads
        for br in L["bounces"]:
            r = br.move(sx, sy)
            pulse = 0.5 + 0.5*math.sin(self.t*8)
            pygame.draw.rect(screen, (80, 70, 0), r)
            pygame.draw.rect(screen, YELLOW, r, 2)
            pygame.draw.line(screen, (255,255,180),
                             (r.x+4, r.centery + int(4*pulse)),
                             (r.right-4, r.centery + int(4*pulse)), 2)

        # hazards (animated stripes)
        for hz in L["hazards"]:
            r = hz.move(sx, sy)
            pygame.draw.rect(screen, (90, 10, 20), r)
            pygame.draw.rect(screen, RED, r, 2)
            offs = int(self.t * 60) % 18
            for x in range(r.x - 18, r.right, 18):
                pygame.draw.polygon(screen, (255,140,140),
                    [(x+offs, r.top),
                     (x+offs+9, r.top),
                     (x+offs+5, r.top+6)])

        # exit
        ex = L["exit"].move(sx, sy)
        pulse = 0.5 + 0.5*math.sin(self.t*5)
        for i in range(6):
            alpha = int(150*pulse * (1 - i/6))
            s = pygame.Surface((ex.w + i*20, ex.h + i*20), pygame.SRCALPHA)
            pygame.draw.rect(s, (140, 255, 80, alpha), s.get_rect(), 2)
            screen.blit(s, (ex.x - i*10, ex.y - i*10))
        pygame.draw.rect(screen, LIME, ex, 3)
        blit(screen, "EXIT", 24, LIME, ex.center)

        # particles
        for p in self.particles:
            p.draw(screen)

        # player + trail
        p = self.player
        for i, (tx, ty, age) in enumerate(p.trail):
            a = max(0.0, 1.0 - age*4)
            r = max(2, int(p.R * (i / len(p.trail)) * 0.8))
            col = (int(CYAN[0]*a), int(CYAN[1]*a), int(CYAN[2]*a))
            pygame.draw.circle(screen, col, (int(tx)+sx, int(ty)+sy), r)

        # glow
        glow_col = MAGENTA if p.boost_t > 0 else CYAN
        for i in range(4, 0, -1):
            s = pygame.Surface((p.R*2 + i*8, p.R*2 + i*8), pygame.SRCALPHA)
            pygame.draw.circle(s, (*glow_col, 30), s.get_rect().center, p.R + i*4)
            screen.blit(s, (int(p.x) - p.R - i*4 + sx, int(p.y) - p.R - i*4 + sy))
        pygame.draw.circle(screen, WHITE, (int(p.x)+sx, int(p.y)+sy), p.R)
        pygame.draw.circle(screen, glow_col, (int(p.x)+sx, int(p.y)+sy), p.R, 2)
        # face indicator
        eye_x = int(p.x + p.facing*5) + sx
        eye_y = int(p.y - 3*p.gdir) + sy
        pygame.draw.circle(screen, DARK, (eye_x, eye_y), 3)

        # flash
        if self.flash > 0:
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((255, 60, 80, int(120 * (self.flash/0.4))))
            screen.blit(s, (0,0))

        # glitch overlay
        if self.glitch > 0:
            for _ in range(8):
                y = random.randint(0, H-1)
                h = random.randint(2, 14)
                offx = random.randint(-30, 30)
                if y+h < H:
                    strip = screen.subsurface(pygame.Rect(0, y, W, h)).copy()
                    screen.blit(strip, (offx, y))

        # transition wipe at level start
        if self.transition > 0:
            t = self.transition / 0.5
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((0, 0, 0, int(220*t)))
            screen.blit(s, (0,0))

        # HUD (keep >= 30px from top)
        blit(screen, f"LV {self.level_idx+1}/{len(LEVELS)}  {self.level['name']}",
             24, CYAN, (40, 40), anchor="topleft")
        blit(screen, f"TIME {self.timer:5.2f}", 24, WHITE, (W//2, 40))
        blit(screen, f"DEATHS {self.deaths}", 24, MAGENTA, (W-40, 40), anchor="topright")

        # boost cooldown bar
        bar_w = 220
        bx = 40; by = 80
        pygame.draw.rect(screen, (40,30,60), (bx, by, bar_w, 8))
        if p.boost_cd > 0:
            frac = 1.0 - p.boost_cd/0.6
        else:
            frac = 1.0
        pygame.draw.rect(screen, MAGENTA, (bx, by, int(bar_w*frac), 8))
        blit(screen, "BOOST", 14, (180,180,200), (bx, by+12), anchor="topleft")

        # hint
        if self.hint_t > 0:
            a = min(1.0, self.hint_t)
            col = (int(YELLOW[0]*a), int(YELLOW[1]*a), int(YELLOW[2]*a))
            blit(screen, self.level["hint"], 36, col, (CX, H-80))


Game().run()
