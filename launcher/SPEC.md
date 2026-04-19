# Arcade Launcher — Full Spec

## Purpose
Replace ES-DE with a custom Odin-based ANSI TUI launcher.
Runs directly on Linux TTY (no X11). Designed for a 4-player arcade cabinet
with HID keyboard encoder controllers. No keyboard assumed to be present.

---

## Hardware / Platform
- Raspberry Pi 4B 2GB, aarch64
- OS: Debian GNU/Linux 13 (trixie)
- `/boot/firmware/config.txt` has `dtoverlay=vc4-kms-v3d` (full KMS, GPU available)
- 4 arcade players, each with 6 inputs: UP DOWN LEFT RIGHT ATTACK JUMP
- Controllers present as HID keyboard encoders (USB keyboard devices)
- All 4 players' inputs appear on `/dev/input/event*` devices

---

## Tech Stack
- **Language**: Odin (nightly at `~/odin-linux-arm64-nightly+2026-04-02/odin`)
- **Input**: Linux evdev — read raw `input_event` structs from `/dev/input/event*`
- **Rendering**: ANSI escape codes to stdout (no SDL, no graphics lib for launcher)
- **Games**: each game's `launch.sh` may use SDL2 + `SDL_VIDEODRIVER=kmsdrm` for
  direct GPU rendering (no X required). Future games can use `vendor:raylib`.
- **No X11**: launcher runs on TTY, X is not used at all

---

## Boot Flow
```
Pi boots → getty autologin on tty1 → ~/.bash_profile launches ~/Arcade/launcher
```
Add to `~/.bash_profile`:
```bash
if [ "$(tty)" = "/dev/tty1" ]; then
    exec ~/Arcade/launcher
fi
```
The old `.xinitrc` / ES-DE squashfs path is obsolete once launcher is running.

---

## File Layout
```
~/Arcade/
  launcher/           ← Odin source + compiled binary (this project)
    SPEC.md
    main.odin
    input.odin
    games.odin
    render.odin
    launch.odin
    build.sh
  launcher             ← compiled binary (output of build.sh)
  controllers.json     ← canonical controller mappings (read-only at runtime)
  controllers.json.bak ← backup
  orbital_breaker.py   ← existing game (pygame)
  calibrate.py         ← controller calibration tool (hidden, combo-unlocked)
  controller_test.py   ← controller debug tool
  ROMs/                ← legacy ES-DE ROMs (kept, not used by new launcher)
  ES-DE/               ← legacy ES-DE data dir (kept for reference)
  ES-DE-arm64.AppImage ← legacy
  squashfs-root/       ← legacy ES-DE extracted AppImage
  AppDir/              ← legacy

~/games/               ← all launcher games live here
  orbital-breaker/
    launch.sh          ← required: shell script to run the game
    meta.json          ← required: game metadata
    TextCard.txt       ← optional: hand-crafted ASCII art (40×7 max)
```

---

## Game Format
Each game is a subdirectory of `~/games/` containing:

**`meta.json`** (required):
```json
{
  "title": "Orbital Breaker",
  "description": "Laser satellite brick-breaker set in space.",
  "players": "1-4",
  "author": "hsad",
  "added": "2026-04-18"
}
```

**`launch.sh`** (required, must be executable):
```bash
#!/bin/bash
SDL_VIDEODRIVER=kmsdrm MESA_GL_VERSION_OVERRIDE=3.3 \
  MESA_GLSL_VERSION_OVERRIDE=330 python3 /home/hsad/Arcade/orbital_breaker.py
```

**`TextCard.txt`** (optional): hand-crafted ASCII art for the title card slot.
Max 40 chars wide × 7 lines tall. Rendered in cream. If absent, the block-font
renderer generates one from the game title automatically.

Games without both `launch.sh` and `meta.json` are ignored by the scanner.

---

## Controllers
**Canonical path**: `~/Arcade/controllers.json`

Format (SDL keycodes, all 4 players, `type: "key"` only — HID encoders):
```json
{
  "players": [
    { "player": 1, "inputs": {
        "UP":     {"type":"key","key":1073741906,"name":"up"},
        "DOWN":   {"type":"key","key":1073741905,"name":"down"},
        "LEFT":   {"type":"key","key":1073741904,"name":"left"},
        "RIGHT":  {"type":"key","key":1073741903,"name":"right"},
        "ATTACK": {"type":"key","key":1073742050,"name":"left alt"},
        "JUMP":   {"type":"key","key":1073742048,"name":"left ctrl"}
    }},
    ...
  ],
  "diagonals": "combinations"
}
```

