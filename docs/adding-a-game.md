# Adding a Game to the Arcade Cabinet

Every game lives in `games/<slug>/`. The slug is lowercase with hyphens (e.g. `space-rocks`).

---

## Required files

### `meta.json`

```json
{
  "title": "My Game",
  "description": "One-line description shown in the launcher.",
  "players": "1-4",
  "author": "yourname",
  "added": "2026-04-21"
}
```

| Field | Notes |
|---|---|
| `title` | Display name. Shown in the menu nav and title card. |
| `description` | One short sentence. Shown below the title in the launcher. |
| `players` | E.g. `"1"`, `"2-4"`, `"1-4"`. Shown as metadata. |
| `author` | Your handle. |
| `added` | ISO date (`YYYY-MM-DD`). |
| `hidden` | Optional. Set `true` to hide the game from the menu while in development. |

A missing or malformed `meta.json` causes the game to be silently skipped by the launcher scanner.

---

### `launch.sh`

Must be executable (`chmod +x launch.sh`). The launcher runs this script directly via `/bin/bash`.

```bash
#!/bin/bash
cd "$(dirname "$0")"
exec python3 my_game.py
```

The launcher injects these environment variables automatically — you do **not** need to set them in `launch.sh`:

```
SDL_VIDEODRIVER=kmsdrm
MESA_GL_VERSION_OVERRIDE=3.3
MESA_GLSL_VERSION_OVERRIDE=330
```

---

## Optional files

### `TextCard.txt`

ASCII art displayed in the launcher's title card box when this game is selected. If absent, the launcher auto-generates a block-font title from `meta.json`.

**Size constraints:**
- The card box is dynamically sized from the terminal grid. On the cabinet's 1920×1080 display the usable area is typically around **120 chars wide × 30+ lines tall**.
- The SPEC says 40×7 as a safe floor for tiny terminals; design to that minimum so it looks acceptable everywhere, then use the extra space for flair on the real display.
- Lines are **vertically centered** within the box automatically.
- Long lines are **truncated** to the box width — they will not wrap.

**Style conventions** (look at existing games for reference):
- `games/chopper-chase/TextCard.txt` — large ASCII block letters with a tagline
- `games/tron/TextCard.txt` — block glyphs (█) with decorative border lines
- `games/orbital-breaker/TextCard.txt` — elaborate ASCII art (only visible at full terminal width)

The card renders in cream color on the launcher's sepia CRT background. Plain ASCII using characters from the printable range (`!`–`~`) plus Unicode box-drawing characters and block elements works well. Avoid color escapes — they are stripped.

---

## Game script conventions

### Display

- Target **1920×1080**, fullscreen.
- Keep important UI (scores, player indicators, title text) **at least 30px from the top** — the cabinet bezel obscures ~1 inch of the top edge.

### Input

Use the event-based `Input` class pattern. **Do not** use `pygame.key.get_pressed()` with a range loop — it silently breaks P1 and P3. See `docs/gotchas.md` for the full explanation and a working reference in `games/chopper-chase/chopper_chase.py`.

### Controller layout

| Player | Directions | JUMP | ATTACK |
|---|---|---|---|
| P1 | arrow keys | left ctrl | left alt |
| P2 | r/f/d/g | a | s |
| P3 | i/j/k/l | right ctrl | right shift |
| P4 | y/n/v/u | b | e |

Full SDL keycodes are in `config/controllers.json`.

### Menu conventions

- **Join / select:** ATTACK button
- **Quit from any menu screen:** hold ATTACK + JUMP simultaneously

---

## Checklist

- [ ] `games/<slug>/meta.json` — valid JSON, no `"hidden": true`
- [ ] `games/<slug>/launch.sh` — executable, runs the game
- [ ] `games/<slug>/TextCard.txt` — optional but recommended; 40 chars wide × 7 lines tall minimum safe size
- [ ] Game runs fullscreen 1920×1080
- [ ] Input uses KEYDOWN/KEYUP events, not `get_pressed()` range loop
- [ ] Important UI is ≥30px from top edge
- [ ] Quit via ATTACK + JUMP hold works from any non-gameplay screen
