import sys
import fcntl
import termios
import struct
import os

# ── Colors ────────────────────────────────────────────────────────────────────
C_RESET   = "\x1b[0m"
C_CREAM   = "\x1b[38;2;240;235;220m"
C_SEPIA   = "\x1b[38;2;190;185;170m"
C_DIM     = "\x1b[38;2;90;85;75m"
C_ACCENT  = "\x1b[38;2;160;150;120m"
C_DANGER  = "\x1b[38;2;200;140;90m"
C_BG      = "\x1b[48;2;8;8;6m"
C_BOLD    = "\x1b[1m"

# ── Logo ──────────────────────────────────────────────────────────────────────
KHI_LOGO = [
    "  ░░▒▒▓▓████████████████████  ██  ██  ██  ██  ██████████████████████▓▓▒▒░░  ",
    "  ░░▒▒▓▓████████████████████    ████      ██  ██████████████████████▓▓▒▒░░  ",
    "  ░░▒▒▓▓████████████████████  ██  ██  ██  ██  ██████████████████████▓▓▒▒░░  ",
]
SUBTEXT_1 = "                           Bearnos Game Station"
SUBTEXT_2 = "                                  1993 \u2122"

# ── Block font (5×5 glyphs, scaled up at render time) ─────────────────────────
BLOCK_FONT: dict[str, list[str]] = {
    'A': ["░███░","█░░░█","█████","█░░░█","█░░░█"],
    'B': ["████░","█░░░█","████░","█░░░█","████░"],
    'C': ["░████","█░░░░","█░░░░","█░░░░","░████"],
    'D': ["████░","█░░░█","█░░░█","█░░░█","████░"],
    'E': ["█████","█░░░░","████░","█░░░░","█████"],
    'F': ["█████","█░░░░","████░","█░░░░","█░░░░"],
    'G': ["░████","█░░░░","█░███","█░░░█","░████"],
    'H': ["█░░░█","█░░░█","█████","█░░░█","█░░░█"],
    'I': ["░███░","░░█░░","░░█░░","░░█░░","░███░"],
    'J': ["░░░░█","░░░░█","░░░░█","█░░░█","░███░"],
    'K': ["█░░░█","█░░█░","████░","█░░█░","█░░░█"],
    'L': ["█░░░░","█░░░░","█░░░░","█░░░░","█████"],
    'M': ["█░░░█","██░██","█░█░█","█░░░█","█░░░█"],
    'N': ["█░░░█","██░░█","█░█░█","█░░██","█░░░█"],
    'O': ["░███░","█░░░█","█░░░█","█░░░█","░███░"],
    'P': ["████░","█░░░█","████░","█░░░░","█░░░░"],
    'Q': ["░███░","█░░░█","█░█░█","█░░██","░████"],
    'R': ["████░","█░░░█","████░","█░░█░","█░░░█"],
    'S': ["░████","█░░░░","░███░","░░░░█","████░"],
    'T': ["█████","░░█░░","░░█░░","░░█░░","░░█░░"],
    'U': ["█░░░█","█░░░█","█░░░█","█░░░█","░███░"],
    'V': ["█░░░█","█░░░█","█░░░█","░█░█░","░░█░░"],
    'W': ["█░░░█","█░░░█","█░█░█","██░██","█░░░█"],
    'X': ["█░░░█","░█░█░","░░█░░","░█░█░","█░░░█"],
    'Y': ["█░░░█","░█░█░","░░█░░","░░█░░","░░█░░"],
    'Z': ["█████","░░░█░","░░█░░","░█░░░","█████"],
    '0': ["░███░","█░░░█","█░░░█","█░░░█","░███░"],
    '1': ["░░█░░","░██░░","░░█░░","░░█░░","░███░"],
    '2': ["░███░","█░░░█","░░██░","░█░░░","█████"],
    '3': ["████░","░░░░█","░███░","░░░░█","████░"],
    '4': ["█░░░█","█░░░█","█████","░░░░█","░░░░█"],
    '5': ["█████","█░░░░","████░","░░░░█","████░"],
    '6': ["░████","█░░░░","████░","█░░░█","░███░"],
    '7': ["█████","░░░░█","░░░█░","░░█░░","░░█░░"],
    '8': ["░███░","█░░░█","░███░","█░░░█","░███░"],
    '9': ["░███░","█░░░█","░████","░░░░█","░███░"],
    ' ': ["░░░░░","░░░░░","░░░░░","░░░░░","░░░░░"],
    '-': ["░░░░░","░░░░░","█████","░░░░░","░░░░░"],
    ':': ["░░░░░","░░█░░","░░░░░","░░█░░","░░░░░"],
    '.': ["░░░░░","░░░░░","░░░░░","░░░░░","░░█░░"],
    '!': ["░░█░░","░░█░░","░░█░░","░░░░░","░░█░░"],
}

