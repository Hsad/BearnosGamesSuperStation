# Bearnos — AI Game Generator for the Arcade Cabinet

## Concept

Players scan a QR code on the cabinet, open a chat on their phone, describe a game, and an AI builds and installs it. The game appears in the launcher automatically.

---

## Flow

1. Player scans QR, opens a unique session URL on their phone (`pi_ip:80/<session-slug>`)
2. Chats with an AI interviewer that draws out a proper game design — genre, player count, win condition, pacing, mechanics, edge cases
3. AI confirms the spec with the player before submitting
4. Spec enters a queue; a watcher picks it up and a builder agent implements the game
5. Game folder is created immediately on pickup, marked hidden until the build completes
6. Launcher picks it up automatically once the game is ready
7. Player checks the cabinet — their game is there

---

## Key Design Decisions

**Session slug as the persistent thread**
The URL slug ties the chat session to the spec to the game folder. If the player returns to their URL, the page can tell them whether their game is queued, building, or ready.

**Everything lives in the game folder**
Once the watcher picks up a spec, the spec moves into the game's folder and lives there permanently alongside the game files. The queue is just a handoff mechanism, not long-term storage.

**Hidden until ready**
The launcher skips game folders marked as hidden. The builder marks the game visible only when it's confident the implementation is complete and launchable.

**Chat agent vs. builder agent are separate**
The chat agent is a conversational interviewer focused on extracting a good spec. The builder agent is a coding agent that works from that spec. They don't overlap.

**Pi-local, simple HTML**
Web server runs on the Pi. No cloud dependency. Chat UI is plain HTML served to the player's phone browser. DGX is available if heavier compute is needed for builds.

---

## Open Questions

- Static QR code (sessions created server-side on load) vs. per-session QR printed at the cabinet?
- What happens if a player wants to revise a game that's already been built?
- Rate limiting / abuse if the cabinet is in a public space?
- Should players be able to put their name on games they commission?
- Automatic DGX escalation on build failure, or manual?
