---
title: "Skateboard Time Trial"
slug: skateboard-time-trial
players: 1
genre: Time Trial Racing
created: 2026-05-01T15:41:40
status: failed
---

## Game Concept

Solo skateboarding race through natural outdoor terrain. Navigate past obstacles by jumping with precise timing, manage your boost cooldown strategically, and chase the fastest possible time. Crashes don't end your run — bounce back and keep going.

## Core Mechanic

Joystick steers left/right through terrain. JUMP button clears obstacles in your path. ATTACK button triggers speed boost with cooldown. Navigate a scrolling course, avoid/jump hazards, reach finish in fastest time.

## Visual Style

Behind-the-skater third-person perspective. Natural outdoor landscape (rolling hills, trees, grass, rocks). Silly, exaggerated physics and character animations for goofy tone.

## Win Condition

Fastest completion time across multiple runs. Player chases personal best.

## Pacing

Speed of incoming obstacles increases on subsequent runs/attempts. Single run per session with timer displayed.

## Tone

Silly and goofy fun — exaggerated crashes, bouncing animations, lighthearted racing vibe.

## Notes

- Infinite boost with cooldown system to manage resource timing
- Crash mechanics: ragdoll bounce back up, no game-over
- Obstacles procedurally generated or placed in fixed course
- UI (timer, boost meter) positioned >30px from top for bezel clearance
- One skateboard character, stylized and cartoonish

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- Event-based input handling (no get_pressed range loops)
- 1920×1080 fullscreen
- Follow Input class pattern from chopper-chase.py
