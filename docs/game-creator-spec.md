# Game Creator — Feature Spec

## Overview

A special screen in the arcade launcher, always last in the game list, that lets players
design a new game via a guided Q&A with Claude. The session produces a structured spec
file. A background daemon watches for new specs and hands them off to a build agent
(local or remote) to generate and validate the game, then drops it into the launcher
automatically.

---

## Components

| Component | Where it runs | What it does |
|---|---|---|
| **Game Creator screen** | Pi, in-process with launcher | Interviews the player, writes spec to spool |
| **Game Dev Daemon** | Pi, background service | Watches spool, dispatches build jobs, deploys results |
| **Build Agent** | Spark (or local) via SSH | Takes spec → builds game → tests it → signals done |

---

## 1. Game Creator Screen

### Entry point

- Appears as the last item in the launcher game list, always pinned there.
- Selecting it launches the creator flow full-screen, styled identically to the launcher
  (same font, palette, UI chrome).

### Question flow

Claude is given a **question category guide** (see below) and asked to generate questions
freely, but covering all the bases. Each turn:

1. Claude returns: a question string + exactly 4 answer options.
2. Player navigates options with the joystick (up/down), selects with ATTACK.
3. The selected answer is recorded and fed back to Claude as context for the next question.
4. Repeat up to **10 questions maximum**.
5. Claude may decide it has enough information before 10 and signal completion.
6. No back navigation — the answer sequence is Claude's context chain; rewinding it
   would corrupt that chain.

**Regenerate:** On any question, the player can press JUMP to regenerate — Claude produces
a new question + 4 fresh options on the same topic. Limit: **3 regenerates per question**.
A small indicator shows remaining regenerates (e.g. `[≋≋≋]` → `[≋≋·]` → `[≋··]` → `[···]`).

### Question category guide (prompt context for Claude)

Claude should cover these areas, in roughly this order, adapting based on prior answers:

1. Core mechanic / genre (platformer, shooter, puzzle, racing, brawler, etc.)
2. Number of players (1–4)
3. Visual theme or aesthetic (pixel, neon, retro, abstract, etc.)
4. Win condition or objective
5. Pacing / difficulty feel
6. Cooperative vs competitive (if multiplayer)
7. Any special mechanic, power-up, or twist
8. Tone (silly, tense, chaotic, chill)
9. Anything Claude wants to know to nail the controls or game feel
10. Claude's wildcard — anything it still needs

Claude is free to skip, reorder, or rephrase these. The guide is a safety net, not a script.

### Spec display

After the last question (or when Claude signals done):

- Show the completed spec sheet full-screen, rendered in launcher style.
- The spec is human-readable (see format below).
- At the bottom: a **placeholder ASCII QR code** (hard-coded dummy block for now, real
  QR linking to a follow-up chat flow is a future phase).
- Player exits with ATTACK+JUMP (hold both) — same quit gesture as menus elsewhere.

At this point the spec is written to `games/_queue/<slug>.md` and the creator's job is done.

---

## 2. Spec File Format

Saved to `games/_queue/<slug>.md`. The slug is auto-generated from the game title
(lowercase, hyphenated).

```markdown
---
title: "Lava Surfboard Chaos"
slug: lava-surfboard-chaos
players: 2-4
genre: racing
created: 2026-04-21T14:32:00
status: queued
---

## Game Concept

2–4 players race across collapsing lava platforms on surfboards. Last one standing wins.

## Core Mechanic

Top-down racing. Platforms fall into the lava behind you. Players can knock each other
off with ATTACK. JUMP gives a brief speed boost with a cooldown.

## Visual Style

Bright neon pixel art. Lava is animated. Camera follows the action with slight zoom out
when players spread apart.

## Win Condition

Last player on a platform wins the round. First to 3 round wins takes the match.

## Pacing

Fast. Rounds last 60–90 seconds. Short pause between rounds to reposition.

## Tone

Chaotic and silly. Big knockback. Exaggerated sound effects.

## Notes

- 4-player support required
- Controls: joystick to move, ATTACK to shove, JUMP to boost
- Must work at 1920×1080 fullscreen

## Build Constraints

- Python + pygame
- No external assets required (procedural or primitive shapes acceptable)
- Must launch cleanly and exit cleanly on ATTACK+JUMP
```

