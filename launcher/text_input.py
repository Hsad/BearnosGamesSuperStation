#!/usr/bin/env python3
"""Reusable text-input widget — alpha cycling + morse code modes.

Alpha mode : UP/DOWN cycle A-Z + space, LEFT/RIGHT move cursor,
             LEFT at col 0 switches to morse, JUMP submits.
Morse mode : JUMP = dit (·), ATTACK = dash (—) navigate the tree;
             RIGHT accepts current letter and advances,
             LEFT accepts and retreats (at col 0 → back to alpha),
             UP held for HOLD_SUBMIT seconds submits.
"""

import time
from input_handler import Action

ALPHA_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Morse tree nodes: (letter, dit_child, dash_child)
def _n(ch, d=None, s=None):
    return (ch, d, s)

MORSE_TREE = _n(None,
    _n('E',
        _n('I', _n('S', _n('H'), _n('V')), _n('U', _n('F'))),
        _n('A', _n('R', _n('L')), _n('W', _n('P'), _n('J')))),
    _n('T',
        _n('N', _n('D', _n('B'), _n('X')), _n('K', _n('C'), _n('Y'))),
        _n('M', _n('G', _n('Z'), _n('Q')), _n('O')))
)

MODE_ALPHA = "alpha"
MODE_MORSE = "morse"

HOLD_SUBMIT = 1.5   # seconds UP must be held to submit

# ── Reference display lines ────────────────────────────────────────────────

MORSE_TREE_LINES = [
    "                    .                                              _",
    "                   /E\\                                            /T\\",
    "            .                _                        .                         _",
    "           /I\\              /A\\                      /N\\                       /M\\",
    "     .             _      .      _             .             _             .          _",
    "    /S\\           /U     /R     /W\\           /D\\           /K\\           /G\\         O",
    "  .      _      .      .      .      _      .      _      .      _      .      _",
    "  H      V      F      L      P      J      B      X      C      Y      Z      Q",
]

MORSE_LEGEND = ". = dit  JUMP button      _ = dash  ATTACK button"

MORSE_ICICLE_LINES = [
    "  A  B  C  D  E  F  G  H  I  J  K  L  M  N  O  P  Q  R  S  T  U  V  W  X  Y  Z",
    "  .  _  _  _  .  .  _  .  .  .  _  .  _  _  _  .  _  .  .  _  .  .  .  _  _  _",
    "  _  .  .  .     .  _  .  .  _  .  _  _  .  _  _  _  _  .     .  .  _  .  .  _",
    "     .  _  .     _  .  .     _  _  .        _  _  .  .  .     _  .  _  .  _  .",
    "     .  .        .     .     _     .           .  _              _     _  _  .",
]


class TextInput:

    def __init__(self, max_len: int = 48):
        self.max_len    = max_len
        self.chars      = [0]              # indices into ALPHA_CHARS
        self.cursor     = 0
        self.mode       = MODE_ALPHA
        self._mnode     = MORSE_TREE
        self._mseq: list = []              # list of '·' or '—'
        self._up_t      = 0.0             # monotonic when UP first held

    # ── public ────────────────────────────────────────────────────────────

    def text(self) -> str:
        return "".join(ALPHA_CHARS[i] for i in self.chars).rstrip()

    def morse_letter(self) -> str:
        return self._mnode[0] or ""

    def morse_dit_letter(self) -> str:
        n = self._mnode[1]
        return (n[0] or "?") if n else "·"

    def morse_dash_letter(self) -> str:
        n = self._mnode[2]
        return (n[0] or "?") if n else "—"

    def morse_seq_str(self) -> str:
        return "  ".join(self._mseq)

    def can_dit(self) -> bool:
        return self._mnode[1] is not None

    def can_dash(self) -> bool:
        return self._mnode[2] is not None

    def handle_event(self, ev) -> bool:
        """Returns True when user submits the text."""
        if self.mode == MODE_ALPHA:
            return self._alpha(ev)
        return self._morse(ev)

    def tick(self) -> bool:
        """Call every frame. Returns True when UP hold threshold is reached (morse mode only)."""
        if self.mode == MODE_MORSE and self._up_t and time.monotonic() - self._up_t >= HOLD_SUBMIT:
            self._up_t = 0.0
            self._morse_accept()
            return True
        return False

    # ── alpha ─────────────────────────────────────────────────────────────

    def _alpha(self, ev) -> bool:
        if ev.action == Action.UP:
            self.chars[self.cursor] = (self.chars[self.cursor] - 1) % len(ALPHA_CHARS)
        elif ev.action == Action.DOWN:
            self._up_t = 0.0
            self.chars[self.cursor] = (self.chars[self.cursor] + 1) % len(ALPHA_CHARS)
        elif ev.action == Action.RIGHT:
            self._up_t = 0.0
            self._advance()
        elif ev.action == Action.LEFT:
            self._up_t = 0.0
            if self.cursor > 0:
                self.cursor -= 1
            else:
                self.mode   = MODE_MORSE
                self._mnode = MORSE_TREE
                self._mseq  = []
        elif ev.action == Action.JUMP:
            self._up_t = 0.0
            return True
        return False

    # ── morse ─────────────────────────────────────────────────────────────

    def _morse(self, ev) -> bool:
        if ev.action == Action.JUMP:          # dit ·
            self._up_t = 0.0
            if self._mnode[1] is not None:
                self._mnode = self._mnode[1]
                self._mseq.append('·')
        elif ev.action == Action.ATTACK:      # dash —
            self._up_t = 0.0
            if self._mnode[2] is not None:
                self._mnode = self._mnode[2]
                self._mseq.append('—')
        elif ev.action == Action.UP:
            if not self._up_t:
                self._up_t = time.monotonic()
        elif ev.action == Action.DOWN:
            self._up_t = 0.0
        elif ev.action == Action.RIGHT:
            self._up_t = 0.0
            self._morse_accept()
            self._advance()
        elif ev.action == Action.LEFT:
            self._up_t = 0.0
            self._morse_accept()
            if self.cursor > 0:
                self.cursor -= 1
            else:
                self.mode = MODE_ALPHA
        return False

    def _morse_accept(self):
        letter = self._mnode[0]
        if letter:
            idx = ALPHA_CHARS.find(letter)
            if idx >= 0:
                self.chars[self.cursor] = idx
        self._mnode = MORSE_TREE
        self._mseq  = []

    def _advance(self):
        if self.cursor < len(self.chars) - 1:
            self.cursor += 1
        elif len(self.chars) < self.max_len:
            self.chars.append(0)
            self.cursor += 1
