# Odin + Raylib Games on the Cabinet

Short reference for adding Odin games to the arcade. Standard game conventions
(meta.json, launch.sh, top-30px bezel clearance, ATTACK+JUMP to quit) still
apply — see `adding-a-game.md`. This doc only covers what's Odin-specific.

## Toolchain (already installed on the Pi)

| What | Where |
|---|---|
| Odin compiler | `/home/hsad/odin-linux-arm64-nightly+2026-04-02/odin` (not on `$PATH`) |
| Linker driver | `clang` (`sudo apt install clang`) |
| Raylib static lib | `…/odin-…/vendor/raylib/linux/libraylib.a` — **aarch64, PLATFORM=DRM** |

The aarch64 raylib was built from source against raylib 5.5 with
`-DPLATFORM=DRM`. Originals are kept next to the active lib:

```
libraylib.a            ← aarch64, PLATFORM=DRM   (active)
libraylib.a.x11.bak    ← aarch64, PLATFORM=Desktop (GLFW/X11)
libraylib.a.x86_64.bak ← what Odin's nightly mislabeled as arm64
```

## launch.sh template

raylib was built with `PLATFORM=DRM` (KMS/DRM/GBM — no window manager needed,
which is what we want since the cabinet boots straight to console). The Odin
binding only auto-links `-ldl -lpthread`, so every game has to pull in the rest
of the platform stack via `-extra-linker-flags`.

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"

ODIN=odin
if ! command -v "$ODIN" >/dev/null 2>&1; then
    ODIN="/home/hsad/odin-linux-arm64-nightly+2026-04-02/odin"
fi

BIN=./mygame
SRC=mygame.odin

DRM_LIBS="-lGLESv2 -lEGL -lgbm -ldrm -linput -ludev -lxkbcommon -lm"

if [ ! -x "$BIN" ] || [ "$SRC" -nt "$BIN" ]; then
    "$ODIN" build . -out:"$BIN" -o:speed -extra-linker-flags:"$DRM_LIBS"
fi

exec "$BIN"
```

No `SDL_VIDEODRIVER=…` needed — raylib's DRM platform talks to KMS directly.
The launcher's injected SDL env vars are ignored by raylib games.

## Input mapping

raylib uses GLFW-style keycodes (`rl.KeyboardKey.LEFT_CONTROL` = 341, etc.),
not SDL scancodes. The `config/controllers.json` file uses SDL keycodes — those
do **not** work with raylib. Hard-code the mappings instead. They match the
cabinet's wiring; if you change them, update both this guide and the cabinet:

```odin
KEYS_LEFT  := [?]rl.KeyboardKey{.LEFT, .D, .J, .V}            // P1..P4
KEYS_RIGHT := [?]rl.KeyboardKey{.RIGHT, .G, .L, .U}
KEYS_UP    := [?]rl.KeyboardKey{.UP, .R, .I, .Y}
KEYS_DOWN  := [?]rl.KeyboardKey{.DOWN, .F, .K, .N}
KEYS_JUMP  := [?]rl.KeyboardKey{.LEFT_CONTROL, .A, .RIGHT_CONTROL, .B}
KEYS_ATK   := [?]rl.KeyboardKey{.LEFT_ALT,     .S, .RIGHT_SHIFT,    .E}
```

Use `rl.IsKeyDown` for held, `rl.IsKeyPressed` for edge-triggered. raylib's
event handling already does the right thing — no `get_pressed()` equivalent
trap to worry about (that bug was pygame-specific).

## Window setup

```odin
rl.SetConfigFlags({.MSAA_4X_HINT, .VSYNC_HINT, .FULLSCREEN_MODE})
rl.InitWindow(1920, 1080, "Game Title")
rl.SetTargetFPS(60)
rl.SetExitKey(.KEY_NULL)   // disable raylib's default ESC-quits-window
rl.HideCursor()
```

Top 30px is still hidden by the cabinet bezel — keep HUD elements at y ≥ 30.

## Common stdlib calls (Odin nightly)

These tripped me up writing the first game; documenting so the next one is
faster.

| Want | Use |
|---|---|
| Read a file | `os.read_entire_file_from_path(name, allocator)` returns `([]byte, Error)` — check `err != nil`, **not** `(data, ok bool)` |
| Write a file | `os.write_entire_file_from_string(name, str)` returns `Error` |
| Format string for raylib text | `fmt.ctprintf("%d", x)` — returns `cstring` directly, no allocation worry |
| Format Odin string | `fmt.tprintf(...)` (temp allocator — clone with `strings.clone` if you need it to outlive the frame) |
| Math | `math.sin`, `math.cos`, `math.floor`, `math.ceil` (proc groups, dispatch on type) |
| Remove from `[dynamic]T` (any order) | Swap with last + `pop(&arr)`. Don't rely on `unordered_remove` being available |

At the end of every frame, `free_all(context.temp_allocator)` to reset what
`tprintf` etc. allocated.

## raylib API gotchas

A few signatures that don't read the way you'd guess:

- `rl.DrawLineEx(start, end, thick: f32, color: Color)` — **thickness comes
  before color**, not after. Same for `DrawRectangleLinesEx`. If you write the
  color where the thickness should be, you'll get "Cannot assign value of type
  Color to f32" errors that point at the color literal.
- Constants declared `H :: 1080` are untyped `int`. Arithmetic on them stays
  `int` and doesn't auto-convert to `i32` for `DrawRectangle(x, y, w, h, …)`.
  Cast explicitly: `i32(H - 60)`.
- `DrawText` takes a `cstring` for the text and `i32` for x/y/size. Build
  formatted strings with `fmt.ctprintf("%d", x)`.
- The rlgl matrix-stack helpers (`rlPushMatrix`, `rlTranslatef`, `rlRotatef`,
  etc.) are **not exposed** under the `rl` namespace in this vendor binding.
  Don't reach for them. Instead, build a `rl.Matrix` from
  `MatrixTranslate / Rotate{X,Y,Z} / Scale` and pass it to
  `rl.DrawMesh(mesh, material, transform)`. Compose matrices with the `*`
  operator — `MatrixMultiply` exists but is deprecated and noisy.
- `DrawCube(pos, w, h, l, color)` — the color is **required**, not optional.
- `cstring` cannot be indexed (`s[0]` fails). It's a raw pointer at the type
  level. Compare against a known literal or carry the length separately.
- Untyped float literals default to `f64`. Expressions like
  `wx := math.sin(yaw) * -0.3` will fail to type-check because `math.sin` on
  an `f32` returns `f32` but `-0.3` is `f64`. Annotate: `local_z : f32 = -0.3`.

## Drawing 3D primitives with rotation

raylib's `DrawCube` is axis-aligned only. To draw a rotated cube (e.g. a tank
hull facing some yaw), build a unit cube mesh once and draw it with a
transform matrix per instance:

```odin
cube_mesh := rl.GenMeshCube(1, 1, 1)
cube_mat  := rl.LoadMaterialDefault()

