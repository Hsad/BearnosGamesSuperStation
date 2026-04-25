---
title: "Crypt Keeper"
slug: crypt-keeper
players: 1-4
genre: Tactical dungeon crawler, survival
created: 2026-04-25T23:39:32
status: failed
---

## Game Concept

A spooky pixel-art dungeon where 1–4 players survive endless waves of enemies in a single arena or connected rooms. Use tactical movement and two distinct attack types to fend off increasingly difficult hordes. Score is determined by waves survived and enemies defeated.

## Core Mechanic

JUMP and ATTACK buttons trigger different combat actions (e.g., JUMP dodges or area-clear; ATTACK is directional single-target). Navigate an 8-way joystick to position tactically. Waves spawn enemies in patterns; survival and high score are the only goals.

## Visual Style

Pixel art retro, top-down view. Spooky dungeon theme with creepy enemy designs, dim lighting, eerie atmosphere. Readable for all 4 players simultaneously.

## Win Condition

No win state—survival as long as possible. Score tracks waves survived, enemies killed, time elapsed. Game ends when player(s) die.

## Pacing

Consistent difficulty throughout (no ramping). Enemies spawn in steady, predictable waves. Tactical (not frantic) so players can coordinate positioning and attacks.

## Tone

Spooky and creepy—eerie music, dark colors, unsettling enemy designs, but gameplay is fair and skill-based, not frustrating.

## Notes

- Each player controls a separate character on screen in co-op mode
- Endless wave-based survival—no floor progression
- Both ATTACK and JUMP do different combat actions
- Supports solo play and drop-in/drop-out co-op for 2–4 players
- Tactical positioning is key—not a button-masher

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- Fullscreen 1920×1080
- Use event-based Input class pattern (no pygame.key.get_pressed() range loops)
- Keep UI 30px from top edge (bezel obstruction)
- 4-player controller support via controllers.json