def get_terminal_size() -> tuple[int, int]:
    try:
        buf = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b'\x00' * 8)
        rows, cols = struct.unpack('hh', buf[:4])
        if rows > 0 and cols > 0:
            return rows, cols
    except Exception:
        pass
    return 24, 80

_saved_termios = None

def term_enter_alt_screen():
    global _saved_termios
    try:
        fd = sys.stdin.fileno()
        _saved_termios = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[3] &= ~(termios.ECHO | termios.ICANON)
        termios.tcsetattr(fd, termios.TCSADRAIN, new)
    except Exception:
        pass
    sys.stdout.write("\x1b[?1049h\x1b[?25l" + C_BG)
    sys.stdout.flush()

def term_leave_alt_screen():
    global _saved_termios
    if _saved_termios is not None:
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _saved_termios)
        except Exception:
            pass
    sys.stdout.write("\x1b[?1049l\x1b[?25h" + C_RESET)
    sys.stdout.flush()

def _move(row: int, col: int) -> str:
    return f"\x1b[{row};{col}H"

def _star_char(row: int, col: int) -> str:
    h = (row * 7919 + col * 3571) % 100
    if h >= 4:
        return " "
    return ['.', '*', '+', '·'][h % 4]

def _center(text: str, width: int) -> str:
    text_len = len(text)
    if text_len >= width:
        return text[:width]
    pad = (width - text_len) // 2
    return " " * pad + text

def _card_box(rows: int, cols: int) -> tuple[int, int, int, int]:
    """Return (box_row, box_col, box_h, box_w) for the TextCard."""
    content_start = 7
    content_end   = rows - 2
    total_content = max(1, content_end - content_start + 1)
    box_h  = max(5,  int(total_content * 0.70))
    box_w  = max(40, int(cols * 0.70))
    box_row = content_end - box_h + 1
    box_col = (cols - box_w) // 2 + 1
    return box_row, box_col, box_h, box_w

