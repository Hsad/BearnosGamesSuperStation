---
title: "Space Junk Derby"
slug: space-junk-derby
players: 2-4
genre: Arena Racing / Item Collection
created: 2026-04-25T04:37:52
status: failed
---

## Game Concept

2–4 players race absurd vehicles (a rocket-boosted office chair, a jet-powered shopping cart, a thruster bathtub, and a turbo fridge) around a wraparound single-screen space station arena. The station is littered with floating random junk — rubber ducks, pizza slices, garden gnomes, and more. Players scramble to grab as many items as possible before the 90-second timer runs out. Zero-gravity zones flip physics, floating debris bounces everyone around, and ATTACK lets you steal items straight out of a rival's haul. Glitchy CRT scanlines and neon outlines wrap the whole chaos in a retro-futurist aesthetic.

## Core Mechanic

Players zip around a toroidal (edge-wrapping) arena collecting randomly spawning junk items. JUMP activates a short speed boost with a cooldown. ATTACK grabs a nearby item OR steals one from a colliding rival. Floating debris acts as dynamic pinball bumpers; zero-gravity zones randomly appear and reverse vertical movement. Most items collected when the timer hits zero wins. Ties broken by last item grabbed.

## Visual Style

Glitchy CRT scanline overlay on a dark space-station grid background. Players drawn as bold, neon-outlined sprites — each vehicle a distinct silhouette and color (P1 cyan chair, P2 yellow cart, P3 magenta bathtub, P4 green fridge). Collectibles are tiny pixel-art doodles. Screen flickers and color-shifts briefly on collisions. All drawn procedurally with pygame primitives and surfaces — no external assets.

## Win Condition

Player with the highest item count when the 90-second round timer expires. A scoreboard screen shows final tallies with a celebratory glitch-flash for the winner. Players can immediately start a rematch with ATTACK or hold ATTACK+JUMP to quit.

## Pacing

Fast and frantic from the first second. Items spawn on a 1.5-second cadence, accelerating to 0.8 seconds in the final 20 seconds. Zero-gravity zones pulse in and out every 10–15 seconds. The last 10 seconds triggers a 'Junk Storm' — double spawn rate and all debris speeds up.

## Tone

Silly and chaotic — cartoon collision physics, exaggerated screen-shake on big hits, comedic item names in a floating pop-up when grabbed. Competitive enough to cause trash-talk, light enough that losing is funny.

## Notes

- Each player vehicle is unique: P1 = office chair (balanced), P2 = shopping cart (fast, poor turning), P3 = bathtub (slow, wide grab radius), P4 = fridge (heavy, stuns rivals on collision)
- ATTACK steal only works when two players are within ~60px of each other — prevents ranged sniping
- Zero-gravity zones rendered as faint pulsing blue ovals; physics inside inverts Y-axis acceleration
- Floating debris pieces are convex polygons that bounce off walls and each other using simple elastic collision
- Item sprites: rubber duck, pizza slice, garden gnome, traffic cone, potted cactus, toilet plunger — all drawn with pygame.draw primitives
- Round starts with a 3-2-1-GO countdown; players cannot move until GO
- CRT effect: a semi-transparent scanline surface (alternating alpha strips) composited each frame — cheap and effective in pygame
- Use the event-based Input class pattern from chopper_chase.py; do NOT use pygame.key.get_pressed() with a range loop
- Keep all score HUD at least 30px from the top edge due to cabinet bezel
- Hold ATTACK+JUMP simultaneously to exit from any screen

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