The launcher reads controllers.json and **never writes to it**.
`calibrate.py` writes it; it is the only writer.

**SDL keycode → Linux evdev keycode mapping** (for input.odin):
```
1073741906 → 103  UP
1073741905 → 108  DOWN
1073741904 → 105  LEFT
1073741903 → 106  RIGHT
1073742050 → 56   LALT
1073742048 → 29   LCTRL
1073742053 → 54   RSHIFT
1073742052 → 97   RCTRL
97→30 98→48 99→46 100→32 101→18 102→33 103→34
104→35 105→23 106→36 107→37 108→38 109→50 110→49
111→24 112→25 113→16 114→19 115→31 116→20 117→22
118→47 119→17 120→45 121→21 122→44
```

---

## Launcher Behaviour

### States
```
MENU  →(ATTACK or JUMP)→  LAUNCHING  →(game exits)→  MENU
```

### Navigation (MENU state)
- **LEFT / RIGHT** (any player): cycle through games
- **ATTACK or JUMP** (any player): launch selected game
- Game list rescanned every **5 seconds** (poll, no inotify needed)
- If current selection disappears on rescan: fall back to index 0

### Calibration (hidden)
- `calibrate.py` is NOT in `~/games/`; it is hidden by default
- Secret combo (only checked when **viewing the first real game, index 0**):
  ```
  P1-JUMP  P2-JUMP  P3-JUMP  P4-JUMP
  P4-ATTACK  P3-ATTACK  P2-ATTACK  P1-ATTACK
  ```
- On success: calibrate appears as a temporary slot **at index 0**
  (real games shift to 1+). Visible for the session only (not persisted).
- Any wrong ATTACK/JUMP input while combo is in progress resets combo to 0.
- LEFT/RIGHT navigation inputs are ignored for combo tracking.

---

## Rendering

### Terminal Setup
- Enter alternate screen: `\x1b[?1049h`
- Hide cursor: `\x1b[?25l`
- Black background: `\x1b[48;2;0;0;0m`
- On exit / before launching game: restore with `\x1b[?1049l` + `\x1b[?25h`
- Query terminal size via `ioctl(STDOUT_FILENO, TIOCGWINSZ)` at startup
  (TIOCGWINSZ = 0x5413 on Linux ARM64); fallback to 80×24

### Color Palette
Aesthetic: paper white / sepia — aged corporate terminal, Xerox circa 1984.

```
Logo / bright:  cream   \x1b[38;2;240;235;220m
Title:          cream   \x1b[38;2;240;235;220m
Description:    sepia   \x1b[38;2;190;185;170m
Dim / prev:     dark    \x1b[38;2;90;85;75m
Accent / sep:   mid     \x1b[38;2;160;150;120m
Danger:         warm    \x1b[38;2;200;140;90m  (no pure red — keep sepia warmth)
Background:     black   \x1b[48;2;8;8;6m        (near-black, faint warm tint)
```

Player colors are not used in the launcher — games manage their own styling.

### KHI Logo (top of screen, every render)
78 chars wide × 3 rows tall. Structure:
```
[2 margin][8 dither][20 solid][20 KHI][20 solid][8 dither][2 margin]
```
Dither left:  `  ░░▒▒▓▓`   Dither right: `▓▓▒▒░░  `

KHI letter section (20 chars wide), doubled-width cells:
- K: 6 wide. Row0,2: `  ██  ` / Row1: `    ██`
- gap: 2 wide. All rows: `██`
- H: 6 wide. Row0,2: `  ██  ` / Row1: `      `
- I: 6 wide. All rows: `██  ██`  (no gap before I — H-I gap removed)

```
  ░░▒▒▓▓████████████████████  ██  ██  ██  ██  ██████████████████████▓▓▒▒░░  
  ░░▒▒▓▓████████████████████    ████      ██  ██████████████████████▓▓▒▒░░  
  ░░▒▒▓▓████████████████████  ██  ██  ██  ██  ██████████████████████▓▓▒▒░░  
                           Bearnos Game Station
                                  1993 ™
```
(27 spaces before "Bearnos", 34 spaces before "1993 ™")

