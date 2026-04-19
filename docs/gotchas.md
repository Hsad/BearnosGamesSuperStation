# Known Gotchas

## pygame key input — P1 and P3 unresponsive

**Symptom:** P1 (arrow keys + left ctrl/alt) and P3 (right ctrl/shift) can't join or act.

**Cause:** Using `get_pressed()` with a range-based set only captures scancode indices
(0–283). P1/P3 use SDLK codes like `1073741906` (up arrow) and `1073742048` (left ctrl)
which are far outside that range and are never tracked.

```python
# BROKEN
raw = pygame.key.get_pressed()
self._curr = {i for i in range(len(raw)) if raw[i]}
```

**Fix:** Use KEYDOWN/KEYUP events — `e.key` gives the correct SDLK value for every key.

```python
def pump(self, events):
    self._prev = set(self._curr)
    for e in events:
        if e.type == pygame.KEYDOWN:
            self._curr.add(e.key)
        elif e.type == pygame.KEYUP:
            self._curr.discard(e.key)
```

Collect events once per frame, pass to `pump(events)`, then reuse the same list for
quit/escape handling. Working reference: `games/chopper-chase/chopper_chase.py`.
