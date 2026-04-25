---
title: "Neon Vigil"
slug: neon-vigil
players: 2
genre: Top-Down Shooter / Shmup
created: 2026-04-22T01:07:16
status: failed
---

## Game Concept

A tense 2-player co-op top-down shooter set in a rain-soaked neon cyberpunk city. P1 is the 'Runner' — a slow-moving data courier who cannot fight but generates score by surviving and collecting data shards. P2 is the 'Guardian' — a fast, armed operative who must shield the Runner from endless waves of corporate assassin drones. If the Runner dies, the run ends. The Guardian can respawn once per wave if they fall.

## Core Mechanic

P1 moves the Runner through the arena collecting glowing data shards for score while enemies converge on them. P2 moves independently and fires in their movement direction (JUMP to shoot). Either player can trigger Bullet Time (ATTACK) — slowing all enemies and bullets to 20% speed for 3 seconds, shared 10-second cooldown shown on HUD. Enemies escalate in speed, count, and variety each wave.

## Visual Style

Pure pygame vector/geometric art. Black background with a faint animated rain-streak overlay. All city elements (barriers, walls) drawn as glowing cyan and magenta wireframe rectangles. Enemies are angular red geometric shapes (triangles, chevrons). The Runner glows bright white. The Guardian pulses electric blue. Data shards are small spinning yellow diamonds. Bullet Time tints the entire screen a deep indigo with motion-blur trails on bullets.

## Win Condition

No true win — survive as many waves as possible. Score is posted on a Game Over screen showing wave reached, shards collected, and enemies destroyed. High score persists in a local JSON file during the session.

## Pacing

Waves start slow (5–8 weak drones) and escalate every 30 seconds with faster enemies, new types (homing missiles, shield-bearing elites), and tighter spawn patterns. By wave 5 the screen is chaotic. Brief 5-second breathing gap between waves.

## Tone

Tense and desperate — low ambient synth drone soundtrack (generated via pygame.sndarray), screen-shake on hits, red vignette flash when the Runner takes damage, frantic enemy pathing that always prioritizes the Runner.

## Notes

- P1 controls Runner: arrow keys + left-ctrl (JUMP unused) + left-alt (ATTACK = trigger Bullet Time)
- P2 controls Guardian: RFDG movement + A (JUMP = shoot) + S (ATTACK = trigger Bullet Time)
- Bullet Time is shared resource — either player can activate it, both benefit, one cooldown
- Runner has 3 HP shown as glowing white icons; Guardian has 2 HP shown as blue icons
- One mid-arena 'safe zone' barrier cluster as cover, randomized each wave
- Use the Input class pattern from chopper_chase.py — no pygame.key.get_pressed() range loops
- Hold ATTACK+JUMP simultaneously on either controller to quit to OS
- Keep all HUD elements (HP, score, wave, bullet-time cooldown bar) at least 30px from top edge

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
