---
title: "THE FAILING ENGINE"
slug: the-failing-engine
players: 1
genre: Puzzle / Strategy
created: 2026-04-23T01:53:45
status: failed
---

## Game Concept

You are the sole technician keeping an ancient, crumbling machine alive. Broken components cascade across a grid-based board — route power, redirect steam, and patch failing circuits before the machine's heart stops beating. Each stage reveals a deeper, more desperate chamber of the dying engine.

## Core Mechanic

Move a snap-to-grid cursor with the joystick across a 10x10 board filled with broken pipe, gear, and wire tiles. Press JUMP to rotate the tile under your cursor; press ATTACK to lock it in place. Completing a continuous path from a power source to a receiver clears it and restores machine integrity. Tiles crack and fail over time, creating constant new breaks to chase.

## Visual Style

Dark industrial pixel art — glowing amber and cyan pipes, spinning gears, and flickering wires drawn entirely in code on a black iron-plate grid. Screen shakes and sparks erupt as integrity drops. A persistent integrity bar pulses red when critical.

## Win Condition

Clear all handcrafted stages of the machine. Each stage is solved when integrity stays above zero long enough to seal the chamber. A final score tallies speed, perfect clears, and fewest wasted moves.

## Pacing

Slow and methodical in early chambers; escalates to frantic multi-break crises as deeper stages introduce simultaneous failures and ticking decay timers.

## Tone

Tense and brain-burning with a melancholic undercurrent — you are fighting to save something magnificent that may already be beyond saving.

## Notes

- JUMP rotates the tile under the cursor; ATTACK locks/confirms placement
- Integrity bar replaces a lives system — bad paths drain it, completed paths restore it
- Stages are fixed and handcrafted, but tile crack order is seeded randomly each run for replayability
- A brief 2-line text epitaph is shown between stages hinting at the machine's forgotten purpose
- No avatar on the board — the cursor IS the player; the machine is the world
- Persist a top-10 all-time high score table to a local JSON file between sessions
- Hold ATTACK + JUMP simultaneously on any screen to quit cleanly

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
