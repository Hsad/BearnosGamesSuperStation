# Game Modder — Spec

Allows players to mod AI-generated games from the launcher using a guided,
multi-level selection UI. No keyboard required — all input via joystick + 2 buttons.

---

## Entry Point

**ATTACK+JUMP** (held simultaneously) on any `generated: true` game in the MENU state.

This opens the **Edit Menu** — it does not immediately enter the mod flow, giving the
player a deliberate checkpoint before doing anything costly.

Note: no collision with in-game quit — the player is in the launcher, not inside a game.

---

## Edit Menu

```
  [ Mod This Game  ]
  [ Mark as Broken ]
```

- D-pad UP/DOWN to navigate
- ATTACK = confirm selection
- JUMP = cancel, back to MENU

Extensible — future options might include: Delete Version, View Spec, Rename.

---

## Versioning Model

All versions of a game are siblings in `~/Arcade/games/`:

```
games/
  neon-vigil/          ← canonical (v1 implicitly)
  neon-vigil-v2/
  neon-vigil-v3/
```

Modding any version always produces the next version number as a child of the
**canonical slug** — no branching tree. The lineage of which version was modded
is stored in `based_on` for reference but does not affect navigation or display.

### meta.json additions

```json
{
  "generated": true,
  "parent":    "neon-vigil",       // absent on canonical
  "version":   2,                  // absent on canonical (implicitly v1)
  "based_on":  "neon-vigil-v2",    // which version was the base for this mod
  "play_count": 14,
  "status":    "ok"                // ok | broken
}
```

Any game — generated or handcrafted — can have versions via `parent`/`version`.

**play_count** is incremented in `meta.json` by `launch_game.py` after `waitpid`
returns (launcher is single-process, no atomicity issue).

**Broken versions** appear normally in the ring but with a black bar overlaid across
the card displaying the label `BROKEN` in the danger/warm color.

---

## Version Ring (launcher navigation)

When a game has versions, UP/DOWN in MENU state cycles through them in-place
(card updates; no sub-menu).

### Ring structure

Ring = `[most_played, v1, v2, v3, …, vN]`

The most-played version is anchored at position 0, followed by the full sequential
list. Most-played appears **twice** in the ring if it is not v1. Ring length is
`version_count + 1` unless most-played is v1 (then `version_count`).

Example — 5 versions, v3 is top-played. Two loops:
```
↓  v3 · v1 · v2 · v3 · v4 · v5 · v3 · v1 · v2 · v3 · v4 · v5 · v3
```

- UP = previous in ring
- DOWN = next in ring
- Ring wraps at both ends

### Footer hint

Shown only when the current game has depth > 1:
```
↕ v3  ·  ▶ 14 plays
```
Play count is shown in this ring sub-view only — not in the default left/right browse.

---

## Mod Flow State Machine

```
EDIT_MENU → MODDING_GRID → (between-change prompt) → MODDING_REVIEW → (writes spec)
                ↑_____________add more changes____________________|
```

---

## Modding Grid (recursive)

The same screen is used at every depth. The top level is the fixed category list;
all deeper levels are Claude-generated based on the game and the path drilled so far.

### Top-level categories (fixed)

```
[ Bug Fix ]      [ Gameplay ]     [ Art / Visual ]
[ New Feature ]  [ Balance ]      [ Audio / Feel ]
[ Controls ]     [ Difficulty ]   [ Rewrite      ]
```


### Grid controls

- D-pad = navigate highlighted cell
- ATTACK = **select** — adds this option to the change list, goes to between-change prompt
- JUMP = **drill down** — Claude generates 9 more specific sub-options for the
  highlighted item; the grid replaces in-place with the new options
- ATTACK+JUMP = **back one level** — returns to parent grid
  (from top level: back to Edit Menu)

### Breadcrumb

Shown above the grid at all depths:
```
Art / Visual  ›  Color & Lighting
```

### Drill-down depth

No hard limit. The player can drill as deep as they want before pressing ATTACK to
lock in a selection. Example path:

```
Art / Visual → Color & Lighting → Rain streak color → "More amber, less cyan"  [ATTACK]
```

### Claude prompt for sub-options

When JUMP is pressed, Claude receives:
- The full game spec (from the existing `_queue/<slug>.md` or the canonical game dir)
- The current breadcrumb path
- The highlighted option text
- Instruction: return exactly 9 short options as a JSON array, each ≤6 words

---

## Between-Change Prompt

Single screen shown after each ATTACK selection:

```
  Change added:
  "Art / Color — More amber in rain streaks"

  [ Add Another Change ]     [ Go to Review ]
```

- D-pad LEFT/RIGHT to move between buttons
- ATTACK = confirm highlighted button
- JUMP = shortcut for "Add Another Change"

---

## Modding Review

Scrollable checklist of all accumulated changes, with action buttons at the bottom.

```
  [✓] Art / Color   — More amber in rain streaks
  [✓] Bug Fix       — Guardian clips through barrier on wave 3
  [ ] Balance       — Bullet Time cooldown reduced to 7s

  ─────────────────────────────────────────────

  [ Add More Changes ]
  [ Confirm & Build  ]
  [ Cancel Mod       ]
```

- D-pad UP/DOWN = navigate all rows (change items + action buttons)
- ATTACK on a change row = toggle checkbox
- ATTACK on `[ Add More Changes ]` = return to Modding Grid (top level)
- ATTACK on `[ Confirm & Build ]` = write mod spec, trigger build daemon, exit to MENU
- ATTACK on `[ Cancel Mod ]` = discard all changes, return to MENU


---

## Mod Spec Output

When the player confirms, a new spec file is written to `games/_queue/<slug>-v<N>.md`
with:
- The original game's full spec as base context
- A "Proposed Changes" section listing only the checked items from the review screen
- Frontmatter: `parent`, `version`, `based_on`, `status: pending`

The build daemon picks it up and runs the same local dispatch flow as a new game,
writing output to `games/neon-vigil-v2/`.

---

## Text Input

No keyboard on the cabinet. The "Other…" category is excluded.

Morse-code-style two-button letter input (JUMP=left branch, ATTACK=right branch
through a binary letter tree) is a potential future feature but out of scope for v1.

---

## Out of Scope (v1)

- Delete a version (flag as broken is sufficient for now)
- Rename a version
- View raw spec from launcher
- Text input / freeform change description
- Mod-of-mods branching tree (all mods are children of canonical slug)