---

## 3. Game Dev Daemon

A small persistent service (`launcher/game_dev_daemon.py`) that runs on the Pi.

### Responsibilities

1. **Watch** `games/_queue/` for new `.md` files with `status: queued`.
2. **Dispatch** the spec to the build agent (see below).
3. **Monitor** for the result.
4. **Deploy:** when the agent signals done, the game directory appears in `games/<slug>/`
   and the spec `status` is updated to `deployed`.

### Dispatch modes (swappable)

The daemon has a pluggable dispatch interface so the build backend can be changed without
touching anything else:

| Mode | How it works |
|---|---|
| `local` | Runs the build agent script directly on the Pi |
| `spark` | SSHes to the DGX Spark, runs the agent there, SCPs result back |
| `remote_generic` | SSH to any host — same as spark mode, different config |

Config lives in `launcher/daemon_config.json`:

```json
{
  "dispatch_mode": "spark",
  "spark_host": "192.168.1.150",       // mDNS name: spark.local
  "spark_user": "arcade",
  "spark_agent_path": "/home/arcade/arcade-builder/run_agent.sh",
  "result_pickup_path": "/home/arcade/arcade-builder/output/",
  "poll_interval_seconds": 30
}
```

### Daemon lifecycle

- **Started by the Game Creator screen** when a spec is written to the spool. The creator
  launches the daemon if it isn't already running, then exits. The daemon keeps running
  in the background until the job is done.
- Polls spool directory every N seconds (configurable).
- One job at a time to start; queue additional specs until current build finishes.
- Logs to `logs/game_dev_daemon.log`.

---

## 4. Build Agent (on Spark)

The Spark-side agent is out of scope for the current build phase, but its interface is
defined here so the daemon can be built against it.

### Contract

**Input:** path to a spec `.md` file (SSHed over or accessible on shared path)

**Output:** Exit 0 + a populated `games/<slug>/` directory (containing `<name>.py`,
`launch.sh`, `meta.json`) copied to the agreed output path.

The agent does not exit until the game works. There is no red light path — failure is
not a valid output state. The agent loops, retries, and self-corrects until it produces
a game that passes validation.

### What the agent should do (to be specced in detail separately)

1. Parse the spec.
2. Generate the game (Claude API or Claude Code).
3. Run it headlessly (or with a virtual display) and confirm it launches without crashing.
4. Confirm it exits cleanly on ATTACK+JUMP.
5. If tests fail: diagnose, fix, and re-test. Loop until passing.
6. Only exit once the game is confirmed working.

### Harness design note

The build agent is the primary place to experiment with agent loop architectures:
- Single-shot: one big Claude prompt, whole game in one response.
- Stepwise: spec → scaffold → implement → test → fix loop → deploy.
- Claude Code CLI: invoke `claude` as a subprocess with a task prompt.
The daemon doesn't care which approach the agent uses, only the exit code and output path.

---

## 5. Launcher Integration

- The launcher scans `games/` on startup. Any directory containing a valid `meta.json`
  appears in the list.
- The Game Creator entry is pinned last by convention in the launcher sort, not by
  directory name.
- No restart needed — games deployed while the launcher is running appear on next
  navigation refresh (or relaunch).

---

## 6. Future Phases (not in scope now)

- **Real QR code** at the bottom of the spec, linking to a hosted chat session where the
  player can continue refining the spec from their phone.
- **Build progress screen** at the cabinet showing live agent steps.
- **Multi-job queue** in the daemon.
- **Spec versioning** (player comes back, tweaks a game, rebuilds it).

---

## Resolved Decisions

| Question | Decision |
|---|---|
| When does the daemon start? | Launched by the Game Creator when a spec is written; stays running in background |
| What happens on build failure? | Not a valid state — agent retries until the game works |
| SSH key setup (Pi ↔ Spark) | Manual, handled separately |
