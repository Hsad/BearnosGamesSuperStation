# Arcade Project

Raspberry Pi arcade cabinet. 4 players, each with an 8-way joystick and 2 buttons
(JUMP, ATTACK). Controller mappings are in `controllers.json`.

## Adding a game

Create `games/<slug>/` containing:
- `<name>.py` — main pygame script (fullscreen 1920×1080)
- `launch.sh` — sets SDL env vars, runs the script
- `meta.json` — title, description, players, author, added date

See `games/orbital-breaker/` as a reference.

## Input

Use the event-based `Input` class pattern from `games/chopper-chase/chopper_chase.py`.
**Do not** use `pygame.key.get_pressed()` with a range loop — it silently breaks P1 and P3.
See `docs/gotchas.md` for the full explanation.

## Display

The TV is mounted in the cabinet with the top edge physically obscured by ~1 inch of bezel.
Keep important UI elements (scores, player indicators, title text) at least 30px from the
top of the screen. The bottom and sides are fully visible.

## Menu conventions

- **Join / select:** press ATTACK
- **Quit from any menu screen:** hold both buttons (ATTACK + JUMP) simultaneously

## Controller layout

- P1: arrow keys · left ctrl (JUMP) · left alt (ATTACK)
- P2: r/f/d/g · a (JUMP) · s (ATTACK)
- P3: i/j/k/l · right ctrl (JUMP) · right shift (ATTACK)
- P4: y/n/v/u · b (JUMP) · e (ATTACK)
