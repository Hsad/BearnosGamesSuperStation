---
title: "Ice Clash"
slug: ice-clash
players: 4
genre: Sports — Ice Hockey
created: 2026-04-25T05:01:31
status: failed
---

## Game Concept

A tense 2v2 retro ice hockey game on a single screen rink. Two teams of two skaters battle to score 5 goals first. Players pass by skating near teammates with the puck, shoot with ATTACK, and burn a cooldown dash with JUMP. Pure arcade hockey — no power-ups, just raw competition.

## Core Mechanic

Each player controls one skater on an 8-way joystick. Whichever skater touches the puck owns it. ATTACK fires a slap shot in the direction the skater is facing. JUMP triggers a brief speed burst (1.5s cooldown) to chase down pucks or blow past defenders. A goal is scored when the puck crosses the opponent's goal line. First team to 5 goals wins.

## Visual Style

Retro 8-bit pixel art. Top-down ice rink with scanline overlay, chunky pixel skaters in team colors (red vs blue), pixel-font score display, and brief screen-shake + flash on every goal. All graphics drawn procedurally with pygame.draw — no external assets.

## Win Condition

First team to score 5 goals wins the match. A victory screen shows the winning team's color with a flashing goal tally before returning to the attract screen.

## Pacing

Fast and unrelenting — the puck moves quickly, rink is mid-size so collisions are constant. Dash cooldown creates micro-decisions. No timer, so matches can be quick bursts or grinding nail-biters depending on skill.

## Tone

Tense and competitive. Minimal music; emphasis on satisfying sound effects (puck clack, goal siren, crowd cheer all synthesized via pygame). Score display always prominent to keep the pressure on.

## Notes

- P1+P2 form Team Red, P3+P4 form Team Blue
- Puck physics: slides with friction, bounces off boards and skaters
- Slap shot power is fixed (no charge) for snappy feel
- Dash has a visible cooldown pip under each skater sprite
- Goal mouth is protected by a simple goalie-post collision box (no AI goalie)
- Scoreboard sits at top-center, kept at least 30px from screen edge per cabinet spec
- Hold ATTACK+JUMP simultaneously to quit from any screen
- Rink drawn with center circle, blue lines, and crease markings in pixel style
- Consider adding a brief face-off freeze at center ice after each goal

## Build Constraints

- Python + pygame
- No external assets required
- Must launch cleanly and exit cleanly on ATTACK+JUMP
