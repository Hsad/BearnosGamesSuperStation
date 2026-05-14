#!/bin/bash
# BREACH — Odin + Raylib, PLATFORM=DRM
set -e
cd "$(dirname "$0")"

ODIN=odin
if ! command -v "$ODIN" >/dev/null 2>&1; then
    ODIN="/home/hsad/odin-linux-arm64-nightly+2026-04-02/odin"
fi

BIN=./breach
SRC=breach.odin

DRM_LIBS="-lGLESv2 -lEGL -lgbm -ldrm -linput -ludev -lxkbcommon -lm"

if [ ! -x "$BIN" ] || [ "$SRC" -nt "$BIN" ]; then
    "$ODIN" build . -out:"$BIN" -o:speed -extra-linker-flags:"$DRM_LIBS"
fi

exec "$BIN"
