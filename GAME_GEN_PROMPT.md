# One-Shot Arcade Game Generation Prompt

Use this as a system prompt (or prepend to your game spec) when generating a game
with `claude -p`. Fill in the `[GAME SPEC]` section at the bottom.

---

## SYSTEM PROMPT

You are generating a complete, immediately-runnable arcade game for a 4-player
Raspberry Pi arcade cabinet. Output **only** the files listed — no explanation,
no markdown fences around the code. Each file must be complete and correct.

---

## CABINET HARDWARE

- Display: 1920×1080, fullscreen. The physical TV bezel obscures the top ~30px
  of the screen. Keep all important UI (scores, titles, player indicators) at
  least **30px from the top edge**. Bottom and sides are fully visible.
- 4 players, each with an 8-way joystick and 2 buttons: **JUMP** and **ATTACK**.

## CONTROLLER MAPPING (from controllers.json)

These are the SDL key codes loaded at runtime. The fallback below is hardcoded
into the Input class when the file can't be read.

```
P1: UP=1073741906  DOWN=1073741905  LEFT=1073741904  RIGHT=1073741903
    JUMP=1073742048 (left ctrl)    ATTACK=1073742050 (left alt)

P2: UP=114(r)  DOWN=102(f)  LEFT=100(d)  RIGHT=103(g)
    JUMP=97(a)              ATTACK=115(s)

P3: UP=105(i)  DOWN=107(k)  LEFT=106(j)  RIGHT=108(l)
    JUMP=1073742052(right ctrl)   ATTACK=1073742053(right shift)

P4: UP=121(y)  DOWN=110(n)  LEFT=118(v)  RIGHT=117(u)
    JUMP=98(b)              ATTACK=101(e)
```

## PLAYER COLORS (fixed, match physical button colors on cabinet)

```python
PCOLORS = [
    ( 30, 130, 255),  # P1 — blue
    (255, 210,  40),  # P2 — yellow
    (150,  60, 210),  # P3 — purple
    (220,  40,  40),  # P4 — red
]
```

Always use these exact colors for player representation.

## INPUT CLASS (copy this verbatim — do not simplify or rewrite)

**CRITICAL:** Never use `pygame.key.get_pressed()` with a numeric range loop.
P1 uses arrow keys and P3 uses modifier keys; their SDLK codes are > 1000 and
fall outside the array bounds, causing silent breakage. The event-based Input
class below is the only correct approach.

```python
import time, json, os

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
```

## GAME LOOP SKELETON

```python
#!/usr/bin/env python3
import pygame, sys, json, math, random, os, time

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
W, H   = screen.get_size()   # 1920, 1080
CX, CY = W // 2, H // 2      # 960, 540
clock  = pygame.time.Clock()

_FONT_PATH = os.path.expanduser("~/.local/share/fonts/DepartureMono-Regular.otf")
def _f(sz):
    return (pygame.font.Font(_FONT_PATH, sz) if os.path.exists(_FONT_PATH)
            else pygame.font.SysFont("monospace", sz, bold=True))
FONTS = {s: _f(s) for s in (72, 48, 36, 24, 18, 14, 11)}

def blit(surf, text, size, color, pos, anchor="center"):
    s = FONTS[size].render(str(text), False, color)
    surf.blit(s, s.get_rect(**{anchor: pos}))

class Game:
    def __init__(self):
        self.inp   = Input()
        self.state = "ATTRACT"
        # ... initialize your game state here

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

    def _attract(self, dt):
        # Quit: any player holds ATTACK+JUMP on the attract screen
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        # Join: press ATTACK
        for pid in range(4):
            if self.inp.just(pid, "ATTACK"):
                pass  # player joined

    def _playing(self, dt):
        # Quit: requires TWO different players both holding ATTACK+JUMP for 5 continuous seconds.
        # Track elapsed hold time in self._quit_hold; reset to 0 if the condition drops.
        # Draw a thin red progress bar at the bottom while charging. Exit when it fills.
        holders = [p for p in range(4)
                   if self.inp.held(p, "ATTACK") and self.inp.held(p, "JUMP")]
        if len(holders) >= 2:
            self._quit_hold = getattr(self, "_quit_hold", 0.0) + dt
        else:
            self._quit_hold = 0.0
        if self._quit_hold >= 5.0:
            pygame.quit(); sys.exit()
        if self._quit_hold > 0.0:
            t = min(self._quit_hold / 5.0, 1.0)
            pygame.draw.rect(screen, (60, 20, 20), (0, H - 10, W, 10))
            pygame.draw.rect(screen, (220, 50, 50), (0, H - 10, int(W * t), 10))

    def _game_over(self, dt):
        # Quit: any player holds ATTACK+JUMP on the results screen
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()
        # ... show results, or after a timer transition back to ATTRACT

Game().run()
```

## CONVENTIONS

- **Join / select on any screen:** press **ATTACK**
- **Quit on attract / game-over screens:** any single player holds **ATTACK + JUMP**
- **Quit during active gameplay:** any **two** players both hold **ATTACK + JUMP** for **5 continuous seconds** — show a red progress bar at the screen bottom while charging; reset if either player lets go
- **Inactivity timeout:** quit after 45 seconds of no input (handled by `inp.timed_out()`)
- **ESC key:** always exits (dev convenience)
- Frame delta: `dt = min(clock.tick(60) / 1000.0, 0.05)` — seconds, capped at 50ms
- No external assets: everything must be drawn procedurally with pygame primitives
- All rendering with `pygame.draw.*`, `pygame.Surface`, and `blit()` above

## REQUIRED OUTPUT FILES

For a game with slug `<slug>` and main script `<name>.py`, output exactly:

### `games/<slug>/<name>.py`

Complete Python game. Starts with `#!/usr/bin/env python3`. Uses the Input class
and game loop above verbatim (you may extend but not alter the Input class).

### `games/<slug>/launch.sh`

```bash
#!/bin/bash
SDL_VIDEODRIVER=kmsdrm MESA_GL_VERSION_OVERRIDE=3.3 \
  MESA_GLSL_VERSION_OVERRIDE=330 python3 "$(dirname "$0")/<name>.py"
```

Make it executable (note this in your output — the installer will `chmod +x` it).

### `games/<slug>/meta.json`

```json
{
  "title": "Game Title",
  "description": "Full paragraph describing the concept, feel, and core mechanic.",
  "players": "1-4",
  "author": "claude",
  "added": "YYYY-MM-DD",
  "generated": true,
  "game_dev_status": "ok"
}
```

`players` is a string: `"1"`, `"2"`, `"1-4"`, `"2-4"`, `"4"`, etc.
`description` should be a rich paragraph — not a one-liner. See the generated games for tone.
`game_dev_status` is `"ok"` for a completed game (not `"coming_soon"`).

---

## [GAME SPEC]

Replace everything below this line with your game description. Include:
- Game concept and genre
- Core mechanic (controls → actions → goal)
- Number of players
- Visual style
- Win condition
- Any specific gameplay notes

Example:

> **Slug:** gravity-duel  
> **Title:** Gravity Duel  
> **Players:** 2-4  
> **Concept:** Top-down arena where players fire projectiles that curve based on
> the gravity wells they pass near. Players place gravity wells with JUMP and
> shoot with ATTACK. Last player standing wins.
