#!/usr/bin/env python3
"""Tron Light Cycles — 4-player arcade"""
import pygame
import sys
import os
import json
import time

ARCADE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTROLLERS_JSON = os.path.join(ARCADE_DIR, "config", "controllers.json")

CELL           = 10
FPS            = 13
TOP_MARGIN     = 25   # ~half inch of bezel obscures cabinet TV top
BOTTOM_MARGIN  = 32   # reserved for jump pip display
MAX_RESERVE    = 10   # starting jump reserve (in pips)
RESERVE_CAP    = 15   # max reserve (can exceed 10 via replenishment)
JUMP_RATE      = 3    # pips consumed per second of hold
CELLS_PER_PIP  = 3    # each pip = 3 grid cells of jump distance

PLAYER_COLORS = [
    ( 34,  85, 255),  # P1 blue
    (255, 215,   0),  # P2 yellow
    (155,  48, 255),  # P3 purple
    (255,  48,  48),  # P4 red
]
PLAYER_NAMES = ["P1", "P2", "P3", "P4"]

def load_controls(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return []
    result = []
    for p in data.get("players", []):
        m = {}
        for action, info in p.get("inputs", {}).items():
            m[action] = info.get("key", 0)
        result.append(m)
    return result

def dim(color, factor=0.35):
    return tuple(int(c * factor) for c in color)

class Player:
    def __init__(self, idx, gw, gh, controls):
        starts = [
            (2,      2,       1,  0),
            (gw - 3, 2,       0,  1),
            (2,      gh - 3,  0, -1),
            (gw - 3, gh - 3, -1,  0),
        ]
        x, y, dx, dy = starts[idx]
        self.x, self.y         = x, y
        self.dx, self.dy       = dx, dy
        self.next_dx           = dx
        self.next_dy           = dy
        self.color             = PLAYER_COLORS[idx]
        self.name              = PLAYER_NAMES[idx]
        self.trail             = {(x, y)}
        self.alive             = True
        self.controls          = controls
        self.speed_mode        = False
        self.jump_reserve      = float(MAX_RESERVE)
        self.jump_cells_left   = 0
        self.jump_hold_start   = None
        self.move_credit       = 1.0  # start ready to move

    @property
    def is_jumping(self):
        return self.jump_cells_left > 0

    def key_down(self, key):
        c = self.controls
        if   key == c.get("UP")    and self.dy == 0: self.next_dx, self.next_dy =  0, -1
        elif key == c.get("DOWN")  and self.dy == 0: self.next_dx, self.next_dy =  0,  1
        elif key == c.get("LEFT")  and self.dx == 0: self.next_dx, self.next_dy = -1,  0
        elif key == c.get("RIGHT") and self.dx == 0: self.next_dx, self.next_dy =  1,  0
        elif key == c.get("ATTACK"):
            self.speed_mode = True
        elif key == c.get("JUMP") and self.jump_hold_start is None:
            self.jump_hold_start = time.monotonic()

    def key_up(self, key):
        c = self.controls
        if key == c.get("ATTACK"):
            self.speed_mode = False
        elif key == c.get("JUMP") and self.jump_hold_start is not None:
            held      = time.monotonic() - self.jump_hold_start
            pips_used = max(1, int(held * JUMP_RATE))
            pips_used = min(pips_used, int(self.jump_reserve))
            if pips_used > 0:
                self.jump_cells_left += pips_used * CELLS_PER_PIP
                self.jump_reserve    -= pips_used
            self.jump_hold_start = None

# ── movement & collision ──────────────────────────────────────────────────────

def move_round(players, gw, gh, trail_owner):
    """Advance all players with move_credit >= 1. Handles collisions."""
    moving = [p for p in players if p.alive and p.move_credit >= 1.0]
    if not moving:
        return

    for p in moving:
        p.dx, p.dy = p.next_dx, p.next_dy

    all_trails = set()
    for p in players:
        all_trails |= p.trail

    new_pos = {p: (p.x + p.dx, p.y + p.dy) for p in moving}
    dead    = set()

    # wall + trail collisions
    for p, (nx, ny) in new_pos.items():
        if nx < 0 or nx >= gw or ny < 0 or ny >= gh:
            dead.add(p)
            continue
        if not p.is_jumping and (nx, ny) in all_trails:
            dead.add(p)
            owner = trail_owner.get((nx, ny))
            if owner and owner is not p and owner.alive:
                owner.jump_reserve = min(owner.jump_reserve + 10, RESERVE_CAP)

    # head-on collisions
    by_pos = {}
    for p, pos in new_pos.items():
        if p not in dead:
            by_pos.setdefault(pos, []).append(p)
    for ps in by_pos.values():
        if len(ps) > 1:
            dead.update(ps)

    # commit
    for p in moving:
        p.move_credit -= 1.0
        if p in dead:
            p.alive = False
            continue
        nx, ny = new_pos[p]
        p.x, p.y = nx, ny
        if p.is_jumping:
            p.jump_cells_left -= 1
        elif not p.speed_mode:
            p.trail.add((nx, ny))
            trail_owner[(nx, ny)] = p

# ── drawing ───────────────────────────────────────────────────────────────────

def draw_pips(screen, players, sw, sh, font):
    section_w = sw // len(players)
    pip_w, pip_h, pip_gap = 14, 18, 3
    y = sh - BOTTOM_MARGIN + (BOTTOM_MARGIN - pip_h) // 2

    for i, p in enumerate(players):
        cx   = i * section_w + section_w // 2
        total = RESERVE_CAP * (pip_w + pip_gap) - pip_gap
        x    = cx - total // 2

        label = font.render(p.name, True, p.color if p.alive else dim(p.color, 0.5))
        screen.blit(label, (x - 34, y + 1))

        filled = int(p.jump_reserve)
        for j in range(RESERVE_CAP):
            color = p.color if j < filled else (25, 25, 25)
            if j == filled and p.jump_hold_start is not None:
                # partially charged pip pulses
                frac  = min(1.0, (time.monotonic() - p.jump_hold_start) * JUMP_RATE - (filled - int(p.jump_reserve)))
                color = tuple(int(c * max(0.15, frac)) for c in p.color)
            pygame.draw.rect(screen, color,
                             (x + j * (pip_w + pip_gap), y, pip_w, pip_h))

def draw_game(screen, players, trail_owner, sw, sh, gw, gh, font):
    screen.fill((8, 8, 6))

    for p in players:
        trail_color = dim(p.color) if p.alive else p.color
        for (tx, ty) in p.trail:
            pygame.draw.rect(screen, trail_color,
                             (tx * CELL, TOP_MARGIN + ty * CELL, CELL - 1, CELL - 1))

    for p in players:
        if not p.alive:
            continue
        if p.is_jumping:
            # Big bright head while airborne
            size       = CELL + 6
            off        = -3
            head_color = (255, 255, 255)
        elif p.jump_hold_start is not None:
            # Crouching — small, dimmed
            size       = CELL - 5
            off        = 2
            head_color = tuple(int(c * 0.5) for c in p.color)
        elif p.speed_mode:
            # Slightly brighter tint while boosting
            size, off  = CELL - 1, 0
            head_color = tuple(min(255, int(c * 1.5)) for c in p.color)
        else:
            size, off  = CELL - 1, 0
            head_color = (255, 255, 255)
        pygame.draw.rect(screen, head_color,
                         (p.x * CELL + off, TOP_MARGIN + p.y * CELL + off, size, size))

    draw_pips(screen, players, sw, sh, font)
    pygame.display.flip()

# ── screens ───────────────────────────────────────────────────────────────────

def text(surf, msg, size, color, cx, cy):
    font = pygame.font.SysFont(None, size)
    img  = font.render(msg, True, color)
    surf.blit(img, img.get_rect(center=(cx, cy)))

def countdown(screen, sw, sh):
    font = pygame.font.SysFont(None, 160)
    for n in ("3", "2", "1", "GO!"):
        screen.fill((0, 0, 0))
        img = font.render(n, True, (200, 200, 200))
        screen.blit(img, img.get_rect(center=(sw // 2, sh // 2)))
        pygame.display.flip()
        pygame.time.wait(700)
        for _ in pygame.event.get():
            pass

def result_screen(screen, winner, controls, sw, sh):
    screen.fill((0, 0, 0))
    if winner:
        text(screen, f"{winner.name}  WINS!", 100, winner.color, sw // 2, sh // 2 - 80)
    else:
        text(screen, "DRAW!", 100, (200, 200, 200), sw // 2, sh // 2 - 80)
    text(screen, "[ ATTACK ]  play again", 44, (160, 150, 120), sw // 2, sh // 2 + 30)
    text(screen, "[ JUMP ]  quit to menu", 44, (90, 85, 75),    sw // 2, sh // 2 + 90)
    pygame.display.flip()

    attack_keys = {c.get("ATTACK") for c in controls}
    jump_keys   = {c.get("JUMP")   for c in controls}
    pygame.time.wait(800)
    for _ in pygame.event.get():
        pass

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in attack_keys: return True
                if event.key in jump_keys:   return False

# ── main round ────────────────────────────────────────────────────────────────

def run_round(screen, controls, sw, sh):
    gw = sw  // CELL
    gh = (sh - TOP_MARGIN - BOTTOM_MARGIN) // CELL

    players     = [Player(i, gw, gh, controls[i] if i < len(controls) else {})
                   for i in range(min(4, len(controls)))]
    trail_owner = {}
    for p in players:
        for pos in p.trail:
            trail_owner[pos] = p

    pip_font = pygame.font.SysFont(None, 22)
    clock    = pygame.time.Clock()

    countdown(screen, sw, sh)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                for p in players:
                    if p.alive: p.key_down(event.key)
            if event.type == pygame.KEYUP:
                for p in players:
                    if p.alive: p.key_up(event.key)

        # Accumulate move credits
        for p in players:
            if p.alive:
                p.move_credit += 1.5 if p.speed_mode else 1.0

        # Process moves until all credits exhausted
        while any(p.alive and p.move_credit >= 1.0 for p in players):
            move_round(players, gw, gh, trail_owner)

        draw_game(screen, players, trail_owner, sw, sh, gw, gh, pip_font)
        clock.tick(FPS)

        alive = [p for p in players if p.alive]
        if len(alive) <= 1:
            return alive[0] if alive else None

# ── entry point ───────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    sw, sh = screen.get_size()

    controls = load_controls(CONTROLLERS_JSON)
    if not controls:
        pygame.quit()
        sys.exit(1)

    while True:
        winner = run_round(screen, controls, sw, sh)
        if winner == "quit":
            break
        if not result_screen(screen, winner, controls, sw, sh):
            break

    pygame.quit()

if __name__ == "__main__":
    main()
