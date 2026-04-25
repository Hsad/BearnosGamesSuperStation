---
title: "Garden Zen"
slug: garden-zen
players: 1-2
genre: Sandbox Garden Simulation
created: 2026-04-25T07:31:38
status: failed
---

## Game Concept

A relaxing cooperative game where 1-2 players tend an endless garden, planting seeds and watering plants while weather and seasons affect growth.

## Core Mechanic

Move characters independently with 8-way joystick; ATTACK button plants seeds; JUMP button waters plants. Both players contribute to a shared garden that grows forever.

## Visual Style

Pixel art nature theme with grass tiles, plants at various growth stages, simple weather effects (rain clouds, sun rays), bright natural color palette.

## Win Condition

No winning condition; endless peaceful garden tending mode where the garden grows indefinitely as players plant and care for it.

## Pacing

Relaxed real-time; no time pressure or scoring race, focus on exploration and tending.

## Tone

Chill, meditative, wholesome; emphasis on cooperation and growth rather than conflict.

## Notes

- Weather system: rain accelerates growth, drought slows it; affects both players' work equally
- Shared single-screen garden space; both players visible and moving independently
- Simple growth stages: seed → sprout → mature plant → flowering
- Optional: different plant types with varying growth speeds
- Cooperative only; no competitive elements or scoring battles

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- Fullscreen 1920×1080
- Keep UI elements 30px from top (bezel occlusion)
- Support 1-2 players simultaneously on shared screen
