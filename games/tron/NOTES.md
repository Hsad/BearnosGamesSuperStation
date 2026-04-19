# Tron — Design Notes

## Underpasses (not yet implemented)

Pre-placed tunnel sections on the grid. Considered and shelved — game may not need them.

**Design spec:**
- Dark grey box, ~2:1 ratio (long axis = tunnel direction), short edges are darker grey
- Enter via a short edge while moving along the tunnel axis → go underground (drawn faded)
- While underground: ignore above-ground trails, don't leave a trail, long sides are solid walls (turning into them = death)
- Exit at the other short edge → pop back to surface
- Above-ground players passing over the tunnel rectangle are unaffected
- Two underground players can still collide with each other

**Implementation notes:**
- Tunnels defined as `(x, y, w, h, axis)` grid rectangles
- Render in layers: ground trails → underground players (faded) → tunnel box → surface players
- The tunnel box drawn on top is what visually hides underground players while inside
- Edge case: speed mode players move 1.5 cells/tick — entry/exit trigger cells need care
