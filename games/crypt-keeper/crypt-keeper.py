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

# ========== INPUT CLASS (copy verbatim) ==========
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

# ========== GAME CLASSES ==========
PCOLORS = [
    ( 30, 130, 255),  # P1 — blue
    (255, 210,  40),  # P2 — yellow
    (150,  60, 210),  # P3 — purple
    (220,  40,  40),  # P4 — red
]

PLAYER_SIZE = 40
ENEMY_SIZE = 30
PLAYER_SPEED = 150  # pixels per second
ENEMY_BASE_SPEED = 30  # pixels per second, increases with wave
ATTACK_RANGE = 100
ATTACK_WIDTH = 30
JUMP_RADIUS = 120
ATTACK_COOLDOWN = 0.3
JUMP_COOLDOWN = 1.0
ENEMY_DAMAGE = 1
PLAYER_START_HEALTH = 3

class Player:
    def __init__(self, pid):
        self.pid = pid
        self.color = PCOLORS[pid]
        self.x = random.randint(100, W-100)
        self.y = random.randint(100, H-100)
        self.health = PLAYER_START_HEALTH
        self.facing = (1, 0)  # default facing right
        self.last_attack = 0
        self.last_jump = 0

    def update(self, dt, inp):
        # Movement
        dx = dy = 0
        if inp.held(self.pid, "UP"):
            dy -= 1
        if inp.held(self.pid, "DOWN"):
            dy += 1
        if inp.held(self.pid, "LEFT"):
            dx -= 1
        if inp.held(self.pid, "RIGHT"):
            dx += 1

        length = math.hypot(dx, dy)
        if length > 0:
            dx /= length
            dy /= length
            self.facing = (dx, dy)
            self.x += dx * PLAYER_SPEED * dt
            self.y += dy * PLAYER_SPEED * dt

        # Keep player on screen
        self.x = max(PLAYER_SIZE//2, min(W - PLAYER_SIZE//2, self.x))
        self.y = max(PLAYER_SIZE//2 + 30, min(H - PLAYER_SIZE//2, self.y))  # +30 for bezel

    def attack(self, current_time, enemies):
        if current_time - self.last_attack < ATTACK_COOLDOWN:
            return []
        self.last_attack = current_time

        # Create attack rectangle in front of player
        ax = self.x + self.facing[0] * (PLAYER_SIZE//2 + ATTACK_WIDTH//2)
        ay = self.y + self.facing[1] * (PLAYER_SIZE//2 + ATTACK_WIDTH//2)
        attack_rect = pygame.Rect(
            ax - ATTACK_WIDTH//2,
            ay - ATTACK_RANGE//2,
            ATTACK_WIDTH,
            ATTACK_RANGE
        )
        # Rotate rectangle to face direction? For simplicity, we'll assume facing right and adjust
        # Actually, let's make it axis-aligned but positioned correctly
        # We'll create a rectangle that extends in the facing direction
        if abs(self.facing[0]) > abs(self.facing[1]):  # mostly horizontal
            attack_rect = pygame.Rect(
                self.x + (PLAYER_SIZE//2 if self.facing[0] > 0 else -ATTACK_RANGE),
                self.y - ATTACK_WIDTH//2,
                ATTACK_RANGE if self.facing[0] > 0 else ATTACK_RANGE,
                ATTACK_WIDTH
            )
        else:  # mostly vertical
            attack_rect = pygame.Rect(
                self.x - ATTACK_WIDTH//2,
                self.y + (PLAYER_SIZE//2 if self.facing[1] > 0 else -ATTACK_RANGE),
                ATTACK_WIDTH,
                ATTACK_RANGE if self.facing[1] > 0 else ATTACK_RANGE
            )

        # Check which enemies are hit
        hit_enemies = []
        for enemy in enemies:
            if attack_rect.colliderect(enemy.rect):
                hit_enemies.append(enemy)
        return hit_enemies

    def jump(self, current_time, enemies):
        if current_time - self.last_jump < JUMP_COOLDOWN:
            return []
        self.last_jump = current_time

        # Create jump circle
        jump_rect = pygame.Rect(
            self.x - JUMP_RADIUS,
            self.y - JUMP_RADIUS,
            JUMP_RADIUS * 2,
            JUMP_RADIUS * 2
        )

        # Check which enemies are hit
        hit_enemies = []
        for enemy in enemies:
            if jump_rect.colliderect(enemy.rect):
                hit_enemies.append(enemy)
        return hit_enemies

class Enemy:
    def __init__(self, wave):
        self.wave = wave
        self.speed = ENEMY_BASE_SPEED + (wave - 1) * 5  # increase speed with wave
        self.color = (100, 100, 100)  # dungeon gray
        # Spawn at random edge
        side = random.randint(0, 3)
        if side == 0:  # top
            self.x = random.randint(0, W)
            self.y = -ENEMY_SIZE
        elif side == 1:  # right
            self.x = W + ENEMY_SIZE
            self.y = random.randint(0, H)
        elif side == 2:  # bottom
            self.x = random.randint(0, W)
            self.y = H + ENEMY_SIZE
        else:  # left
            self.x = -ENEMY_SIZE
            self.y = random.randint(0, H)

        self.rect = pygame.Rect(self.x - ENEMY_SIZE//2,
                               self.y - ENEMY_SIZE//2,
                               ENEMY_SIZE, ENEMY_SIZE)

    def update(self, dt, players):
        # Move toward nearest player
        closest_player = None
        closest_dist = float('inf')

        for player in players:
            if player.health > 0:
                dist = math.hypot(player.x - self.x, player.y - self.y)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_player = player

        if closest_player:
            dx = closest_player.x - self.x
            dy = closest_player.y - self.y
            length = math.hypot(dx, dy)
            if length > 0:
                dx /= length
                dy /= length
                self.x += dx * self.speed * dt
                self.y += dy * self.speed * dt

        self.rect.x = self.x - ENEMY_SIZE//2
        self.rect.y = self.y - ENEMY_SIZE//2

        # Check collision with players
        for player in players:
            if player.health > 0 and self.rect.colliderect(
                pygame.Rect(player.x - PLAYER_SIZE//2,
                           player.y - PLAYER_SIZE//2,
                           PLAYER_SIZE, PLAYER_SIZE)):
                player.health -= ENEMY_DAMAGE
                return True  # enemy should be removed after hitting
        return False

class Game:
    def __init__(self):
        self.inp   = Input()
        self.state = "ATTRACT"
        self.players = []  # list of Player objects
        self.joined_players = set()  # which player indices have joined
        self.enemies = []
        self.wave_number = 0
        self.enemies_to_spawn = 0
        self.spawn_timer = 0
        self.spawn_interval = 1.0  # seconds between spawns
        self.wave_clear_timer = 0
        self.wave_clear_delay = 2.0  # seconds to wait before next wave
        self.game_over_timer = 0
        self.game_over_delay = 3.0  # seconds before returning to attract
        self.score = 0
        self.wave_survived = 0
        self.enemies_killed = 0

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
            if self.inp.just(pid, "ATTACK") and pid not in self.joined_players:
                self.joined_players.add(pid)
                self.players.append(Player(pid))

        # Start game if at least one player joined
        if len(self.joined_players) > 0:
            self.state = "PLAYING"
            self._start_wave()

        # Draw attract screen
        screen.fill((0, 0, 0))
        blit(screen, "CRYPT KEEPER", 72, (200, 50, 50), (CX, H//4), anchor="center")
        blit(screen, "Survive endless waves of dungeon horrors", 24, (180, 180, 180), (CX, H//4 + 80), anchor="center")
        blit(screen, "Press ATTACK to join", 36, (255, 255, 255), (CX, H//2), anchor="center")
        blit(screen, f"Players joined: {len(self.joined_players)}/4", 24, (200, 200, 200), (CX, H//2 + 50), anchor="center")
        blit(screen, "JUMP: Area clear  |  ATTACK: Directional strike", 18, (150, 150, 150), (CX, H*3//4), anchor="center")
        blit(screen, "Hold ATTACK+JUMP with 2 players to quit during game", 18, (100, 100, 100), (CX, H*3//4 + 30), anchor="center")

    def _start_wave(self):
        self.wave_number += 1
        # Wave difficulty: more enemies and faster spawn
        base_count = 3
        self.enemies_to_spawn = base_count + (self.wave_number - 1) * 2
        self.spawn_interval = max(0.3, 1.0 - (self.wave_number - 1) * 0.05)
        self.spawn_timer = 0
        self.enemies = []  # clear existing enemies

    def _playing(self, dt):
        current_time = time.time()

        # Spawn enemies
        if self.enemies_to_spawn > 0:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                self.enemies.append(Enemy(self.wave_number))
                self.enemies_to_spawn -= 1
                self.spawn_timer = self.spawn_interval

        # Update players
        for player in self.players:
            if player.pid in self.joined_players and player.health > 0:
                player.update(dt, self.inp)

                # Handle attack
                if self.inp.just(player.pid, "ATTACK"):
                    hit_enemies = player.attack(current_time, self.enemies)
                    for enemy in hit_enemies:
                        if enemy in self.enemies:
                            self.enemies.remove(enemy)
                            self.score += 10
                            self.enemies_killed += 1

                # Handle jump
                if self.inp.just(player.pid, "JUMP"):
                    hit_enemies = player.jump(current_time, self.enemies)
                    for enemy in hit_enemies:
                        if enemy in self.enemies:
                            self.enemies.remove(enemy)
                            self.score += 15
                            self.enemies_killed += 1

        # Update enemies
        for enemy in self.enemies[:]:
            if enemy.update(dt, self.players):
                if enemy in self.enemies:
                    self.enemies.remove(enemy)

        # Check if wave is complete
        if len(self.enemies) == 0 and self.enemies_to_spawn == 0:
            self.wave_clear_timer += dt
            if self.wave_clear_timer >= self.wave_clear_delay:
                self.wave_survived += 1
                self._start_wave()
        else:
            self.wave_clear_timer = 0

        # Check for two-player quit condition (ATTACK+JUMP held by 2 different players)
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

        # Check if all players are dead
        alive_players = [p for p in self.players if p.health > 0 and p.pid in self.joined_players]
        if len(alive_players) == 0:
            self.state = "GAME_OVER"
            self.game_over_timer = 0

        # Draw playing screen
        screen.fill((10, 10, 20))  # dark blue-black background

        # Draw enemies
        for enemy in self.enemies:
            pygame.draw.rect(screen, enemy.color, enemy.rect)

        # Draw players
        for player in self.players:
            if player.pid in self.joined_players:
                # Draw player
                pygame.draw.rect(screen, player.color,
                                pygame.Rect(player.x - PLAYER_SIZE//2,
                                           player.y - PLAYER_SIZE//2,
                                           PLAYER_SIZE, PLAYER_SIZE))
                # Draw health
                for i in range(player.health):
                    pygame.draw.rect(screen, (255, 0, 0),
                                    pygame.Rect(player.x - PLAYER_SIZE//2 + i*8,
                                               player.y - PLAYER_SIZE//2 - 10,
                                                6, 6))
                # Draw attack/jump effects
                current_time = time.time()
                if current_time - player.last_attack < 0.2:
                    # Draw attack effect
                    if abs(player.facing[0]) > abs(player.facing[1]):
                        pygame.draw.rect(screen, (255, 255, 255),
                                        pygame.Rect(player.x + (PLAYER_SIZE//2 if player.facing[0] > 0 else -ATTACK_RANGE),
                                                   player.y - ATTACK_WIDTH//2,
                                                   ATTACK_RANGE if player.facing[0] > 0 else ATTACK_RANGE,
                                                   ATTACK_WIDTH), 2)
                    else:
                        pygame.draw.rect(screen, (255, 255, 255),
                                        pygame.Rect(player.x - ATTACK_WIDTH//2,
                                                   player.y + (PLAYER_SIZE//2 if player.facing[1] > 0 else -ATTACK_RANGE),
                                                   ATTACK_WIDTH,
                                                   ATTACK_RANGE if player.facing[1] > 0 else ATTACK_RANGE), 2)
                if current_time - player.last_jump < 0.2:
                    # Draw jump effect
                    pygame.draw.circle(screen, (255, 255, 255),
                                     (int(player.x), int(player.y)), JUMP_RADIUS, 2)

        # Draw UI (top, but below bezel)
        ui_y = 40
        blit(screen, f"Wave: {self.wave_number}", 24, (255, 255, 255), (100, ui_y), anchor="left")
        blit(screen, f"Enemies: {len(self.enemies)}", 24, (255, 255, 255), (300, ui_y), anchor="left")
        blit(screen, f"Score: {self.score}", 24, (255, 255, 255), (500, ui_y), anchor="left")

        # Draw player health indicators
        for i, player in enumerate(self.players):
            if player.pid in self.joined_players:
                color = PCOLORS[player.pid]
                blit(screen, f"P{i+1}:", 18, color, (100, ui_y + 30 + i*25), anchor="left")
                for j in range(PLAYER_START_HEALTH):
                    heart_color = (255, 0, 0) if j < player.health else (50, 50, 50)
                    pygame.draw.rect(screen, heart_color,
                                   (150 + j*12, ui_y + 20 + i*25, 10, 10))

        # Instructions
        blit(screen, "ATTACK: Directional strike  |  JUMP: Area clear", 18, (180, 180, 180), (CX, H - 60), anchor="center")

    def _game_over(self, dt):
        # Quit: any player holds ATTACK+JUMP on the results screen
        for pid in range(4):
            if self.inp.held(pid, "ATTACK") and self.inp.held(pid, "JUMP"):
                pygame.quit(); sys.exit()

        self.game_over_timer += dt
        if self.game_over_timer > self.game_over_delay:
            # Reset game
            self.__init__()
            self.state = "ATTRACT"

        # Draw game over screen
        screen.fill((0, 0, 0))
        blit(screen, "GAME OVER", 72, (200, 50, 50), (CX, H//3), anchor="center")
        blit(screen, f"Waves survived: {self.wave_survived}", 36, (255, 255, 255), (CX, H//2), anchor="center")
        blit(screen, f"Enemies defeated: {self.enemies_killed}", 36, (255, 255, 255), (CX, H//2 + 50), anchor="center")
        blit(screen, f"Total score: {self.score}", 36, (255, 255, 255), (CX, H//2 + 100), anchor="center")
        blit(screen, "Press ATTACK to play again", 24, (200, 200, 200), (CX, H*3//4), anchor="center")

Game().run()