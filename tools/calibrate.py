#!/usr/bin/env python3
"""
Arcade controller calibration wizard.
Guides each player through UP/DOWN/LEFT/RIGHT/ATTACK/JUMP.
Saves mappings to config/controllers.json.
Diagonals are handled at runtime as combinations.
"""
import pygame
import sys
import os
import json
import time

pygame.init()
W, H = 1280, 720
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Controller Calibration")
clock = pygame.time.Clock()

font_big  = pygame.font.SysFont("monospace", 52, bold=True)
font_med  = pygame.font.SysFont("monospace", 28)
font_sm   = pygame.font.SysFont("monospace", 20)

BLACK  = (0,   0,   0)
WHITE  = (255, 255, 255)
GRAY   = (60,  60,  60)
GREEN  = (0,   220, 80)
YELLOW = (220, 220, 0)
CYAN   = (0,   200, 220)
DIM    = (100, 100, 100)
RED    = (220, 50,  50)

NUM_PLAYERS = 4
STEPS = [
    ("UP",     "Push the stick UP"),
    ("DOWN",   "Push the stick DOWN"),
    ("LEFT",   "Push the stick LEFT"),
    ("RIGHT",  "Push the stick RIGHT"),
    ("ATTACK", "Press the ATTACK button"),
    ("JUMP",   "Press the JUMP button"),
]

pygame.joystick.init()
joysticks = {}
for i in range(pygame.joystick.get_count()):
    js = pygame.joystick.Joystick(i)
    js.init()
    joysticks[js.get_instance_id()] = js

mappings = []   # one dict per player, filled as we go
AXIS_THRESHOLD = 0.5

def flush_events():
    pygame.event.clear()
    time.sleep(0.15)

def draw_screen(player, step_name, prompt, captured=None, done=False, all_done=False):
    screen.fill(BLACK)

    if all_done:
        t = font_big.render("Calibration complete!", True, GREEN)
        screen.blit(t, t.get_rect(center=(W // 2, H // 2 - 40)))
        t2 = font_med.render("Saved to ~/controllers.json", True, WHITE)
        screen.blit(t2, t2.get_rect(center=(W // 2, H // 2 + 30)))
        t3 = font_sm.render("Press ESC to exit", True, DIM)
        screen.blit(t3, t3.get_rect(center=(W // 2, H // 2 + 80)))
        pygame.display.flip()
        return

    # Progress dots
    total = NUM_PLAYERS * len(STEPS)
    done_count = len(mappings) * len(STEPS) + STEPS.index((step_name, prompt))
    for i in range(total):
        col = GREEN if i < done_count else GRAY
        pygame.draw.circle(screen, col, (W // 2 - total * 9 + i * 18, 30), 6)

    p_txt = font_big.render(f"Player {player + 1}", True, CYAN)
    screen.blit(p_txt, p_txt.get_rect(center=(W // 2, 120)))

    action_txt = font_big.render(step_name, True, YELLOW)
    screen.blit(action_txt, action_txt.get_rect(center=(W // 2, 230)))

    prompt_txt = font_med.render(prompt, True, WHITE)
    screen.blit(prompt_txt, prompt_txt.get_rect(center=(W // 2, 310)))

    if captured:
        cap_txt = font_med.render(f"Got: {captured}", True, GREEN)
        screen.blit(cap_txt, cap_txt.get_rect(center=(W // 2, 400)))
        next_txt = font_sm.render("Hold... confirming", True, DIM)
        screen.blit(next_txt, next_txt.get_rect(center=(W // 2, 450)))
    else:
        wait_txt = font_sm.render("Waiting for input...", True, DIM)
        screen.blit(wait_txt, wait_txt.get_rect(center=(W // 2, 400)))

    hint = font_sm.render("ESC = quit without saving", True, GRAY)
    screen.blit(hint, hint.get_rect(center=(W // 2, H - 30)))

    pygame.display.flip()


def wait_for_input():
    """
    Returns a dict describing the input:
      keyboard: {"type": "key", "key": keycode}
      joystick button: {"type": "js_button", "id": instance_id, "button": n}
      joystick axis:   {"type": "js_axis",   "id": instance_id, "axis": n, "sign": +/-1}
      joystick hat:    {"type": "js_hat",    "id": instance_id, "hat": n, "value": (x,y)}
    Returns None on ESC.
    """
    flush_events()
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                return {"type": "key", "key": event.key, "name": pygame.key.name(event.key)}

            if event.type == pygame.JOYDEVICEADDED:
                js = pygame.joystick.Joystick(event.device_index)
                js.init()
                joysticks[js.get_instance_id()] = js

            if event.type == pygame.JOYBUTTONDOWN:
                return {"type": "js_button", "id": event.instance_id, "button": event.button}

            if event.type == pygame.JOYAXISMOTION:
                if abs(event.value) >= AXIS_THRESHOLD:
                    return {"type": "js_axis", "id": event.instance_id,
                            "axis": event.axis, "sign": 1 if event.value > 0 else -1}

            if event.type == pygame.JOYHATMOTION:
                if event.value != (0, 0):
                    return {"type": "js_hat", "id": event.instance_id,
                            "hat": event.hat, "value": list(event.value)}


def describe(inp):
    if inp["type"] == "key":
        return f"key:{inp['name']}"
    if inp["type"] == "js_button":
        return f"js{inp['id']}_btn{inp['button']}"
    if inp["type"] == "js_axis":
        sign = "+" if inp["sign"] > 0 else "-"
        return f"js{inp['id']}_axis{inp['axis']}{sign}"
    if inp["type"] == "js_hat":
        return f"js{inp['id']}_hat{inp['hat']}={inp['value']}"
    return "?"


# ---- main calibration loop ----
all_done = False
aborted = False

for player in range(NUM_PLAYERS):
    player_map = {"player": player + 1, "inputs": {}}

    for step_name, prompt in STEPS:
        draw_screen(player, step_name, prompt)
        inp = wait_for_input()

        if inp is None:
            aborted = True
            break

        desc = describe(inp)
        draw_screen(player, step_name, prompt, captured=desc)
        time.sleep(0.6)   # brief confirmation pause

        player_map["inputs"][step_name] = inp

    if aborted:
        break

    mappings.append(player_map)

if not aborted and len(mappings) == NUM_PLAYERS:
    output = {"players": mappings, "diagonals": "combinations"}
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "controllers.json")
    with open(path, "w") as f:
        json.dump(output, f, indent=2)

    all_done = True
    draw_screen(0, "", "", all_done=True)
    waiting = True
    while waiting:
        clock.tick(30)
        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.KEYDOWN):
                waiting = False

pygame.quit()
sys.exit()
