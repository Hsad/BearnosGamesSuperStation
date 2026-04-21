#!/usr/bin/env python3
"""
CHOPPER CHASE — 4-player competitive helicopter cave game.
JUMP=thrust  LEFT/RIGHT=reposition  ATTACK=fire missile
Left edge = death. Crash = death. 3 lives each. Last pilot wins.
"""
import pygame, sys, json, math, random, os, time

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
W, H   = screen.get_size()
clock  = pygame.time.Clock()
pygame.display.set_caption("CHOPPER CHASE")

_FONT_PATH = os.path.expanduser("~/.local/share/fonts/DepartureMono-Regular.otf")
def _f(sz):
    return (pygame.font.Font(_FONT_PATH, sz) if os.path.exists(_FONT_PATH)
            else pygame.font.SysFont("monospace", sz, bold=True))
FONTS = {s: _f(s) for s in (72, 48, 36, 24, 18, 14, 11)}

def blit(surf, text, size, color, pos, anchor="center"):
    s = FONTS[size].render(str(text), False, color)
    surf.blit(s, s.get_rect(**{anchor: pos}))

# ── Palette ───────────────────────────────────────────────────────────────────
WHITE  = (255, 255, 255)
BG     = ( 10,  14,  28)
ROCK   = ( 38,  42,  58)
ROCK_E = ( 55,  60,  82)
ROCK_D = ( 58,  48,  70)
GRAY   = ( 90,  90, 100)
DGRAY  = ( 35,  35,  45)
DANGER = (140,  20,  20)

PCOLORS = [
    ( 30, 130, 255),  # P1 – blue
    (255, 210,  40),  # P2 – yellow
    (150,  60, 210),  # P3 – purple
    (220,  40,  40),  # P4 – red
]

# ── Tuning ────────────────────────────────────────────────────────────────────
GRAVITY       = 820
THRUST        = 2300
VY_MAX        =  500
VY_MIN        = -430
PMOVE_SPD     =  180

SCROLL_START  =  150.0
SCROLL_DOUBLE =  120.0

CHOP_R        =   13
CHOP_LIVES    =    3
INVULN_DUR    =    3.0

MISSILE_SLOTS =    4
MISSILE_CD    =    3.0
MISSILE_SPD   =  560
MISSILE_TTL   =    3.0

DEATH_X       =   32

# ── Tile grid ─────────────────────────────────────────────────────────────────
TILE        = 24          # px per tile (H=1080 → 45 rows, W=1920 → 80 cols)
TILES_H     = H // TILE   # 45
DRIFT_EVERY = 3           # tile columns between cave drift steps
GAP_T_START = 15          # starting gap in tiles (360 px)
GAP_T_MIN   =  5          # minimum gap in tiles  (120 px)
DRIFT_MAX   =  2          # max drift in tiles per step

# Obstacle spawn distances
OBS_MIN_GAP =  680
OBS_MAX_GAP = 1100

OBS_DIST    = [("block",50),("stala",30),("stalac",8),("pipe",12)]
OBS_TOTAL   = sum(w for _,w in OBS_DIST)

STALA_MAX_F  = 0.52
STALAC_MAX_F = 0.65
STALAC_GUARD = 0.33
PIPE_TILES_W =  3
PIPE_W       = PIPE_TILES_W * TILE
PIPE_GAP_0   =  230
PIPE_GAP_MIN =  130
PIPE_GAP_T   =  480.0
PIPE_MIN_Y_F = 0.27

