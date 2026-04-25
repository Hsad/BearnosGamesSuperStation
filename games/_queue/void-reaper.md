---
title: "Void Reaper"
slug: void-reaper
players: 1-4
genre: Top-down shooter
created: 2026-04-23T02:57:25
status: failed
---

## Game Concept

Four pilots trapped in a derelict asteroid field fight to the death. Ships fire a single forward laser and can snap 180° to punish anyone on their tail. The galaxy is cold, silent, and unforgiving — only kill count survives the verdict when the clock hits zero.

## Core Mechanic

Each ship moves in 8 directions with the joystick and fires a forward-facing laser with ATTACK. JUMP instantly flips the ship 180°, reversing thrust direction and redirecting the laser — a high-skill reversal tool for escaping pursuit or punishing an attacker. Kills score 1 point; dying deducts 1 point. Match lasts 2 minutes; highest score wins.

## Visual Style

Dark space void background with dim star parallax. Ships are sharp geometric silhouettes in distinct muted colors per player (blood red, sickly green, bone white, rust orange). Asteroids are jagged, dark grey, slightly luminous at edges. Laser beams are thin, bright, and leave a brief afterglow trail. Explosions are violent white flashes that fade to drifting debris. HUD is minimal — kill counts and a countdown timer in cold mono font, kept 30px from the top edge.

## Win Condition

Most kills (kills minus deaths) when the 2-minute timer expires. Ties broken by fewer deaths. Scores displayed on a grim post-match scoreboard before returning to attract screen.

## Pacing

Medium arcade pace. Ships are agile but not twitchy. Lasers travel fast with moderate range. The 180° flip has no cooldown but briefly halts forward motion, creating a risk-reward rhythm. Asteroids provide natural cover and choke points. Shield pickups absorb one hit; health packs restore half a life segment. Pickups spawn on a 15-second cycle at fixed asteroid-adjacent positions.

## Tone

Grim and dark. No music during play — only sparse sound effects: laser hiss, metal-crack impacts, hollow explosion thuds, and a low ambient drone. Post-match scoreboard shows each pilot's fate with sparse skull iconography.

## Notes

- Ships have 3 HP; losing all HP triggers a 3-second respawn with brief invincibility frames on re-entry.
- Asteroids are static collidable obstacles that block laser fire and ship movement — good for ambushes.
- Shield pickup displays as a faint hex aura around the ship; health pack shows as a pulsing red cross.
- The 180° flip (JUMP) reverses facing and laser direction instantly but applies a half-second drag to velocity — skilled players exploit momentum drift.
- Player join screen: press ATTACK to lock in your ship before match start; all joined players launch simultaneously.
- Quit any screen by holding ATTACK + JUMP simultaneously (per cabinet convention).
- Attract screen cycles through ship silhouettes and the title 'VOID REAPER' in jagged block letters.

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- Fullscreen 1920x1080
- Use event-based Input class pattern from chopper_chase.py — do not use pygame.key.get_pressed() with range loop
- Keep all critical UI elements at least 30px from top of screen
- Controller mappings must follow controllers.json as documented in CLAUDE.md
