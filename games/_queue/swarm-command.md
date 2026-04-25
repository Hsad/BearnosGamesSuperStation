---
title: "Swarm Command"
slug: swarm-command
players: 4
genre: co-op space shooter
created: 2026-04-25T05:42:32
status: failed
---

## Game Concept

Four players crew a starship cockpit, each controlling a different subsystem (pilot, weapons, shields, engines) to fight off waves of alien insects and defeat their mothership. Silly and chaotic with escalating difficulty.

## Core Mechanic

Role-based ship management: pilot steers using joystick and evasion, weapons officer locks and fires with ATTACK, shields engineer activates defense with JUMP, engineer manages power throttle. Coordinate to survive waves and topple the final boss.

## Visual Style

Retro-futuristic sci-fi cockpit with purple/neon accent colors, 2D vector-style alien swarms, large chunky insectoid enemies in silhouette against nebula backgrounds. Silly googly eyes and wobbly animations.

## Win Condition

Survive all enemy waves and destroy the mothership boss in the final encounter to win. Game over if the ship's health reaches zero.

## Pacing

Gentle first wave with 3-4 basic enemies; subsequent waves add count, speed, and new enemy types. Boss wave introduces a massive creature with destructible segments.

## Tone

Silly and goofy—enemies squeak when hit, ship groans with absurd alarms, players banter through chaos.

## Notes

- Joystick controls: all players use 8-way joystick for their role's specific input (navigate, aim, manage systems)
- JUMP and ATTACK mapped per role (e.g., pilot uses joystick for steering, weapons uses ATTACK to fire)
- Power-ups drop from defeated enemies: shield boost, weapon power, engine overdrive, system repair
- Simple procedural wave scaling: more enemies per wave, slight speed increase, new enemy types introduced mid-game

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- Fullscreen 1920×1080
- 4-player simultaneous input using event-based Input class pattern
- Keep UI (health, wave counter, player roles) at least 30px from top edge