# Spawn positions spread across screen
SPAWN_XS = [W//5, W*2//5, W*3//5, W*4//5]   # [384, 768, 1152, 1536]

GAP_SHRINK_T = 600.0


# ── Input — event-based so large SDLK codes (arrows, modifiers) work ─────────
class Input:
    INACTIVITY_TIMEOUT = 60.0

    def __init__(self):
        self.maps  = []
        self._prev = set()
        self._curr = set()
        self._last_activity = time.monotonic()
        ctrl = os.path.join(os.path.dirname(__file__), "controllers.json")
        try:
            data = json.load(open(ctrl))
            for p in data["players"]:
                self.maps.append({a: v["key"] for a,v in p["inputs"].items()
                                  if v["type"]=="key"})
        except Exception:
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

    def any_just(self, pid):
        return any(self.just(pid,a) for a in ("UP","DOWN","LEFT","RIGHT","JUMP","ATTACK"))


# ── Cave — true tile grid ─────────────────────────────────────────────────────
class Cave:
    """
    World is a grid of TILE×TILE cells.
    tcols[world_tile_x] = (ceil_rows, floor_rows): solid tile counts top/bottom.
    destroyed: set of (world_tile_x, row) pairs blasted out by missiles.
    """
    def __init__(self):
        self.scroll    = 0.0
        self.tcols     = {}
        self.destroyed = set()
        self._cy_tile  = TILES_H // 2
        self._gap_half = GAP_T_START // 2
        cols_needed    = W // TILE + 8
        for tx in range(cols_needed):
            self._push(tx)

    def _push(self, tx):
        if tx % DRIFT_EVERY == 0 and self.tcols:
            self._cy_tile += random.randint(-DRIFT_MAX, DRIFT_MAX)
        gh = self._gap_half
        self._cy_tile = max(gh + 2, min(TILES_H - gh - 2, self._cy_tile))
        self.tcols[tx] = (self._cy_tile - gh, TILES_H - (self._cy_tile + gh))

    def update(self, dx, gap_tiles):
        self.scroll += dx
        self._gap_half = max(1, gap_tiles // 2)
        left = int(self.scroll // TILE) - 2
        self.tcols     = {tx: v for tx, v in self.tcols.items() if tx >= left}
        self.destroyed = {k for k in self.destroyed if k[0] >= left}
        right = max(self.tcols.keys()) if self.tcols else left
        need  = int((self.scroll + W) // TILE) + 6
        while right < need:
            right += 1
            self._push(right)

    def gap_at(self, sx):
        """Pixel (top_y, bot_y) of the open gap at screen-x sx. Tile-aligned."""
        tx = int((sx + self.scroll) // TILE)
        if tx in self.tcols:
            cr, fr = self.tcols[tx]
            return cr * TILE, H - fr * TILE
        return 0, H

    def collides(self, sx, sy, r=CHOP_R):
        """Tile-aware collision — destroyed tiles are passable."""
        wx  = sx + self.scroll
        tx  = int(wx // TILE)
        for dtx in (-1, 0, 1):
            wtx = tx + dtx
            if wtx not in self.tcols: continue
            cr, fr = self.tcols[wtx]
            scx = wtx * TILE - self.scroll
            if sx + r <= scx or sx - r >= scx + TILE: continue
            for row in range(cr):
                if (wtx, row) in self.destroyed: continue
                ry = row * TILE
                if sy - r < ry + TILE and sy + r > ry:
                    return True
            for row in range(TILES_H - fr, TILES_H):
                if (wtx, row) in self.destroyed: continue
                ry = row * TILE
                if sy - r < ry + TILE and sy + r > ry:
                    return True
        return False

    def missile_destroy(self, sx, sy):
        """If missile is inside a wall tile, destroy it and return Debris."""
        wx  = sx + self.scroll
        tx  = int(wx // TILE)
        row = int(sy // TILE)
        if tx not in self.tcols: return []
        cr, fr = self.tcols[tx]
        key = (tx, row)
        if key in self.destroyed: return []
        if row < cr or row >= TILES_H - fr:
            self.destroyed.add(key)
            scx = tx * TILE - self.scroll + TILE // 2
            scy = row * TILE + TILE // 2
            return quarter_debris(scx, scy, TILE, TILE)
        return []

    def draw(self, surf):
        left_tx  = int(self.scroll // TILE) - 1
        right_tx = left_tx + W // TILE + 3
        for tx in range(left_tx, right_tx + 1):
            if tx not in self.tcols: continue
            cr, fr = self.tcols[tx]
            sx = int(tx * TILE - self.scroll)
            for row in range(cr):
                if (tx, row) in self.destroyed: continue
                pygame.draw.rect(surf, ROCK,   (sx, row*TILE, TILE, TILE))
                pygame.draw.rect(surf, ROCK_E, (sx, row*TILE, TILE, TILE), 1)
            for row in range(TILES_H - fr, TILES_H):
                if (tx, row) in self.destroyed: continue
                pygame.draw.rect(surf, ROCK,   (sx, row*TILE, TILE, TILE))
                pygame.draw.rect(surf, ROCK_E, (sx, row*TILE, TILE, TILE), 1)


# ── Falling debris ────────────────────────────────────────────────────────────
class Debris:
    def __init__(self, sx, sy, w, h):
        self.sx, self.sy = float(sx), float(sy)
        self.vx = random.uniform(-60, 60)
        self.vy = random.uniform(-80, 20)
        self.w, self.h = int(w), int(h)
        self.ttl  = 5.0
        self.alive= True

    def update(self, dt, sdx):
        self.sx += self.vx*dt - sdx
        self.vy  = min(VY_MAX, self.vy + GRAVITY*dt)
        self.sy += self.vy*dt
        self.ttl -= dt
        if self.ttl<=0 or self.sy>H+100 or self.sx<-300:
            self.alive = False

    def hit(self, px, py, r=CHOP_R):
        return abs(px-self.sx)<self.w/2+r and abs(py-self.sy)<self.h/2+r

    def draw(self, surf):
        x,y = int(self.sx-self.w//2), int(self.sy-self.h//2)
        pygame.draw.rect(surf, ROCK_D, (x, y, self.w, self.h))
        pygame.draw.rect(surf, ROCK_E, (x, y, self.w, self.h), 1)


def quarter_debris(cx, cy, w, h):
    hw, hh = max(TILE//2, w//2), max(TILE//2, h//2)
    return [Debris(cx+ox, cy+oy, hw, hh)
            for ox,oy in ((-hw//2,-hh//2),(hw//2,-hh//2),
                          (-hw//2, hh//2),(hw//2, hh//2))]


# ── Heli wreckage bits ────────────────────────────────────────────────────────
class HeliBit:
    def __init__(self, sx, sy, kind, color):
        self.sx, self.sy = float(sx), float(sy)
        self.vx  = random.uniform(-150, 150)
        self.vy  = random.uniform(-200, 80)
        self.rot = random.uniform(0, 360)
        self.rspd= random.uniform(-500, 500)
        self.kind  = kind
        self.color = color
        self.ttl   = random.uniform(2.0, 3.5)
        self.alive = True

    def update(self, dt, sdx):
        self.sx += self.vx*dt - sdx
        self.vy  = min(500, self.vy + GRAVITY*0.65*dt)
        self.sy += self.vy*dt
        self.rot = (self.rot + self.rspd*dt) % 360
        self.ttl -= dt
        if self.ttl<=0 or self.sy>H+100: self.alive=False

    def hit(self, px, py, r=CHOP_R):
        return abs(px-self.sx)<18+r and abs(py-self.sy)<14+r

    def draw(self, surf):
        S = 4
        x,y = int(self.sx), int(self.sy)
        a   = math.radians(self.rot)
        c,s = math.cos(a), math.sin(a)
        if self.kind=='body':
            pts=[];
            for deg in range(0,360,45):
                ra=math.radians(deg); ex,ey=math.cos(ra)*3*S, math.sin(ra)*2*S
                pts.append((x+int(ex*c-ey*s), y+int(ex*s+ey*c)))
            if len(pts)>=3: pygame.draw.polygon(surf, self.color, pts)
        elif self.kind=='tail':
            ex,ey=3*S*c,3*S*s
            pygame.draw.line(surf,self.color,(x-int(ex),y-int(ey)),(x+int(ex),y+int(ey)),3)
        else:
            ex,ey=4*S*c,4*S*s
            pygame.draw.line(surf,WHITE,(x-int(ex),y-int(ey)),(x+int(ex),y+int(ey)),2)


# ── Obstacles ─────────────────────────────────────────────────────────────────
class Obs:
    def __init__(self, wx):
        self.wx    = float(wx)
        self.alive = True
    def scrx(self, scroll): return self.wx - scroll
    def cull(self, scroll):
        if self.scrx(scroll) < -400: self.alive = False
    def hit(self, px,py,scroll,r=CHOP_R): return False
    def missile_hit(self, msy, scroll):   return []
    def draw(self, surf, scroll):         pass


class FloatBlock(Obs):
    HP = 1
    def __init__(self, wx, cy):
        super().__init__(wx)
        self.cy = cy
        self.hp = self.HP

    def hit(self, px,py,scroll,r=CHOP_R):
        rx = self.scrx(scroll)
        return abs(px-rx)<TILE/2+r and abs(py-self.cy)<TILE/2+r

    def missile_hit(self, msy, scroll):
        self.hp -= 1
        if self.hp<=0:
            self.alive=False
            return quarter_debris(self.scrx(scroll), self.cy, TILE, TILE)
        return []

    def draw(self, surf, scroll):
        rx  = int(self.scrx(scroll))
        x0  = rx - TILE//2
        y0  = int(self.cy) - TILE//2
        col = ROCK_D if self.hp<self.HP else ROCK
        pygame.draw.rect(surf, col,   (x0, y0, TILE, TILE))
        pygame.draw.rect(surf, ROCK_E,(x0, y0, TILE, TILE), 1)
        if self.hp<self.HP:
            pygame.draw.line(surf, WHITE, (rx-3,int(self.cy)-2),(rx+2,int(self.cy)+3), 1)


def pick_type():
    r,cumul=random.random()*OBS_TOTAL,0
    for kind,w in OBS_DIST:
        cumul+=w
        if r<cumul: return kind
    return "block"

def make_obs(wx, cave, elapsed):
    """Returns a list of FloatBlock tiles for any obstacle type."""
    ty,by=cave.gap_at(min(W+60,W-1))
    gap=by-ty; kind=pick_type()

    if kind=="block":
        n        = random.randint(4, 9)
        col_span = random.randint(2, 5)
        ty_t     = int(ty // TILE)
        by_t     = int(by // TILE)
        avail    = by_t - ty_t
        if avail <= 0: return []
        placed   = set()
        attempts = 0
        while len(placed) < n and attempts < n * 12:
            c = random.randint(0, col_span - 1)
            r = random.randint(ty_t, by_t - 1)
            placed.add((c, r))
            attempts += 1
        return [FloatBlock(wx + c*TILE + TILE//2, r*TILE + TILE//2)
                for c,r in placed]

    elif kind=="stala":
        max_n = max(1, int(gap * STALA_MAX_F // TILE))
        n     = random.randint(max(1, max_n//2), max_n)
        return [FloatBlock(wx, by - (i + 0.5)*TILE) for i in range(n)]

    elif kind=="stalac":
        max_n   = max(1, int(gap * STALAC_MAX_F // TILE))
        guard_n = max(0, int(gap * STALAC_GUARD // TILE))
        avail   = max(1, max_n - guard_n)
        n       = random.randint(max(1, avail//2), avail)
        return [FloatBlock(wx, ty + (i + 0.5)*TILE) for i in range(n)]

    else:  # pipe — two multi-tile columns with a gap
        t_frac = min(1.0, elapsed / PIPE_GAP_T)
        gap_px = max(PIPE_GAP_MIN, PIPE_GAP_0 + (PIPE_GAP_MIN - PIPE_GAP_0)*t_frac)
        gap_px = round(gap_px / TILE) * TILE
        low    = by - gap*(1.0 - PIPE_MIN_Y_F); high = ty + gap*0.72
        cy     = min(random.uniform(low, max(low+1, high)),
                     random.uniform(low, max(low+1, high)))
        gt     = round(max(ty + TILE, cy - gap_px/2) / TILE) * TILE
        gb     = round(min(by - TILE, cy + gap_px/2) / TILE) * TILE
        n_top  = max(0, int((gt - ty) // TILE))
        n_bot  = max(0, int((by - gb) // TILE))
        blocks = []
        for tx_off in range(PIPE_TILES_W):
            bwx = wx - PIPE_W//2 + tx_off*TILE + TILE//2
            for i in range(n_top):
                blocks.append(FloatBlock(bwx, ty + (i + 0.5)*TILE))
            for i in range(n_bot):
                blocks.append(FloatBlock(bwx, gb + (i + 0.5)*TILE))
        return blocks


# ── Missile ───────────────────────────────────────────────────────────────────
class Missile:
    def __init__(self,sx,sy,owner,color):
        self.sx,self.sy=float(sx),float(sy)
        self.owner,self.color=owner,color
        self.ttl,self.alive=MISSILE_TTL,True

    def update(self,dt,sdx):
        self.sx+=MISSILE_SPD*dt-sdx; self.ttl-=dt
        if self.ttl<=0 or self.sx>W+80: self.alive=False

    def draw(self,surf):
        x,y=int(self.sx),int(self.sy)
        pygame.draw.line(surf,self.color,(x,y),(x-22,y),3)
        pygame.draw.circle(surf,WHITE,(x,y),3)


# ── Sparks ────────────────────────────────────────────────────────────────────
class Spark:
    __slots__=("x","y","vx","vy","life","color")
    def __init__(self,x,y,color):
        a=random.uniform(0,math.tau); s=random.uniform(70,310)
        self.x,self.y=float(x),float(y)
        self.vx,self.vy=math.cos(a)*s,math.sin(a)*s
        self.life=random.uniform(0.4,1.2); self.color=color
    def update(self,dt,sdx):
        self.x+=self.vx*dt-sdx; self.y+=self.vy*dt; self.life-=dt
    def draw(self,surf):
        pygame.draw.circle(surf,self.color,(int(self.x),int(self.y)),max(1,int(self.life*5)))


# ── Helicopter sprite ─────────────────────────────────────────────────────────
S = 4   # sprite pixel-block size (px)

_ROTOR_HALF = [7, 4, 1]   # main rotor half-width in S units per frame
_TAIL_RTR_H = [3, 2, 1]   # tail rotor height in S units per frame

def draw_chopper_sprite(surf, x, y, color, frame, pid, invuln, t, tilt=0.0):
    """
    Blocky pixel-art helicopter facing RIGHT (cockpit right, tail left).
    tilt: -1=leaning back (moving left)  0=level  +1=leaning forward (moving right)
    Visual shear: cockpit drops / rises, tail rises / drops.
    """
    if invuln > 0 and int(t*9)%2==0:
        return

    tp   = int(tilt * 5)          # tilt offset in px (positive = nose-down)
    dim  = tuple(max(0, v-80) for v in color)
    glass= (140, 200, 255)

    # ── Body (stays level) ──────────────────────────────────────────────────
    pygame.draw.rect(surf, color, (x-5*S, y-S, 10*S, 3*S))

    # ── Cockpit (right side, tilts with forward lean) ────────────────────────
    cy_off = tp
    pygame.draw.rect(surf, glass, (x+2*S, y-2*S+cy_off, 3*S, 3*S))
    pygame.draw.rect(surf, WHITE, (x+3*S, y-S+cy_off,     S,   S))  # shine

    # ── Tail boom + fin (left side, tilts opposite) ──────────────────────────
    ty_off = -tp
    pygame.draw.rect(surf, dim, (x-9*S, y+ty_off,       4*S, 2*S))
    pygame.draw.rect(surf, dim, (x-9*S, y-2*S+ty_off,   S,   2*S))

    # ── Tail rotor ───────────────────────────────────────────────────────────
    trh = _TAIL_RTR_H[frame] * S
    pygame.draw.rect(surf, WHITE, (x-10*S, y-trh//2+S+ty_off, S, trh))

    # ── Rotor mast + blade ───────────────────────────────────────────────────
    pygame.draw.rect(surf, dim,   (x-S//2, y-3*S, S, 2*S))
    rh = _ROTOR_HALF[frame] * S
    pygame.draw.rect(surf, WHITE, (x-rh,   y-4*S, rh*2, S))

    # ── Label ────────────────────────────────────────────────────────────────
    blit(surf, f"P{pid+1}", 11, WHITE, (x, y-6*S))


# ── Chopper ───────────────────────────────────────────────────────────────────
class Chopper:
    def __init__(self, idx, color):
        self.idx   = idx
        self.color = color
        self.lives = CHOP_LIVES
        self._spawn()

    def _spawn(self, cave=None):
        self.sx = float(SPAWN_XS[self.idx])
        if cave is not None:
            ty,by   = cave.gap_at(self.sx)
            self.sy = float((ty+by)/2)
        else:
            self.sy = float(H//2)
        self.vy     = 0.0
        self.tilt   = 0.0
        self.alive  = True
        self.cause  = ""
        self.invuln = INVULN_DUR
        self.blade  = random.uniform(0, 360)
        self.ammo   = [0.0]*MISSILE_SLOTS

    def respawn(self, cave): self._spawn(cave)

    @property
    def frame(self): return int(self.blade/120)%3

    @property
    def ammo_ready(self): return sum(1 for t in self.ammo if t<=0)

    def update(self, dt, inp, sdx, cave, obs_list, debris_list, bits_list):
        if not self.alive: return

        self.blade  = (self.blade + 600*dt) % 360
        self.invuln = max(0.0, self.invuln - dt)
        self.ammo   = [max(0.0, t-dt) for t in self.ammo]

        # Tilt: lerp toward ±1 based on horizontal input
        target_tilt = 0.0
        if   inp.held(self.idx,"RIGHT"): target_tilt =  1.0
        elif inp.held(self.idx,"LEFT"):  target_tilt = -1.0
        self.tilt += (target_tilt - self.tilt) * min(1.0, dt*6)

        # Vertical physics
        if inp.just(self.idx,"JUMP"):
            self.vy = min(self.vy, 0)   # snap out of downward momentum
        accel = GRAVITY - (THRUST if inp.held(self.idx,"JUMP") else 0)
        self.vy = max(VY_MIN, min(VY_MAX, self.vy + accel*dt))
        self.sy += self.vy*dt

        # Horizontal
        if inp.held(self.idx,"LEFT"):  self.sx -= PMOVE_SPD*dt
        if inp.held(self.idx,"RIGHT"): self.sx += PMOVE_SPD*dt
        self.sx = max(DEATH_X+1, min(W-20, self.sx))

        if self.invuln > 0:
            ity, iby = cave.gap_at(self.sx)
            if self.sy < ity + CHOP_R:
                self.sy = float(ity + CHOP_R)
                self.vy = max(0.0, self.vy)
            elif self.sy > iby - CHOP_R:
                self.sy = float(iby - CHOP_R)
                self.vy = min(0.0, self.vy)
            return

        if self.sx <= DEATH_X:
            self._die("left behind")
        elif cave.collides(self.sx, self.sy):
            self._die("crashed")
        elif self.sy<0 or self.sy>H:
            self._die("out of bounds")
        else:
            for o in obs_list:
                if o.hit(self.sx,self.sy,cave.scroll):
                    self._die("crashed"); return
            for d in debris_list:
                if d.alive and d.hit(self.sx,self.sy):
                    self._die("crushed"); return
            for hb in bits_list:
                if hb.alive and hb.hit(self.sx,self.sy):
                    self._die("hit by wreckage"); return

    def _die(self, cause):
        self.alive=False; self.cause=cause; self.lives-=1

    def fire(self, missiles):
        if not self.alive or self.invuln>0: return False
        for i,t in enumerate(self.ammo):
            if t<=0:
                self.ammo[i]=MISSILE_CD
                missiles.append(Missile(self.sx+26,self.sy,self.idx,self.color))
                return True
        return False

    def bits(self):
        return [HeliBit(self.sx,self.sy,k,self.color) for k in ('body','tail','rotor')]

    def draw(self, surf, t):
        if not self.alive: return
        draw_chopper_sprite(surf, int(self.sx), int(self.sy),
                            self.color, self.frame, self.idx,
                            self.invuln, t, self.tilt)


# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud(surf, choppers, active, speed):
    col_w=W//4
    for i in active:
        c=choppers[i]; col=PCOLORS[i]; cx=col_w*i+16
        alive_col=col if (c.alive or c.lives>0) else GRAY
        # Keep HUD below TV bezel (top 30px obscured per CLAUDE.md)
        blit(surf,"♥"*c.lives+"♡"*(CHOP_LIVES-c.lives),18,alive_col,(cx,36),anchor="topleft")
        for sl in range(MISSILE_SLOTS):
            pygame.draw.rect(surf,col if c.ammo[sl]<=0 else DGRAY,(cx+sl*18,60,13,8))
        if not c.alive and c.lives==0:
            blit(surf,"OUT",14,GRAY,(cx+72,36),anchor="topleft")
    blit(surf,f"spd {int(speed)}",14,GRAY,(W//2,36))


# ── Lobby ─────────────────────────────────────────────────────────────────────
INACTIVE,WAITING,READY=0,1,2

def lobby(inp):
    states=[INACTIVE]*4; cdwn=None
    inp.reset_activity()

    while True:
        dt=min(clock.tick(60)/1000.0,0.05)
        events=pygame.event.get()
        inp.pump(events)

        if inp.timed_out(): return False

        for e in events:
            if e.type==pygame.QUIT: return False
            if e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE: return False

        if any(inp.held(p,"JUMP") and inp.held(p,"ATTACK") for p in range(4)):
            return False

        for pid in range(4):
            s=states[pid]
            if s==INACTIVE:
                if inp.any_just(pid): states[pid]=WAITING
            elif s==WAITING:
                if   inp.just(pid,"ATTACK"): states[pid]=INACTIVE
                elif inp.just(pid,"JUMP"):   states[pid]=READY
            else:
                if inp.just(pid,"JUMP") or inp.just(pid,"ATTACK"): states[pid]=WAITING

        joined   =[p for p in range(4) if states[p]!=INACTIVE]
        all_ready=bool(joined) and all(states[p]==READY for p in joined)

        if all_ready:
            if cdwn is None: cdwn=3.0
            else:
                cdwn-=dt
                if cdwn<=0: return joined
        else:
            cdwn=None

        screen.fill(BG)
        blit(screen,"CHOPPER CHASE",72,WHITE,(W//2,120))
        blit(screen,"fly  dodge  shoot  last pilot wins",18,GRAY,(W//2,210))

        col_w=W//4
        for pid in range(4):
            cx=col_w*pid+col_w//2; cy=H//2; col=PCOLORS[pid]; s=states[pid]
            box=(25,28,45) if s==INACTIVE else (35,40,60)
            brd=col if s!=INACTIVE else DGRAY
            pygame.draw.rect(screen,box,(col_w*pid+30,cy-130,col_w-60,270),border_radius=8)
            pygame.draw.rect(screen,brd,(col_w*pid+30,cy-130,col_w-60,270),2,border_radius=8)
            blit(screen,f"P{pid+1}",48,col if s!=INACTIVE else DGRAY,(cx,cy-80))
            draw_chopper_sprite(screen,cx,cy-10,col if s!=INACTIVE else DGRAY,0,pid,0.0,0.0)
            if s==INACTIVE:
                blit(screen,"PRESS ANY",14,GRAY,(cx,cy+44))
                blit(screen,"BUTTON",14,GRAY,(cx,cy+66))
            elif s==WAITING:
                blit(screen,"JUMP to ready",18,WHITE,(cx,cy+44))
                blit(screen,"ATTACK to leave",14,GRAY,(cx,cy+68))
            else:
                blit(screen,"READY!",24,col,(cx,cy+52))

        if cdwn is not None:
            blit(screen,f"starting in {math.ceil(max(0,cdwn))}",36,WHITE,(W//2,H-100))
        else:
            blit(screen,"hold JUMP+ATTACK to quit",14,GRAY,(W//2,H-60))

        pygame.display.flip()


# ── End screen ────────────────────────────────────────────────────────────────
def end_screen(choppers, active, inp):
    ranked=sorted([choppers[i] for i in active],key=lambda c:c.lives,reverse=True)
    winner=ranked[0] if ranked[0].lives>0 else None
    sel=0
    inp.reset_activity()

    while True:
        events=pygame.event.get()
        inp.pump(events)
        if inp.timed_out(): return False
        for e in events:
            if e.type==pygame.QUIT: return False
            if e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE: return False
        for pid in range(4):
            if inp.just(pid,"LEFT") or inp.just(pid,"UP"):    sel=(sel-1)%2
            if inp.just(pid,"RIGHT") or inp.just(pid,"DOWN"): sel=(sel+1)%2
            if inp.just(pid,"JUMP") or inp.just(pid,"ATTACK"): return sel==0

        screen.fill(BG)
        if winner:
            blit(screen,f"PLAYER {winner.idx+1} WINS!",72,PCOLORS[winner.idx],(W//2,H//2-200))
        else:
            blit(screen,"ALL PILOTS DOWN",72,WHITE,(W//2,H//2-200))
        for rank,c in enumerate(ranked):
            col=PCOLORS[c.idx] if c.lives>0 else GRAY
            blit(screen,f"P{c.idx+1}  {'♥'*c.lives}{'♡'*(CHOP_LIVES-c.lives)}  {c.cause or 'survived'}",
                 24,col,(W//2,H//2-90+rank*44))
        for opt,label,oy in ((0,"PLAY AGAIN",H//2+120),(1,"QUIT",H//2+170)):
            col=WHITE if sel==opt else GRAY
            blit(screen,f"> {label} <" if sel==opt else f"  {label}  ",36,col,(W//2,oy))
        pygame.display.flip()
        clock.tick(60)


# ── Play ──────────────────────────────────────────────────────────────────────
def play(inp, active):
    solo=len(active)==1
    cave     =Cave()
    choppers =[Chopper(i,PCOLORS[i]) for i in range(4)]
    missiles,sparks,obs_list,debris_list,bits_list=[],[],[],[],[]
    next_wx  =float(W+OBS_MIN_GAP)
    elapsed,t_total,cdwn=0.0,0.0,3.0
    prev_alive={i:True for i in active}
    inp.reset_activity()

    while True:
        dt=min(clock.tick(60)/1000.0,0.05)
        t_total+=dt
        events=pygame.event.get()
        inp.pump(events)
        if inp.timed_out(): return False
        for e in events:
            if e.type==pygame.QUIT: return False
            if e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE: return False

        if cdwn>0:
            cdwn-=dt
            screen.fill(BG); cave.draw(screen)
            for i in active: choppers[i].draw(screen,t_total)
            blit(screen,str(math.ceil(cdwn)) if cdwn>0 else "GO!",72,WHITE,(W//2,H//2))
            pygame.display.flip()
            continue

        elapsed+=dt
        speed  =SCROLL_START*(2.0**(elapsed/SCROLL_DOUBLE))
        sdx    =speed*dt

        # Convert shrinking gap to tile units
        min_gap_px = (GAP_T_START + (GAP_T_MIN - GAP_T_START)*min(1.0,elapsed/GAP_SHRINK_T)) * TILE
        gap_tiles  = max(GAP_T_MIN, round(min_gap_px/TILE))

        cave.update(sdx, gap_tiles)

        if next_wx-cave.scroll<W+120:
            obs_list.extend(make_obs(next_wx,cave,elapsed))
            next_wx+=random.randint(OBS_MIN_GAP,OBS_MAX_GAP)
        for o in obs_list: o.cull(cave.scroll)
        obs_list=[o for o in obs_list if o.alive]

        still_in=[i for i in active if choppers[i].alive or choppers[i].lives>0]

        for i in active:
            c=choppers[i]; was=prev_alive[i]
            if c.alive:
                c.update(dt,inp,sdx,cave,obs_list,debris_list,bits_list)
                if inp.just(i,"ATTACK"): c.fire(missiles)
            if was and not c.alive:
                n=22 if c.lives==0 else 14
                sparks+=[Spark(c.sx,c.sy,c.color) for _ in range(n)]
                sparks+=[Spark(c.sx,c.sy,WHITE)   for _ in range(n//3)]
                bits_list.extend(c.bits())
                if c.lives>0:
                    remaining=[j for j in active if choppers[j].alive or choppers[j].lives>0]
                    if solo or len(remaining)>1:
                        c.respawn(cave)
            prev_alive[i]=c.alive

        new_debris=[]
        for m in missiles:
            m.update(dt,sdx)
            if not m.alive: continue
            if m.sy < 0 or m.sy > H: m.alive=False; continue
            wall_d = cave.missile_destroy(m.sx, m.sy)
            if wall_d:
                new_debris.extend(wall_d)
                sparks += [Spark(m.sx, m.sy, WHITE) for _ in range(5)]
                m.alive=False; continue
            blocked=False
            for o in obs_list:
                if o.hit(m.sx,m.sy,cave.scroll,r=5):
                    new_debris.extend(o.missile_hit(m.sy,cave.scroll))
                    m.alive=False; blocked=True; break
            if blocked or not m.alive: continue
            for i in active:
                c=choppers[i]
                if c.alive and i!=m.owner and c.invuln<=0:
                    if abs(m.sx-c.sx)<24 and abs(m.sy-c.sy)<20:
                        c._die(f"shot by P{m.owner+1}"); m.alive=False; break

        missiles=[m for m in missiles if m.alive]
        debris_list+=new_debris
        for d in debris_list: d.update(dt,sdx)
        debris_list=[d for d in debris_list if d.alive]
        for hb in bits_list: hb.update(dt,sdx)
        bits_list=[hb for hb in bits_list if hb.alive]
        for s in sparks: s.update(dt,sdx)
        sparks=[s for s in sparks if s.life>0]

        still_in=[i for i in active if choppers[i].alive or choppers[i].lives>0]
        if len(still_in)<=(0 if solo else 1):
            return choppers,active

        screen.fill(BG); cave.draw(screen)
        for o in obs_list:    o.draw(screen,cave.scroll)
        for d in debris_list: d.draw(screen)
        for s in sparks:      s.draw(screen)
        for m in missiles:    m.draw(screen)
        for hb in bits_list:  hb.draw(screen)
        for i in active:      choppers[i].draw(screen,t_total)
        pygame.draw.rect(screen,DANGER,(0,0,DEATH_X,H))
        draw_hud(screen,choppers,active,speed)
        pygame.display.flip()


# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    inp=Input()
    while True:
        active=lobby(inp)
        if active is False: break
        result=play(inp,active)
        if result is False: break
        choppers,active=result
        if not end_screen(choppers,active,inp): break
    pygame.quit()
    sys.exit()

if __name__=="__main__":
    main()
