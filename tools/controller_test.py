#!/usr/bin/env python3
"""
Arcade controller test/calibration tool.
Shows raw input from joysticks AND keyboard-mode HID encoders.
Plug in controllers and run to see what fires.
"""
import pygame
import sys
from collections import deque

pygame.init()
W, H = 1280, 720
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Controller Test - press ESC to quit")
clock = pygame.time.Clock()

font_big = pygame.font.SysFont("monospace", 28, bold=True)
font_med = pygame.font.SysFont("monospace", 20)
font_sm  = pygame.font.SysFont("monospace", 15)

BLACK  = (0,   0,   0)
WHITE  = (255, 255, 255)
GRAY   = (60,  60,  60)
GREEN  = (0,   220, 80)
RED    = (220, 50,  50)
YELLOW = (220, 220, 0)
CYAN   = (0,   200, 220)
DIM    = (100, 100, 100)

# ---------- joystick setup ----------
pygame.joystick.init()
joysticks = []
for i in range(pygame.joystick.get_count()):
    js = pygame.joystick.Joystick(i)
    js.init()
    joysticks.append(js)

# Live state per joystick: axes, buttons, hats
js_state = {}
for js in joysticks:
    js_state[js.get_id()] = {
        "axes":    [0.0] * js.get_numaxes(),
        "buttons": [False] * js.get_numbuttons(),
        "hats":    [(0, 0)] * js.get_numhats(),
    }

# ---------- keyboard state ----------
key_state = {}   # keycode -> bool
event_log = deque(maxlen=20)
log_file = open("/home/hsad/Arcade/controller_events.log", "w", buffering=1)

def log(msg):
    event_log.appendleft(msg)
    log_file.write(msg + "\n")

def draw_stick(surface, cx, cy, r, dx, dy, active):
    """Draw 8-way joystick indicator."""
    color = GRAY
    pygame.draw.circle(surface, color, (cx, cy), r, 2)
    # 8-direction tick marks
    import math
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = cx + int((r - 6) * math.cos(rad))
        y1 = cy + int((r - 6) * math.sin(rad))
        x2 = cx + int(r * math.cos(rad))
        y2 = cy + int(r * math.sin(rad))
        pygame.draw.line(surface, DIM, (x1, y1), (x2, y2), 2)
    # Dot
    dot_x = cx + int(dx * (r - 8))
    dot_y = cy - int(dy * (r - 8))
    dot_color = GREEN if active else WHITE
    pygame.draw.circle(surface, dot_color, (dot_x, dot_y), 8)

def draw_button(surface, cx, cy, r, pressed, label):
    color = RED if pressed else GRAY
    pygame.draw.circle(surface, color, (cx, cy), r)
    pygame.draw.circle(surface, WHITE, (cx, cy), r, 2)
    txt = font_sm.render(label, True, WHITE)
    surface.blit(txt, txt.get_rect(center=(cx, cy)))

