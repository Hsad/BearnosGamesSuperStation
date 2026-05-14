---
title: "Momentum Flux"
slug: momentum-flux
players: 1
genre: Physics-based momentum platformer
created: 2026-05-01T15:03:07
status: failed
---

## Game Concept

Navigate chaotic neon levels by mastering floaty, momentum-driven movement through environmental puzzles and obstacles. Reach the end of each level as hazards and physics challenges intensify.

## Core Mechanic

Player controls character with floaty, forgiving momentum-based movement. Interact with gravity switches, moving platforms, bounce pads, and hazardous geometry. Each level introduces new physics mechanics that must be chained together to progress.

## Visual Style

Vibrant neon (bright cyans, magentas, yellows) on dark backgrounds. Minimalist geometric shapes. Glitch effects on transitions and collisions. Clean lines with neon glow.

## Win Condition

Reach the exit at the end of each level. Progress through increasingly complex physics-based obstacle courses.

## Pacing

Steady difficulty increase: early levels teach single mechanics (gravity zones, bounce surfaces), mid-game combines mechanics, late-game layers speed, tight timing, and multi-step puzzles.

## Tone

Chaotic and frantic—screen feels alive with neon energy, constant visual feedback, fast-paced but forgiving.

## Notes

- Floaty, momentum-based controls—player glides and drifts rather than snaps to inputs
- Environmental interaction: gravity reversals, bounce zones, conveyor platforms, moving obstacles
- Physics-based puzzles integrated into level design—solve by chaining momentum and environment
- No enemies; all challenge comes from level design and physics
- Solo single-player focus
- Neon/glitch aesthetic—visual feedback on collision and momentum changes
- Consider tiered difficulty: 3–5 levels minimum, each introducing and combining mechanics

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- 1920×1080 fullscreen display
- Single player (P1 controls only)
- Keep UI/text 30px from top edge due to cabinet bezel