draw_box_rot :: proc(pos: Vec3, size: Vec3, yaw, pitch, roll: f32, col: rl.Color) {
    s := rl.MatrixScale(size.x, size.y, size.z)
    rZ := rl.MatrixRotateZ(roll)
    rX := rl.MatrixRotateX(pitch)
    rY := rl.MatrixRotateY(yaw)
    t := rl.MatrixTranslate(pos.x, pos.y, pos.z)
    cube_mat.maps[0].color = col
    rl.DrawMesh(cube_mesh, cube_mat, s * rZ * rX * rY * t)
}
```

For cylinders use `DrawCylinderEx(start, end, r1, r2, sides, color)` —
endpoint-based so no rotation needed. Working example: `games/breach/`.

## Split-screen via RenderTexture

For per-player viewports, render each player's scene to its own
`RenderTexture2D` and composite at the end:

```odin
rt[0] = rl.LoadRenderTexture(VW, VH)
rt[1] = rl.LoadRenderTexture(VW, VH)

// per frame:
for i in 0..<2 {
    rl.BeginTextureMode(rt[i])
    rl.BeginMode3D(cam[i])
    // … draw world for player i …
    rl.EndMode3D()
    // … HUD draws here go directly into the render texture …
    rl.EndTextureMode()
}

rl.BeginDrawing()
// FLIP Y in source rect — render textures are upside-down on GPU
src := rl.Rectangle{0, 0, f32(VW), -f32(VH)}
rl.DrawTexturePro(rt[0].texture, src, rl.Rectangle{0, 0, f32(VW), f32(VH)}, {}, 0, rl.WHITE)
rl.DrawTexturePro(rt[1].texture, src, rl.Rectangle{f32(VW), 0, f32(VW), f32(VH)}, {}, 0, rl.WHITE)
rl.EndDrawing()
```

The negative source height is the standard raylib idiom for flipping the
texture so it draws right-side up.

## Procedural audio

raylib can load PCM from memory — no need for wav files on disk. Useful for
synthesized sound effects.

```odin
SR :: 22050
synth :: proc(dur_s: f32, gen: proc(t: f32, i: int) -> f32) -> rl.Sound {
    frames := int(f32(SR) * dur_s)
    buf := make([]i16, frames)
    defer delete(buf)
    for i in 0..<frames {
        s := clamp(gen(f32(i) / f32(SR), i), -1, 1)
        buf[i] = i16(s * 32000)
    }
    w := rl.Wave{
        frameCount = c.uint(frames),
        sampleRate = c.uint(SR),
        sampleSize = 16,
        channels   = 1,
        data       = raw_data(buf),
    }
    return rl.LoadSoundFromWave(w)   // raylib copies the data, safe to free buf
}
```

Init with `rl.InitAudioDevice()` after `InitWindow`, check
`rl.IsAudioDeviceReady()` before relying on sounds. `rl.SetSoundPitch` and
`rl.SetSoundVolume` work per-call. Working example: `games/lodestar/`.

## Permissions

The DRM platform needs:
- `/dev/dri/card*` — `video` group
- `/dev/input/event*` — `input` group

If a game launches but you get a blank screen or no input, check `groups`. To
add the user:

```
sudo usermod -aG video,input hsad   # then reboot
```

## Rebuilding raylib

If you ever need to nuke and rebuild raylib (e.g. upgrade version, switch
platform), the recipe is:

```bash
cd /tmp
git clone --depth 1 --branch 5.5 https://github.com/raysan5/raylib.git
cd raylib && mkdir build && cd build
cmake .. -DBUILD_SHARED_LIBS=OFF -DBUILD_EXAMPLES=OFF \
         -DCMAKE_BUILD_TYPE=Release -DPLATFORM=DRM
make -j4
cp raylib/libraylib.a /home/hsad/odin-linux-arm64-nightly+2026-04-02/vendor/raylib/linux/libraylib.a
```

Platform options: `Desktop` (GLFW/X11), `DRM` (KMS/DRM/GBM), `Web`, `Android`.
The cabinet wants `DRM`.

Required apt packages (already installed):
```
cmake clang
libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev
libgl-dev libegl-dev libgles2-mesa-dev
libdrm-dev libgbm-dev libinput-dev libudev-dev libxkbcommon-dev
libwayland-dev
```

## Reference

`games/skateboard-time-trial-v2/` is the first Odin game on the cabinet. Crib
from it for project layout, Camera3D setup, scene recycling, and the trick /
combo system.
