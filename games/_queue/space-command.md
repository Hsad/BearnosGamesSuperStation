---
title: "SPACE COMMAND"
slug: space-command
players: 1-4
genre: Cooperative Tactical Strategy
created: 2026-04-26T00:13:34
status: failed
---

## Game Concept

Four players command sector fleets in a split-screen cooperative campaign. Each player controls one quadrant of the battlefield. Pause mid-battle to queue group movement orders (all units in your sector move forward, hold, or defend), then execute in real-time while enemies advance. Complete objectives, unlock new ship types, and reinforce endangered teammates across a multi-mission campaign.

## Core Mechanic

Pause-to-plan fleet orders with real-time execution. Each player: (1) uses 8-way joystick to select a movement direction, (2) presses JUMP to pause and confirm orders, (3) orders auto-execute in real-time on all units in that sector. Teammates can reinforce struggling sectors.

## Visual Style

Modern 3D vector graphics. Clean geometric UI. Split-screen quadrants clearly bounded; each sector shows fleet, objectives, enemy positions. Minimalist HUD (score, mission progress, available ship types).

## Win Condition

Complete all missions in the campaign by capturing/destroying all designated objectives in your sector. If a sector falls, teammates can move units in to reinforce and recover it. Lose only if all objectives are lost across all sectors.

## Pacing

Medium; deliberate pause-plan cycles with real-time execution between pauses. Enemy complexity and unit variety escalate across missions as new ship types unlock.

## Tone

Serious and tactical.

## Notes

- Screen layout: 4 quadrants (480×540 each) at 1920×1080. Each player has one quadrant.
- Input: 8-way joystick queues a direction. JUMP pauses & confirms orders. ATTACK executes all queued orders in real-time.
- Reinforcement: teammates can move their units into an endangered sector to defend or retake it.
- Ship progression: new ship types (e.g., scouts, bombers, tanks) unlock after each mission. Carry forward to the next mission.
- Campaign: 5–7 missions with escalating objectives (defend, capture, destroy, escort).
- Scoring is secondary; mission completion and squad survival are primary.
- Auto-exit on ATTACK+JUMP held simultaneously (per cabinet convention).

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- 1920×1080 fullscreen
- 4-player input via controllers.json mapping
- Each player's UI must stay ≥30px from top (bezel clearance)