Logo rendered in cream. Spaces within the bar show near-black background = letter cutouts.

### Star Field (behind everything except UI chrome)
Deterministic scatter using `(row * 7919 + col * 3571) % 100 < 4`.
Characters: `.` `*` `+` `·` cycling on the hash remainder.
Rendered in dim/dark sepia. Redrawn on each render call (static pattern, no animation needed).

### Main Menu Layout
```
Row 1:    KHI logo bar (row 1 of 3)
Row 2:    KHI logo bar (row 2 of 3)
Row 3:    KHI logo bar (row 3 of 3)
Row 4:    "Bearnos Game Station"
Row 5:    "1993 ™"
Row 6:    (blank)
Rows 7..: star field background
Row mid-4: ◄ PREV TITLE (dim, left)    [ CURRENT TITLE ] (cream, centered)    NEXT TITLE ► (dim, right)
Row mid-2: description (sepia, centered)
Row mid-1: players · by author (dim, centered)
Row mid:   TextCard box (40×7, centered, accent color)
           — see TextCard Rendering section below
Row last-1: ═══ separator (accent)
Row last:   "◄ LEFT/RIGHT TO BROWSE ►    [ ATTACK ] or [ JUMP ] TO PLAY" (sepia)
```

### TextCard Rendering
The card box is **dynamic** — sized from terminal dimensions by `_card_box()` in `renderer.py`:

```python
content_start = 7
content_end   = rows - 2
total_content = max(1, content_end - content_start + 1)
box_h  = max(5,  int(total_content * 0.70))   # 70% of usable rows,  min 5
box_w  = max(40, int(cols * 0.70))             # 70% of terminal cols, min 40
box_row = content_end - box_h + 1
box_col = (cols - box_w) // 2 + 1
```

**At 186×51 (typical maximised terminal on 1920×1080): box is 130 wide × 30 tall.**
Design TextCard.txt to use that space — 40×5 is only the fallback floor for tiny terminals.

Rendering behaviour (from `_render_textcard`):
- Lines are vertically centered within `box_h`
- Each line is horizontally centered within `box_w`
- Lines longer than `box_w` are truncated (not wrapped)
- Rendered in cream (`C_CREAM`)

**Priority:**
1. If `~/games/<slug>/TextCard.txt` exists: render as above.
2. Fallback: render the game title using the built-in **5×5 block font** (see below), auto-scaled
   so glyphs fill ≤90% of `box_w`, each pixel expanded to `scale` chars in both axes.

**Block font** — 5-wide × 5-tall glyphs using `█` and `░` (defined in `renderer.py`):
- Characters: A–Z, 0–9, space, `-` `:` `.` `!`
- `░` pixels render as spaces in output
- Scale factor chosen automatically; centered in box

**Calibrate slot** uses a fixed built-in TextCard (hardcoded string in `games.py`).

### LAUNCHING overlay
Full-width darkened rows around screen center.
`LAUNCHING  <TITLE> ...` in cream bold, centered.
Shown briefly before exec, terminal restored before child process starts.

### No Games message
```
NO GAMES INSTALLED       (danger/warm, centered)
drop a game folder into ~/games/    (dim, centered)
```

---

## Source File Responsibilities

### `main.odin`
- `App` struct: state, games list, selected index, calibrate_unlocked, combo_idx, last_refresh, devs, ctrl, term dimensions
- `main`: init, main loop (poll → handle → render), 5s rescan
- `handle_event`: state machine dispatch
- `game_count`, `get_game_at`, `get_selected_game` helpers

### `input.odin`
- `Action` enum: NONE LEFT RIGHT UP DOWN ATTACK JUMP
- `Action_Event` struct: player int, action Action
- `Controller_Map`: `map[u16][2]int` (evdev_code → {player, action})
- `sdl_to_evdev`: SDL keycode → Linux evdev keycode lookup table
- `load_controllers(path)`: parse controllers.json via `json.parse`, build Controller_Map
- `open_input_devices`: scan `/dev/input/event*`, open all with O_RDONLY|O_NONBLOCK|O_CLOEXEC
- `poll_input(devs, ctrl, timeout_ms)`: linux.poll → read Evdev_Event → map to Action_Event
- `Evdev_Event` struct (24 bytes): tv_sec i64, tv_usec i64, type u16, code u16, value i32
- `COMBO` constant: 8-step sequence for calibration unlock
- `advance_combo(idx, ev)`: advance or reset combo, return true when complete