running = True
while running:
    screen.fill(BLACK)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            key_state[event.key] = True
            log(f"KEY DOWN  {pygame.key.name(event.key)} (code {event.key})")

        elif event.type == pygame.KEYUP:
            key_state[event.key] = False
            log(f"KEY UP    {pygame.key.name(event.key)} (code {event.key})")

        elif event.type == pygame.JOYAXISMOTION:
            js = event.joy
            if js in js_state:
                js_state[js]["axes"][event.axis] = event.value
            log(f"JS{js} AXIS {event.axis} = {event.value:+.3f}")

        elif event.type == pygame.JOYBUTTONDOWN:
            js = event.joy
            if js in js_state:
                js_state[js]["buttons"][event.button] = True
            log(f"JS{js} BTN  {event.button} DOWN")

        elif event.type == pygame.JOYBUTTONUP:
            js = event.joy
            if js in js_state:
                js_state[js]["buttons"][event.button] = False
            log(f"JS{js} BTN  {event.button} UP")

        elif event.type == pygame.JOYHATMOTION:
            js = event.joy
            if js in js_state:
                js_state[js]["hats"][event.hat] = event.value
            log(f"JS{js} HAT  {event.hat} = {event.value}")

        elif event.type == pygame.JOYDEVICEADDED:
            js = pygame.joystick.Joystick(event.device_index)
            js.init()
            joysticks.append(js)
            js_state[js.get_id()] = {
                "axes":    [0.0] * js.get_numaxes(),
                "buttons": [False] * js.get_numbuttons(),
                "hats":    [(0, 0)] * js.get_numhats(),
            }
            log(f"JOYSTICK ADDED: {js.get_name()}")

        elif event.type == pygame.JOYDEVICEREMOVED:
            log(f"JOYSTICK REMOVED: id {event.instance_id}")

    # ---------- draw joystick panels ----------
    js_count = len(joysticks)
    if js_count == 0:
        msg = font_big.render("No joysticks detected — plug in controllers", True, YELLOW)
        screen.blit(msg, msg.get_rect(center=(W // 2, 180)))
        msg2 = font_med.render("(keyboard HID events will still show in the log below)", True, DIM)
        screen.blit(msg2, msg2.get_rect(center=(W // 2, 220)))
    else:
        panel_w = W // min(js_count, 4)
        for i, js in enumerate(joysticks[:4]):
            st = js_state.get(js.get_id(), {})
            px = i * panel_w
            # Panel border
            pygame.draw.rect(screen, GRAY, (px, 0, panel_w, 380), 1)
            # Name
            name = js.get_name()[:18]
            label = font_sm.render(f"JS{i}: {name}", True, CYAN)
            screen.blit(label, (px + 6, 6))

            axes = st.get("axes", [])
            hats = st.get("hats", [])
            buttons = st.get("buttons", [])

            # Stick: prefer hat, fall back to axes 0+1
            cx, cy = px + panel_w // 2, 160
            if hats:
                dx, dy = hats[0]
            elif len(axes) >= 2:
                dx, dy = axes[0], axes[1]
            else:
                dx, dy = 0, 0
            active = (dx != 0 or dy != 0)
            draw_stick(screen, cx, cy, 60, dx, dy, active)

            # Axes list
            for ai, val in enumerate(axes[:6]):
                bar_x = px + 10
                bar_y = 240 + ai * 18
                pygame.draw.rect(screen, GRAY, (bar_x, bar_y, 120, 12))
                filled = int((val + 1) / 2 * 120)
                pygame.draw.rect(screen, GREEN, (bar_x, bar_y, filled, 12))
                atxt = font_sm.render(f"A{ai}:{val:+.2f}", True, WHITE)
                screen.blit(atxt, (bar_x + 126, bar_y - 2))

            # Buttons
            for bi, pressed in enumerate(buttons[:8]):
                bx = px + 20 + (bi % 4) * 50
                by = 340 + (bi // 4) * 40
                draw_button(screen, bx, by, 16, pressed, str(bi))

    # ---------- keyboard HID section ----------
    y_kbd = 390
    pygame.draw.line(screen, GRAY, (0, y_kbd - 5), (W, y_kbd - 5), 1)
    hdr = font_med.render("Keyboard / HID keys held:", True, CYAN)
    screen.blit(hdr, (10, y_kbd))
    held = [pygame.key.name(k) for k, v in key_state.items() if v]
    held_txt = font_med.render("  ".join(held) if held else "(none)", True, GREEN if held else DIM)
    screen.blit(held_txt, (10, y_kbd + 26))

    # ---------- event log ----------
    y_log = 440
    pygame.draw.line(screen, GRAY, (0, y_log - 5), (W, y_log - 5), 1)
    log_hdr = font_med.render("Event log:", True, CYAN)
    screen.blit(log_hdr, (10, y_log))
    for i, entry in enumerate(event_log):
        col = WHITE if i == 0 else DIM
        t = font_sm.render(entry, True, col)
        screen.blit(t, (10, y_log + 22 + i * 16))

    # ---------- status bar ----------
    status = font_sm.render(
        f"Joysticks: {js_count}   ESC=quit", True, DIM
    )
    screen.blit(status, (W - status.get_width() - 10, H - 20))

    pygame.display.flip()
    clock.tick(60)

log_file.close()
pygame.quit()
sys.exit()
