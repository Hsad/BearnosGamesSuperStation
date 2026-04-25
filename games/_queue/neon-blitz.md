---
title: "Neon Blitz"
slug: neon-blitz
players: 4
genre: Racing / Brawler Hybrid
created: 2026-04-25T20:02:23
status: failed
---

## Game Concept

Two teams of two players race hovercrafts through a looping neon cyberpunk circuit, building combo multipliers by chaining gates, drafting, and ramming rivals. Every risky move can spike your score—or wreck your run.

## Core Mechanic

Players accumulate points by passing through glowing score gates while maintaining a combo chain. Each consecutive gate extends the chain multiplier (x1→x2→x4→x8). Momentum is physics-based with inertia and drift. ATTACK rams nearby opponents to break their chain. JUMP activates OVERDRIVE—a short speed and multiplier burst (x3 bonus)—but if you collide with anything during OVERDRIVE, you wipe out, lose your chain, and are briefly stunned. High risk, massive reward.

## Visual Style

Dark background with neon grid lines and glowing circuit-trace track edges. Hovercrafts are sharp silhouettes with team-colored exhaust trails (cyan vs orange). Score gates pulse bright when active. HUD uses blocky monospace fonts with scanline overlays. No sprites or external assets—all drawn with pygame primitives and glow effects via surface blending.

## Win Condition

Match ends after 3 minutes. The team with the highest combined score wins. Individual scores are tracked; the top scorer gets a BEST DRIVER callout.

## Pacing

Consistently hard from the first second—the circuit is tight, OVERDRIVE windows are narrow, and opponents are always in ramming range. No ramp-up, no safe zones.

## Tone

Gritty and serious. No jokes. Terse UI text. Sparse sound cues. The vibe is competitive underground street racing.

## Notes

- Teams are P1+P3 (cyan) vs P2+P4 (orange), auto-assigned on join
- OVERDRIVE (JUMP) has a 4-second cooldown shown on HUD as a draining bar
- Ramming during an opponent's OVERDRIVE scores a bonus 'Interrupt' point burst for the attacker's team
- Chain resets on wall collision or being rammed—momentum loss is punishing
- Score gates cycle positions every 20 seconds to prevent camping
- A 'COMBO x8' achieved by either team triggers a brief screen flash and audio sting to heighten tension
- Hold ATTACK+JUMP simultaneously on any screen to quit

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- Use event-based Input class pattern from games/chopper-chase/chopper_chase.py
- Keep HUD elements at least 30px from top of screen
- Fullscreen 1920x1080