### `games.odin`
- `Game` struct: title, description, players, author, slug, dir, textcard (all cloned strings;
  `textcard` is empty string if `TextCard.txt` absent)
- `CALIBRATE_GAME` constant (includes hardcoded textcard art)
- `scan_games(dir)`: os.read_dir → filter for launch.sh+meta.json → parse meta → try read
  TextCard.txt → sort by title
- `refresh_games(games, dir)`: free existing, rescan
- JSON parsed via `json.parse` (returns json.Value tree), not json.unmarshal

### `render.odin`
- Terminal control: `term_enter_alt_screen`, `term_leave_alt_screen`, `get_terminal_size`
- `KHI_LOGO`: `[3]string` constants (the 3 bar rows)
- `SUBTEXT_1`, `SUBTEXT_2`: logo subtext constants
- `COLOR_*` constants for the full paper-white palette
- `render(app)`: full redraw — stars, logo, game selector, footer
- `render_textcard(game, box_col, box_row)`: render TextCard.txt verbatim or fall back to
  `render_block_title`; always fits within 40×7
- `render_block_title(title, box_col, box_row)`: 5×5 block-font renderer; centers output in box
- `BLOCK_FONT`: `map[rune][5]string` — 5-row glyph definitions for A–Z, 0–9, punctuation
- `render_launching(app)`: overlay before exec
- `render_no_games(app)`: empty state

### `launch.odin`
- `launch_game(app)`:
  1. `term_leave_alt_screen()`
  2. `linux.fork()`
  3. Child: build argv (`/bin/bash`, `launch.sh`), build minimal envp
     (PATH, HOME, USER, SDL_VIDEODRIVER=kmsdrm, MESA vars), `linux.execve`
  4. Parent: `linux.wait4(pid, nil, {}, nil)`
  5. `term_enter_alt_screen()`
- Calibrate game special-cases to `~/Arcade/ROMs/ports/calibrate-controllers.sh`

---

## Build
```bash
# build.sh
#!/bin/bash
set -e
ODIN=~/odin-linux-arm64-nightly+2026-04-02/odin
cd ~/Arcade/launcher
$ODIN build . -out:../launcher -target:linux_arm64
echo "Built: ~/Arcade/launcher"
```

---

## Existing Games to Wire Up
`~/games/orbital-breaker/` needs to be created with:
- `meta.json`: title="Orbital Breaker", description="Laser satellite brick-breaker set in space.", players="1-4", author="hsad", added="2026-04-18"
- `launch.sh`: `SDL_VIDEODRIVER=kmsdrm MESA_GL_VERSION_OVERRIDE=3.3 MESA_GLSL_VERSION_OVERRIDE=330 python3 /home/hsad/Arcade/orbital_breaker.py`

---

## Remote Dev / Viewing the Screen

**TUI launcher (tmux):** Run the launcher inside tmux for a true live view over SSH.
```bash
# ~/.bash_profile
if [ "$(tty)" = "/dev/tty1" ]; then
    exec tmux new-session -s arcade ~/Arcade/launcher
fi
```
Then `tmux attach -t arcade` from any SSH session. Real-time, full color.
When a game launches it takes over the framebuffer; tmux goes blank until the game exits.

**GPU-rendered games (kmsvnc):** For SDL/raylib games rendering via kmsdrm there is
no TTY to attach to. `kmsvnc` is a VNC server that hooks into KMS/DRM and streams
the display live without X. Not in apt — needs to be compiled from source. Overkill
for now but the right tool when game dev starts.

**Quick text snapshot:** `cat /dev/vcs1` dumps the raw text of tty1 right now. No
color, but useful for a sanity check without any setup.

---

## Out of Scope (future)
- Raylib games (vendor:raylib available in Odin nightly, SDL_VIDEODRIVER=kmsdrm works)
- Preview images / per-game art
- High score previews
- Attract mode
- Recently played sort
- Scrolling marquee for long descriptions
