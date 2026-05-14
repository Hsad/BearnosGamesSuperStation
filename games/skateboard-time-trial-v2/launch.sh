#!/bin/bash
# Skateboard Time Trial v2 — Odin + Raylib (PLATFORM=DRM, no window manager).
# Rebuilds the binary if the source is newer, then execs.
set -e
cd "$(dirname "$0")"

ODIN=odin
if ! command -v "$ODIN" >/dev/null 2>&1; then
    ODIN="/home/hsad/odin-linux-arm64-nightly+2026-04-02/odin"
fi

BIN=./skateboard
SRC=skateboard_time_trial.odin

# raylib in the Odin vendor dir is built with PLATFORM=DRM, so we have to pull
# in the GLES/EGL/GBM/DRM/libinput stack at link time. (The Odin binding only
# adds -ldl -lpthread by default; everything else is the platform's problem.)
DRM_LIBS="-lGLESv2 -lEGL -lgbm -ldrm -linput -ludev -lxkbcommon -lm"

if [ ! -x "$BIN" ] || [ "$SRC" -nt "$BIN" ]; then
    "$ODIN" build . -out:"$BIN" -o:speed -extra-linker-flags:"$DRM_LIBS"
fi

exec "$BIN"