def render(app) -> None:
    rows, cols = app.term_rows, app.term_cols
    buf = []

    buf.append(C_BG + "\x1b[2J")

    # Star field (rows 7 onward)
    buf.append(C_DIM)
    for r in range(7, rows + 1):
        for c in range(1, cols + 1):
            ch = _star_char(r, c)
            if ch != " ":
                buf.append(_move(r, c) + ch)

    # Logo (rows 1-3)
    buf.append(C_CREAM)
    for i, line in enumerate(KHI_LOGO):
        buf.append(_move(i + 1, 1) + line[:cols])

    # Subtext (rows 4-5)
    buf.append(_move(4, 1) + SUBTEXT_1[:cols])
    buf.append(_move(5, 1) + SUBTEXT_2[:cols])

    games = app.game_list()
    count = len(games)

    if count == 0:
        mid = rows // 2
        buf.append(C_DANGER + _move(mid, 1) + _center("NO GAMES INSTALLED", cols))
        buf.append(C_DIM   + _move(mid + 1, 1) + _center("drop a game folder into ~/Arcade/games/", cols))
    else:
        game = games[app.selected]
        box_row, box_col, box_h, box_w = _card_box(rows, cols)

        # Nav / metadata sits above the card with a comfortable margin
        info_row  = box_row - 1
        desc_row  = box_row - 2
        title_row = box_row - 4
        title_row = max(7, title_row)
        desc_row  = max(title_row + 1, desc_row)
        info_row  = max(desc_row + 1, info_row)

        # Title nav
        prev_title = games[(app.selected - 1) % count].title if count > 1 else ""
        next_title = games[(app.selected + 1) % count].title if count > 1 else ""
        nav_left   = f"◄ {prev_title}" if count > 1 else ""
        nav_right  = f"{next_title} ►" if count > 1 else ""
        cur_title  = f"[ {game.title} ]"

        buf.append(C_DIM   + _move(title_row, 2) + nav_left[:cols // 3])
        buf.append(C_CREAM + _move(title_row, 1) + _center(cur_title, cols))
        if nav_right:
            buf.append(C_DIM + _move(title_row, cols - len(nav_right) - 1) + nav_right)

        # Description
        buf.append(C_SEPIA + _move(desc_row, 1) + _center(game.description, cols))

        # Players / author
        info = f"{game.players} players · by {game.author}" if game.author else f"{game.players} players"
        buf.append(C_DIM + _move(info_row, 1) + _center(info, cols))

        # TextCard
        _render_textcard(buf, game, box_col, box_row, box_w, box_h)

    # Footer separator
    buf.append(C_ACCENT + _move(rows - 1, 1) + ("═" * cols)[:cols])

    # Footer hint
    hint = "◄ LEFT/RIGHT TO BROWSE ►    [ ATTACK ] or [ JUMP ] TO PLAY"
    buf.append(C_SEPIA + _move(rows, 1) + _center(hint, cols))

    sys.stdout.write("".join(buf))
    sys.stdout.flush()

def _render_textcard(buf: list, game, box_col: int, box_row: int,
                     box_w: int, box_h: int) -> None:
    buf.append(C_CREAM)
    if game.textcard:
        lines = game.textcard.splitlines()
        # Vertically center within box_h
        pad_top = max(0, (box_h - len(lines)) // 2)
        for i in range(box_h):
            li = i - pad_top
            if 0 <= li < len(lines):
                raw  = lines[li]
                # Horizontally center each line within box_w
                line = _center(raw, box_w) if len(raw) < box_w else raw[:box_w]
            else:
                line = ""
            buf.append(_move(box_row + i, box_col) + line)
    else:
        _render_block_title(buf, game.title, box_col, box_row, box_w, box_h)

def _render_block_title(buf: list, title: str, box_col: int, box_row: int,
                        box_w: int, box_h: int) -> None:
    # Scale glyph width to fill roughly 60% of box_w.
    # Each glyph cell is 5 pixels wide; we expand each pixel to `scale` chars.
    # Glyph width = 5*scale, gap = scale, total per char = 6*scale.
    chars = [c for c in title.upper() if c in BLOCK_FONT]
    if not chars:
        return

    # Find the largest scale where all chars fit within box_w
    scale = 1
    while True:
        glyph_w  = 5 * (scale + 1)
        gap_w    = (scale + 1)
        total_w  = len(chars) * glyph_w + (len(chars) - 1) * gap_w
        if total_w > int(box_w * 0.90):
            break
        scale += 1
    scale = max(1, scale)

    glyph_w = 5 * scale
    gap_w   = scale
    total_w = len(chars) * glyph_w + (len(chars) - 1) * gap_w
    glyph_h = 5 * scale  # each pixel row repeated `scale` times

    left_pad = max(0, (box_w - total_w) // 2)
    top_pad  = max(0, (box_h - glyph_h) // 2)

    for row_idx in range(5):
        # Build the pixel row string (each pixel → `scale` chars)
        pixel_row = ""
        for ci, ch in enumerate(chars):
            for pixel in BLOCK_FONT[ch][row_idx]:
                pixel_row += ("█" if pixel == "█" else " ") * scale
            if ci < len(chars) - 1:
                pixel_row += " " * gap_w

        # Repeat the row `scale` times vertically
        for rep in range(scale):
            r = box_row + top_pad + row_idx * scale + rep
            buf.append(_move(r, box_col + left_pad) + pixel_row[:box_w])

def render_screensaver() -> None:
    sys.stdout.write("\x1b[48;2;0;0;0m\x1b[2J")
    sys.stdout.flush()

def render_launching(app) -> None:
    rows, cols = app.term_rows, app.term_cols
    games = app.game_list()
    title = games[app.selected].title if games else "?"
    mid = rows // 2
    buf = [C_BG + "\x1b[2J", C_CREAM + C_BOLD]
    for r in range(mid - 1, mid + 2):
        buf.append(_move(r, 1) + " " * cols)
    msg = f"LAUNCHING  {title} ..."
    buf.append(_move(mid, 1) + _center(msg, cols))
    sys.stdout.write("".join(buf))
    sys.stdout.flush()
