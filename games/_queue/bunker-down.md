---
title: "Bunker Down"
slug: bunker-down
players: 1
genre: Top-down survival wave defense
created: 2026-04-25T04:10:59
status: failed
---

## Game Concept

A lone survivor in a post-apocalyptic wasteland defends a crumbling bunker against endless zombie hordes. Scrap metal drops from every kill and is spent on traps and turrets placed around the perimeter. Waves never stop — they only get worse. Dark humor keeps the mood from tipping into pure despair.

## Core Mechanic

Top-down free-roam on a wasteland map. Zombies pathfind toward the bunker from the map edges each wave. The player runs around collecting scrap (auto-pickup on contact), then uses JUMP to cycle through available trap types (Spike Pit, Flame Barrel, Electric Fence, Auto-Turret) and ATTACK to place the selected trap at the player's current tile. Traps have scrap costs shown in a HUD strip at the bottom. Placed traps persist until destroyed by zombies. Between waves a short scavenge phase gives extra scrap. The game ends when the bunker's HP hits zero; final score is waves survived + zombies killed.

## Visual Style

Top-down pixel-art style drawn entirely with pygame primitives and surfaces. Desaturated wasteland palette — cracked earth browns, rust reds, ash grays, dull greens for slime. Chunky tile-based map with the bunker centered. Zombies are simple sprites with wobble animations. Darkly humorous wave title cards appear between rounds (e.g., 'WAVE 4: The Ones That Used To Be Your Neighbors'). Occasional sarcastic kill-count comments appear as floating text.

## Win Condition

Endless survival — no true win state. High score is tracked as Waves Survived and Total Zombies Killed, displayed on game-over screen with a sardonic epitaph line.

## Pacing

Waves escalate in zombie count, movement speed, and HP every 3 waves. Waves 1-3 are tutorial-paced; by wave 10 the horde is thick and fast. A 10-second scavenge phase between each wave lets the player collect leftover scrap and reposition. Boss zombies (giant, slow, high HP) appear every 5 waves and drop large scrap bounties.

## Tone

Gritty but darkly humorous. The world is bleak; the commentary is wry. Trap names are deadpan ('Mild Inconvenience Mk. II'). Death screen reads something like 'You held out. Briefly. The zombies are unimpressed.'

## Notes

- Trap types: Spike Pit (cheap, single use, high damage), Flame Barrel (mid-cost, damages all passing zombies until burned out), Electric Fence (line trap, stuns and damages, degrades over time), Auto-Turret (expensive, shoots nearest zombie, destroyed after sustained hits)
- Bunker has a visible HP bar on the HUD; zombies that reach the bunker deal contact damage to it each second
- Player is invincible (wasteland survivor is scrappy) — only the bunker can be destroyed, keeping tension on base defense not personal survival
- Scrap is shown as a glowing orange counter in the HUD; placed trap cost flashes red if insufficient funds
- Map is scrollable or large enough to require movement, so scrap collection is a risk-vs-reward decision during active waves
- Use the Input class pattern from chopper_chase.py for all controller input; P1 controls: arrow keys, left ctrl (JUMP), left alt (ATTACK)
- Hold ATTACK + JUMP simultaneously on any screen to quit, per cabinet convention

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
- Fullscreen 1920x1080
- Keep all HUD and UI elements at least 30px from the top of the screen
- Follow Input class event-based pattern from games/chopper-chase/chopper_chase.py
- Include meta.json with title, description, players, author, added date
- Include launch.sh setting SDL env vars
