---
title: "Dungeon Vanguard"
slug: dungeon-vanguard
players: 1
genre: Brawler / Beat-em-up
created: 2026-04-22T01:27:06
status: failed
---

## Game Concept

A lone hero fights through a monster-infested dungeon, picking up fallen weapons along the way, battling through increasingly dangerous rooms to reach the exit and escape. Each room is a self-contained arena that must be cleared before the door forward opens.

## Core Mechanic

Classic side-scrolling brawler: ATTACK to punch/use weapon, JUMP to leap. Enemies spawn in waves per room. Defeated enemies drop weapons (sword, axe, spear, torch) that the player can pick up — each with unique reach and attack speed. Weapons break after limited uses, forcing the player to adapt.

## Visual Style

Dark stone dungeon aesthetic rendered in bold pixel-art style using pygame.draw primitives and rects. Torchlight flicker effect on walls, shadowy enemy sprites built from geometric shapes, glowing weapon pickups for visibility. Color palette: deep grays, warm amber torchlight, enemy blood-red accents.

## Win Condition

Player clears all rooms on a floor and reaches the exit staircase. Multiple floors of increasing difficulty. Reaching the surface (floor 0) triggers the victory screen.

## Pacing

Medium–fast. Rooms are small and intense. Enemy count scales per floor. No time limit, but enemies continuously pressure the player. Boss enemy guards the final exit staircase.

## Tone

Epic and heroic — booming visual feedback (screen flash on kills, large hit numbers), dramatic room-clear fanfare drawn as animated text, a sense of mounting triumph as floors fall.

## Notes

- Unarmed state: basic short-range punch; picking up a weapon extends reach and adds a damage bonus
- Weapons degrade and shatter with a visual burst effect after ~10 hits
- Enemy types: Skeleton (fast, low HP), Orc (slow, high HP), Wraith (dodges, ranged attack)
- Boss on final floor: Stone Golem with a stomp shockwave the player must jump over
- Room doors are visually locked (red glow) until all enemies are defeated, then unlock (green glow)
- HP shown as a hero portrait + heart icons along the bottom-left (safe from bezel)
- Score tracked by enemies defeated and floors cleared, shown at game-over/victory
- Hold ATTACK+JUMP on any screen to quit — per cabinet convention

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
